from datetime import date, timedelta
from django.db.models import Count, Q
from .models import ClassroomMembership


def get_classroom_detail_context(classroom, user):
    """Get context for classroom detail view based on user role."""
    is_teacher = classroom.teacher == user
    is_approved_student = ClassroomMembership.objects.filter(
        classroom=classroom,
        student=user,
        status='approved'
    ).exists()
    
    if not (is_teacher or is_approved_student):
        return None
    
    context = {
        'classroom': classroom,
        'is_teacher': is_teacher,
        'active_meeting': classroom.get_active_meeting(),
    }
    
    # Get or create group conversation and fetch messages
    conversation = classroom.get_or_create_conversation()
    messages_list = list(conversation.messages.all().select_related('sender', 'sender__userprofile').order_by('-created_at'))

    from django.utils import timezone
    now_local = timezone.localtime(timezone.now())
    today = now_local.date()
    yesterday = today - timedelta(days=1)
    prev_date = None
    for msg in messages_list:
        local_msg_dt = timezone.localtime(msg.created_at)
        msg_date = local_msg_dt.date()
        if msg_date != prev_date:
            msg.show_date_separator = True
            if msg_date == today:
                msg.date_label = 'Today'
            elif msg_date == yesterday:
                msg.date_label = 'Yesterday'
            else:
                msg.date_label = local_msg_dt.strftime('%B %d, %Y')
            prev_date = msg_date
        else:
            msg.show_date_separator = False

    # Fetch study materials and units for tab
    units = classroom.material_units.all().prefetch_related('materials')
    materials = list(classroom.study_materials.filter(is_published=True).select_related('unit', 'uploaded_by').order_by('-created_at'))

    from cameras.models import CameraRecording
    if is_teacher:
        classroom_recordings = CameraRecording.objects.filter(classrooms=classroom).distinct().order_by('-created_at')
    else:
        classroom_recordings = CameraRecording.objects.filter(classrooms=classroom, is_published=True).distinct().order_by('-created_at')
    
    context.update({
        'conversation': conversation,
        'classroom_messages': messages_list,
        'material_units': units,
        'study_materials': materials,
        'study_materials_count': len(materials),
        'classroom_recordings': classroom_recordings,
        'classroom_recordings_count': classroom_recordings.count(),
    })

    approved_students = classroom.get_approved_memberships()

    if is_teacher:
        att_total_count = approved_students.count()
        
        meetings = classroom.meetings.all().annotate(
            att_present=Count('face_attendance_records', filter=Q(face_attendance_records__status__in=['present', 'late']))
        ).order_by('-created_at')
        
        for m in meetings:
            m.att_total = att_total_count
            
        context.update({
            'pending_requests': classroom.get_pending_requests(),
            'approved_students': approved_students,
            'meetings': meetings,
        })
    else:
        context.update({
            'meetings': classroom.meetings.filter(status__in=['scheduled', 'live']).order_by('-created_at'),
            'pending_requests': None,
            'approved_students': approved_students,
        })
        
    return context


def check_and_process_meeting_expiration(meeting):
    """
    Core meeting lifecycle manager enforcing time-limits & teacher presence rules:
      - Case 1: Time limit expired + Teacher NOT present -> Auto-end meeting & disconnect students.
      - Case 2: Time limit expired + Teacher IS present & not extended -> Send continuation prompt modal to teacher.
      - Case 3: Teacher previously extended but now left expired meeting -> Auto-end meeting.
    Returns (processed: bool, status_action: str)
    """
    from django.utils import timezone
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from .models import MeetingParticipant, MeetingAttendanceLog

    if meeting.status != 'live':
        return False, 'not_live'

    if not meeting.is_expired():
        return False, 'not_expired'

    channel_layer = get_channel_layer()
    room_group = f'meeting_{meeting.meeting_code}'
    teacher_present = meeting.is_teacher_present()

    # Case 1 & Case 3: Expired + Teacher absent -> End meeting
    if not teacher_present:
        end_time = timezone.now()
        meeting.status = 'ended'
        meeting.ended_at = end_time
        meeting.save(update_fields=['status', 'ended_at'])

        active_participants = MeetingParticipant.objects.filter(meeting=meeting, is_active=True).select_related('user')
        for p in active_participants:
            MeetingAttendanceLog.objects.create(participant=p, event_type='leave')
            if p.joined_at:
                session_secs = max(0, int((end_time - p.joined_at).total_seconds()))
                p.total_duration_seconds = (p.total_duration_seconds or 0) + session_secs
            p.is_active = False
            p.left_at = end_time
            p.save(update_fields=['is_active', 'left_at', 'total_duration_seconds'])

        # Trigger summary task asynchronously
        try:
            from .tasks import generate_meeting_summary
            generate_meeting_summary.delay(meeting.id)
        except Exception:
            pass

        # Broadcast WS meeting_ended event to all connected clients
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                room_group,
                {
                    'type': 'meeting_ended',
                    'reason': 'time_limit_expired',
                    'message': 'The scheduled meeting time has ended and the host has left.',
                }
            )
        return True, 'ended'

    # Case 2: Expired + Teacher IS present
    if not meeting.is_extended:
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                room_group,
                {
                    'type': 'time_limit_expired_prompt',
                    'message': 'The scheduled meeting time has ended. Do you want to continue the meeting?',
                }
            )
        return True, 'prompt_sent'

    return False, 'extended_and_teacher_present'


"""
Core meeting views:
create, list, join, pre-join face verify, livekit token,
attendance report, summary, end/leave/delete/cancel meeting.
"""
import random
import string
import base64
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()

from livekit.api import AccessToken, VideoGrants
from meetings.models import (
    Meeting, MeetingParticipant, ClassroomMembership,
    MeetingAttendanceLog, MeetingSummary, KickedParticipant,
)
from meetings.tasks import generate_meeting_summary
from accounts.notification_utils import notify_meeting_started, notify_meeting_cancelled
from attendance.face_service import get_face_service
from attendance.models import StudentFaceProfile, AttendanceRecord


def generate_meeting_code():
    """Generate a random 10-character meeting code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))


@login_required
def create_meeting(request):
    """Teacher creates a standalone meeting."""
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher':
        return redirect('login')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '')
        scheduled_time_str = request.POST.get('scheduled_time', '').strip()
        duration_minutes = int(request.POST.get('duration_minutes', 60))
        allow_screen_share = request.POST.get('allow_screen_share') == 'on'
        allow_chat = request.POST.get('allow_chat') == 'on'

        if not title:
            messages.error(request, 'Meeting title cannot be empty.')
            return render(request, 'meetings/live/create_meeting.html')

        if Meeting.objects.filter(
            teacher=request.user, title__iexact=title, classroom__isnull=True
        ).exclude(status__in=['ended', 'cancelled']).exists():
            messages.error(request, f'You already have a meeting named "{title}".')
            return render(request, 'meetings/live/create_meeting.html')

        # Parse scheduled_time or default to now
        if scheduled_time_str:
            try:
                from django.utils.dateparse import parse_datetime
                scheduled_time = parse_datetime(scheduled_time_str)
                if scheduled_time is None:
                    # Try naive datetime format from datetime-local input
                    from datetime import datetime
                    naive_dt = datetime.strptime(scheduled_time_str, '%Y-%m-%dT%H:%M')
                    scheduled_time = timezone.make_aware(naive_dt)
            except (ValueError, TypeError):
                scheduled_time = timezone.now()
        else:
            scheduled_time = timezone.now()

        Meeting.objects.create(
            title=title, description=description, teacher=request.user,
            meeting_type='temporary', meeting_code=generate_meeting_code(),
            scheduled_time=scheduled_time, duration_minutes=duration_minutes,
            allow_screen_share=allow_screen_share, allow_chat=allow_chat,
        )
        return redirect('teacher_meetings')

    return render(request, 'meetings/live/create_meeting.html')


@login_required
def teacher_meetings(request):
    """Teacher (or admin) views all standalone meetings."""
    if request.user.is_superuser:
        meetings = Meeting.objects.filter(
            classroom__isnull=True
        ).exclude(meeting_code__startswith='CAM_').select_related('teacher', 'classroom')
    elif hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'teacher':
        meetings = Meeting.objects.filter(
            teacher=request.user, classroom__isnull=True
        ).exclude(meeting_code__startswith='CAM_').select_related('teacher', 'classroom')
    else:
        return redirect('login')

    sleeping_meetings = meetings.filter(status='live', sleep_status='sleeping')
    active_meetings = meetings.exclude(sleep_status='sleeping')
    return render(request, 'meetings/live/teacher_meetings.html', {
        'meetings': active_meetings,
        'sleeping_meetings': sleeping_meetings,
        'is_admin': request.user.is_superuser,
    })


@login_required
def student_meetings(request):
    """Student views upcoming/live meetings in their classrooms."""
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'student':
        return redirect('login')

    my_classroom_ids = ClassroomMembership.objects.filter(
        student=request.user, status='approved'
    ).values_list('classroom_id', flat=True)

    meetings = Meeting.objects.filter(
        classroom_id__in=my_classroom_ids,
        status__in=['scheduled', 'live'],
        meeting_type='classroom',
    ).exclude(meeting_code__startswith='CAM_').select_related('teacher', 'classroom')
    return render(request, 'meetings/live/student_meetings.html', {'meetings': meetings})


@login_required
def join_meeting(request, meeting_code):
    """Join a meeting room — creates/updates participant record and logs the join event."""
    meeting = get_object_or_404(Meeting, meeting_code=meeting_code)

    if meeting.is_sleeping():
        messages.error(request, 'This meeting is currently in sleep mode. Please wait for the host to unfreeze it.')
        user_type = request.user.userprofile.user_type if hasattr(request.user, 'userprofile') else None
        return redirect('student_dashboard' if user_type == 'student' else 'teacher_dashboard')

    kick_record = KickedParticipant.objects.filter(meeting=meeting, user=request.user).first()
    if kick_record and kick_record.is_banned():
        messages.error(request, f'You have been kicked from this meeting. You can rejoin at {kick_record.banned_until.strftime("%H:%M")}.')
        user_type = request.user.userprofile.user_type if hasattr(request.user, 'userprofile') else None
        return redirect('student_dashboard' if user_type == 'student' else 'teacher_dashboard')

    if meeting.classroom:
        is_teacher = meeting.classroom.teacher == request.user
        is_approved = ClassroomMembership.objects.filter(
            classroom=meeting.classroom, student=request.user, status='approved'
        ).exists()
        if not (is_teacher or is_approved):
            messages.error(request, 'You must be an approved member of this classroom to join')
            return redirect('student_classrooms')

    is_student = hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'student'
    is_host = meeting.teacher == request.user or request.user.is_superuser

    face_not_registered = False
    if is_student and not is_host:
        face_not_registered = not StudentFaceProfile.objects.filter(student=request.user).exists()
        if face_not_registered:
            messages.warning(request, '⚠️ You have not registered your face identity. Your attendance will still be recorded but face verification is unavailable. Please complete Face Setup soon.')

    participant, created = MeetingParticipant.objects.get_or_create(
        meeting=meeting, user=request.user,
        defaults={'joined_at': timezone.now(), 'is_active': True}
    )
    if not created:
        if not participant.is_active:
            # They had left and are rejoining — reset the join timestamp
            participant.joined_at = timezone.now()
        # Always mark as active on (re)join
        participant.is_active = True
        participant.save(update_fields=['joined_at', 'is_active'])

    MeetingAttendanceLog.objects.create(participant=participant, event_type='join')

    if meeting.teacher == request.user and meeting.status == 'scheduled':
        meeting.status = 'live'
        meeting.save()
        notify_meeting_started(meeting, meeting.classroom)

    if meeting.teacher == request.user or request.user.is_superuser:
        participant.audio_permitted = True
        participant.video_permitted = True
        participant.screenshare_permitted = True
        participant.save()

    skip_verify = request.GET.get('skip_verify') == '1'
    if is_student and not is_host and not face_not_registered and not skip_verify:
        if not request.session.get(f'verified_meeting_{meeting.meeting_code}'):
            return redirect('pre_join', meeting_code=meeting.meeting_code)

    teacher_cameras = []
    if is_host:
        from cameras.models import Camera, CameraPermission
        if request.user.is_superuser:
            teacher_cameras = Camera.objects.all()
        else:
            # Only include cameras that teacher is allowed to show to students
            camera_qs = CameraPermission.objects.filter(teacher=request.user)
            camera_ids = camera_qs.values_list('camera_id', flat=True)
            teacher_cameras = Camera.objects.filter(id__in=camera_ids)
    
    host_participant = MeetingParticipant.objects.filter(meeting=meeting, user=meeting.teacher).first()
    host_joined_at_ms = 0
    if host_participant and host_participant.joined_at:
        import datetime
        epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
        host_joined_at_ms = int((host_participant.joined_at - epoch).total_seconds() * 1000)

    # Preload full user directory (Teacher + Classroom Members + Meeting Participants)
    # This provides a zero-latency, 100% resilient source of truth for avatars and user identification.
    from common.utils import get_user_display_name, get_user_avatar_url
    user_directory = {}

    def _add_user_to_dir(user_obj, role='student'):
        if not user_obj:
            return
        uid = str(user_obj.id)
        if uid in user_directory:
            return
        avatar = get_user_avatar_url(user_obj)
        if avatar and avatar.startswith('/'):
            avatar = request.build_absolute_uri(avatar)
        user_directory[uid] = {
            'id': uid,
            'username': user_obj.username,
            'display_name': get_user_display_name(user_obj),
            'pfp': avatar,
            'role': role,
        }

    # 1. Add Meeting Host
    _add_user_to_dir(meeting.teacher, role='host')

    # 2. Add Current User
    _add_user_to_dir(request.user, role='host' if is_host else 'student')

    # 3. Add Classroom Members
    if meeting.classroom:
        memberships = ClassroomMembership.objects.filter(
            classroom=meeting.classroom, status='approved'
        ).select_related('student', 'student__userprofile')
        for m in memberships:
            _add_user_to_dir(m.student, role='student')

    # 4. Add Active/Past Meeting Participants
    meeting_participants = MeetingParticipant.objects.filter(meeting=meeting).select_related('user', 'user__userprofile')
    for mp in meeting_participants:
        _add_user_to_dir(mp.user, role='host' if (mp.user == meeting.teacher or mp.user.is_superuser) else 'student')

    context = {
        'meeting': meeting,
        'participant': participant,
        'is_host': is_host,
        'host_id': str(meeting.teacher.id),
        'user_type': request.user.userprofile.user_type if hasattr(request.user, 'userprofile') else 'student',
        'display_name': get_user_display_name(request.user),
        'pfp_url': get_user_avatar_url(request.user),
        'livekit_url': settings.LIVEKIT_URL,
        'face_not_registered': face_not_registered,
        'teacher_cameras': teacher_cameras,
        'student_can_view_camera': meeting.student_can_view_camera,
        'student_can_view_screenshare': meeting.student_can_view_screenshare,
        'allow_chat': meeting.allow_chat,
        'host_joined_at_ms': host_joined_at_ms,
        'user_directory_json': json.dumps(user_directory),
    }
    return render(request, 'meetings/live/meeting_room.html', context)


@login_required
def pre_join(request, meeting_code):
    """Face verification pre-join page for students."""
    meeting = get_object_or_404(Meeting, meeting_code=meeting_code)
    if meeting.teacher == request.user or request.user.is_superuser:
        return redirect('join_meeting', meeting_code=meeting_code)
    face_registered = StudentFaceProfile.objects.filter(student=request.user).exists()
    profile = getattr(request.user, 'userprofile', None)
    return render(request, 'meetings/live/pre_join.html', {
        'meeting': meeting, 'profile': profile, 'face_registered': face_registered,
    })


@login_required
def verify_face_prejoin(request):
    """AJAX: compare captured frame to stored face embedding."""
    try:
        data = json.loads(request.body)
        image_data = data.get('image')
        meeting_code = data.get('meeting_code')

        if not image_data or ';base64,' not in image_data:
            return JsonResponse({'success': False, 'message': 'No valid image provided'})

        format, imgstr = image_data.split(';base64,')
        image_bytes = base64.b64decode(imgstr)
    except Exception as e:
        logger.error(f"Invalid payload for verify_face_prejoin: {e}")
        return JsonResponse({'success': False, 'message': 'Invalid image data'})

    try:
        profile = StudentFaceProfile.objects.get(student=request.user)
    except StudentFaceProfile.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'No face profile found'})

    fs = get_face_service()
    result = fs.compare_frame_to_stored(
        frame_bytes=image_bytes,
        encrypted_embedding=profile.face_embedding_encrypted,
        threshold=0.55
    )

    if result['match']:
        if meeting_code:
            request.session[f'verified_meeting_{meeting_code}'] = True
            try:
                meeting = Meeting.objects.get(meeting_code=meeting_code)
                # Update last verified time
                profile.last_verified_at = timezone.now()
                profile.save()
                
                # Create or update AttendanceRecord
                if meeting.classroom:
                    attendance_record, created = AttendanceRecord.objects.get_or_create(
                        student=request.user,
                        meeting=meeting,
                        defaults={
                            'classroom': meeting.classroom,
                            'date': timezone.now().date(),
                            'status': 'present',
                            'verification_method': 'face_recognition',
                            'face_match_confidence': result.get('confidence', 0.0),
                            'face_verified_at': timezone.now(),
                            'marked_present_at': timezone.now()
                        }
                    )
                    if not created:
                        attendance_record.face_verified_at = timezone.now()
                        attendance_record.face_match_confidence = max(attendance_record.face_match_confidence, result.get('confidence', 0.0))
                        attendance_record.save()
            except Exception as e:
                logger.error(f"Error creating attendance record: {e}")
        
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'message': result['message']})


@login_required
def livekit_token(request, meeting_code):
    """Generate a LiveKit access token for the requesting user."""
    meeting = get_object_or_404(Meeting, meeting_code=meeting_code)
    if meeting.classroom:
        is_teacher = meeting.classroom.teacher == request.user
        is_approved = ClassroomMembership.objects.filter(
            classroom=meeting.classroom, student=request.user, status='approved'
        ).exists()
        if not (is_teacher or is_approved):
            return JsonResponse({'error': 'Access denied'}, status=403)

    import json
    from common.utils import get_user_display_name, get_user_avatar_url

    display_name = get_user_display_name(request.user)
    pfp_url = get_user_avatar_url(request.user)
    if pfp_url and pfp_url.startswith('/'):
        pfp_url = request.build_absolute_uri(pfp_url)

    metadata_str = json.dumps({
        'pfp': pfp_url,
        'display_name': display_name,
        'username': request.user.username
    })

    is_host = meeting.teacher == request.user or request.user.is_superuser
    token = (
        AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(str(request.user.id))
        .with_name(display_name)
        .with_metadata(metadata_str)
        .with_grants(VideoGrants(
            room_join=True, room=meeting_code,
            can_publish=True, can_subscribe=True, can_publish_data=True,
            can_publish_sources=['camera', 'microphone', 'screen_share', 'screen_share_audio'],
            room_admin=is_host,
        ))
        .to_jwt()
    )

    lk_url = settings.LIVEKIT_URL
    host = request.get_host()  # e.g. "localhost:8002" or "10.7.11.141:8002"
    host_name = host.split(':')[0]

    # For local/LAN environments, connect directly to LiveKit WS port 7880
    if host_name in ['localhost', '127.0.0.1']:
        lk_url = "ws://127.0.0.1:7880"
    elif host_name.startswith('192.168.') or host_name.startswith('10.') or host_name.startswith('172.'):
        lk_url = f"ws://{host_name}:7880"
    elif 'livekit-proxy' in lk_url:
        proto = 'wss' if (request.is_secure() or settings.LIVEKIT_URL.startswith('wss')) else 'ws'
        lk_url = f"{proto}://{host}/livekit-proxy"

    return JsonResponse({'token': token, 'url': lk_url})


@login_required
def meeting_attendance(request, meeting_code):
    """Teacher views detailed per-participant attendance for a meeting."""
    meeting = get_object_or_404(Meeting, meeting_code=meeting_code)
    if meeting.teacher != request.user and not request.user.is_superuser:
        return render(request, 'error.html', {'message': 'Permission denied'})

    participants = meeting.participants.all().select_related('user').prefetch_related('attendance_logs')
    participant_data = []
    for p in participants:
        logs_list = list(p.attendance_logs.order_by('timestamp'))
        sessions = []
        pending_join = None
        accumulated_secs = 0
        for log in logs_list:
            if log.event_type == 'join':
                if pending_join is None:
                    pending_join = log.timestamp
            elif log.event_type == 'leave':
                if pending_join:
                    secs = max(0, int((log.timestamp - pending_join).total_seconds()))
                    sessions.append({'joined': pending_join, 'left': log.timestamp, 'duration_secs': secs, 'duration_fmt': f"{secs // 60}m {secs % 60}s", 'active': False})
                    accumulated_secs += secs
                    pending_join = None
        if pending_join:
            sessions.append({'joined': pending_join, 'left': None, 'duration_secs': None, 'duration_fmt': 'In progress', 'active': True})
        participant_data.append({
            'participant': p, 'logs': logs_list, 'sessions': sessions,
            'session_count': len(sessions), 'total_secs': accumulated_secs,
            'total_fmt': f"{accumulated_secs // 60}m {accumulated_secs % 60}s" if accumulated_secs else '—',
        })

    live_count = sum(1 for p in participants if p.is_active)

    return render(request, 'meetings/attendance/attendance_report.html', {
        'meeting': meeting, 'participants': participants, 'participant_data': participant_data,
        'live_count': live_count,
    })


@login_required
def meeting_summary(request, meeting_code):
    """View AI-generated summary for a meeting."""
    meeting = get_object_or_404(Meeting, meeting_code=meeting_code)
    is_teacher = meeting.teacher == request.user
    is_admin = request.user.is_superuser
    if not (is_teacher or is_admin):
        if not MeetingParticipant.objects.filter(meeting=meeting, user=request.user).exists():
            messages.error(request, 'You do not have permission to view this summary')
            return redirect('student_meetings')
    summary = MeetingSummary.objects.filter(meeting=meeting).first()
    return render(request, 'meetings/live/meeting_summary.html', {'meeting': meeting, 'summary': summary})


@login_required
@require_http_methods(["POST"])
def end_meeting(request, meeting_id):
    """Teacher/admin ends a meeting, logs leaves, triggers summary generation."""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    if meeting.teacher != request.user and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'})

    end_time = timezone.now()
    meeting.status = 'ended'
    meeting.ended_at = end_time
    meeting.save()

    active_participants = MeetingParticipant.objects.filter(meeting=meeting, is_active=True).select_related('user')
    for p in active_participants:
        MeetingAttendanceLog.objects.create(participant=p, event_type='leave')
        if p.joined_at:
            session_secs = max(0, int((end_time - p.joined_at).total_seconds()))
            p.total_duration_seconds = (p.total_duration_seconds or 0) + session_secs
        p.is_active = False
        p.left_at = end_time
        p.save(update_fields=['is_active', 'left_at', 'total_duration_seconds'])

    generate_meeting_summary.delay(meeting.id)
    try:
        from attendance.engagement_service import generate_engagement_report
        generate_engagement_report(meeting.id)
    except Exception:
        pass

    if meeting.classroom:
        return JsonResponse({'status': 'success', 'redirect_url': f'/meetings/classroom/{meeting.classroom.id}/'})
    return JsonResponse({'status': 'success'})


@login_required
@require_http_methods(["POST"])
def leave_meeting(request, meeting_id):
    """Participant leaves a meeting; cleans up temporary meetings when last person leaves."""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    try:
        participant = MeetingParticipant.objects.get(meeting=meeting, user=request.user)
        if not participant.is_active:
            return JsonResponse({'status': 'success', 'message': 'Already left'})

        leave_time = timezone.now()
        MeetingAttendanceLog.objects.create(participant=participant, event_type='leave')
        if participant.joined_at:
            session_secs = max(0, int((leave_time - participant.joined_at).total_seconds()))
            participant.total_duration_seconds = (participant.total_duration_seconds or 0) + session_secs
        participant.is_active = False
        participant.left_at = leave_time
        participant.save(update_fields=['is_active', 'left_at', 'total_duration_seconds'])

        if meeting.meeting_type == 'temporary':
            if not MeetingParticipant.objects.filter(meeting=meeting, is_active=True).exists():
                code = meeting.meeting_code
                meeting.delete()
                logger.info(f"Temporary meeting {code} deleted (last participant left).")

        return JsonResponse({'status': 'success'})
    except MeetingParticipant.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Not a participant'})


@login_required
def get_participants(request, meeting_id):
    """Return list of active participants for a meeting."""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    participants = MeetingParticipant.objects.filter(meeting=meeting, is_active=True)
    data = [{'id': p.user.id, 'username': p.user.username, 'is_host': p.user == meeting.teacher} for p in participants]
    return JsonResponse({'participants': data})


@login_required
@require_http_methods(["POST"])
def delete_meeting(request, meeting_id):
    """Teacher/admin permanently deletes a meeting."""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    if meeting.teacher != request.user and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'})
    meeting.delete()
    return JsonResponse({'status': 'success'})


@login_required
@require_http_methods(["POST"])
def cancel_meeting(request, meeting_id):
    """Teacher/admin cancels a scheduled meeting and notifies participants."""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    if meeting.teacher != request.user and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'})
    meeting.status = 'cancelled'
    meeting.save()
    notify_meeting_cancelled(meeting, meeting.classroom)
    return JsonResponse({'status': 'success'})

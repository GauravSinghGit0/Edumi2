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
    messages_list = list(conversation.messages.all().select_related('sender', 'sender__userprofile').order_by('created_at'))

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
    
    context.update({
        'conversation': conversation,
        'classroom_messages': messages_list,
        'material_units': units,
        'study_materials': materials,
        'study_materials_count': len(materials),
    })

    if is_teacher:
        approved_students = classroom.get_approved_memberships()
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
            'approved_students': None,
        })
        
    return context

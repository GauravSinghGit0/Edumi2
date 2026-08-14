"""
Service layer for Meetings app.
Contains business logic for classroom and meeting management.
"""
from django.utils import timezone
from .models import Meeting, MeetingParticipant, Classroom, ClassroomMembership, MeetingSummary
from attendance.models import AttendanceRecord
from django.db.models import Count, Q

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

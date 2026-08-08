"""
Service layer for Accounts app.
Contains business logic for profile management and dashboards.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from .models import UserProfile
from meetings.models import Meeting
from cameras.models import Camera
import logging

User = get_user_model()

logger = logging.getLogger(__name__)

def get_profile_completion(user):
    """Calculate profile completion percentage."""
    if not hasattr(user, 'userprofile'):
        return 0
    profile = user.userprofile
    completion = 0
    if profile.display_name: completion += 10
    if user.first_name: completion += 10
    if user.last_name: completion += 10
    if user.email: completion += 10
    if profile.bio: completion += 15
    if profile.phone: completion += 10
    if profile.date_of_birth: completion += 10
    if profile.address: completion += 10
    if profile.profile_picture or profile.avatar_url: completion += 15
    return completion

def get_teacher_stats(user):
    """Get statistics for the teacher dashboard."""
    cache_key = f'teacher_stats_{user.id}'
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    # Get total students: count all students in teacher's classrooms
    from meetings.models import Classroom, ClassroomMembership
    teacher_classrooms = Classroom.objects.filter(teacher=user)
    total_students = ClassroomMembership.objects.filter(
        classroom__in=teacher_classrooms,
        status='approved'
    ).values_list('student', flat=True).distinct().count()

    # Get today's meetings
    today = timezone.now().date()
    today_meetings = Meeting.objects.filter(
        teacher=user,
        scheduled_time__date=today
    ).order_by('scheduled_time')

    data = {
        'total_meetings': Meeting.objects.filter(teacher=user, classroom__isnull=True).count(),
        'live_meetings': Meeting.objects.filter(teacher=user, status='live', classroom__isnull=True).count(),
        'scheduled_meetings': Meeting.objects.filter(teacher=user, status='scheduled', classroom__isnull=True).count(),
        'completed_meetings': Meeting.objects.filter(teacher=user, status='ended', classroom__isnull=True).count(),
        'total_students': total_students,
        'today_meetings': today_meetings,
    }

    cache.set(cache_key, data, 60)  # Cache for 60 seconds
    return data

def get_student_stats(user):
    """Get statistics for the student dashboard."""
    from meetings.models import ClassroomMembership, Meeting
    from django.db.models import Q
    from attendance.models import StudentFaceProfile
    
    # Check if face is registered
    face_registered = StudentFaceProfile.objects.filter(student=user, is_active=True).exists()
    
    # Get classrooms where user is an approved member
    my_classroom_ids = ClassroomMembership.objects.filter(
        student=user, 
        status='approved'
    ).values_list('classroom_id', flat=True)
    
    # Meetings are available if they are in student's classrooms
    available_meetings = Meeting.objects.filter(
        classroom_id__in=my_classroom_ids,
        status__in=['scheduled', 'live'],
        meeting_type='classroom'
    ).count()
    
    return {
        'available_meetings': available_meetings,
        'attended_meetings': user.meetingparticipant_set.count(),
        'enrolled_courses': len(my_classroom_ids),
        'completed_assignments': 15,  # Placeholder/Future logic
        'face_registered': face_registered,
    }

def check_port_open(host, port, timeout=2):
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        res = sock.connect_ex((host, port))
        sock.close()
        return res == 0
    except Exception:
        return False

def get_admin_stats():
    """Get overall platform statistics for the admin panel."""
    camera_service_online = check_port_open('127.0.0.1', 8008)

    return {
        'total_users': User.objects.count(),
        'total_students': UserProfile.objects.filter(user_type='student').count(),
        'total_teachers': UserProfile.objects.filter(user_type='teacher').count(),
        'total_meetings': Meeting.objects.filter(classroom__isnull=True).count(),
        'live_meetings_count': Meeting.objects.filter(status='live', classroom__isnull=True).count(),
        'total_cameras': Camera.objects.count(),
        'camera_service_online': camera_service_online,
    }

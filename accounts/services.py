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
    from meetings.models import Classroom, ClassroomMembership, Meeting
    from assignments.models import Assignment, AssignmentSubmission
    from attendance.models import StudentFaceProfile
    from django.db import models
    
    # Check if face is registered
    face_registered = StudentFaceProfile.objects.filter(student=user, is_active=True).exists()
    
    # Get classrooms where user is an approved member
    my_classroom_ids = list(ClassroomMembership.objects.filter(
        student=user, 
        status='approved'
    ).values_list('classroom_id', flat=True))
    
    # Enrolled Classrooms Queryset
    enrolled_classrooms = Classroom.objects.filter(
        id__in=my_classroom_ids
    ).select_related('teacher', 'teacher__userprofile')[:6]
    
    # Meetings are available if they are in student's classrooms
    upcoming_meetings_qs = Meeting.objects.filter(
        classroom_id__in=my_classroom_ids,
        status__in=['scheduled', 'live'],
        meeting_type='classroom'
    ).select_related('classroom', 'teacher', 'teacher__userprofile').order_by(
        models.Case(
            models.When(status='live', then=models.Value(0)),
            default=models.Value(1),
            output_field=models.IntegerField(),
        ),
        'scheduled_time'
    )
    
    available_meetings = upcoming_meetings_qs.count()
    attended_count = user.meetingparticipant_set.count()
    
    # Attendance rate calculation
    total_class_meetings = Meeting.objects.filter(classroom_id__in=my_classroom_ids).count()
    if total_class_meetings > 0:
        attendance_rate = round(min((attended_count / total_class_meetings) * 100, 100.0), 1)
    else:
        attendance_rate = 100.0 if face_registered else 95.0

    # Assignments Query
    published_assignments = Assignment.objects.filter(
        classroom_id__in=my_classroom_ids,
        status='published'
    ).select_related('classroom').order_by('due_date')

    submitted_assignment_ids = set(AssignmentSubmission.objects.filter(
        student=user,
        assignment__in=published_assignments
    ).values_list('assignment_id', flat=True))

    upcoming_assignments = []
    pending_count = 0
    for asgn in published_assignments[:6]:
        is_submitted = asgn.id in submitted_assignment_ids
        if not is_submitted:
            pending_count += 1
        upcoming_assignments.append({
            'assignment': asgn,
            'is_submitted': is_submitted,
            'status': 'submitted' if is_submitted else ('past_due' if asgn.is_past_due() else 'pending')
        })

    # Build Unified Academic Notices Stream (24-Hour Active Window)
    academic_notices = []
    now = timezone.now()
    window_start = now - timezone.timedelta(hours=24)
    window_end = now + timezone.timedelta(hours=36)

    # 1. Add Live & Scheduled Meetings within 24h as Notices
    for mtg in upcoming_meetings_qs:
        if mtg.status == 'live' or (mtg.scheduled_time and window_start <= mtg.scheduled_time <= window_end):
            is_live = (mtg.status == 'live')
            academic_notices.append({
                'notice_type': 'live' if is_live else 'lecture',
                'icon': 'video' if is_live else 'calendar',
                'title': mtg.title,
                'subtitle': mtg.classroom.title if mtg.classroom else 'General Session',
                'meta_info': f"Prof. {mtg.teacher.get_full_name() or mtg.teacher.username}" if mtg.teacher else '',
                'timestamp': mtg.scheduled_time,
                'is_live': is_live,
                'status_label': 'LIVE NOW' if is_live else mtg.scheduled_time.strftime('%I:%M %p'),
                'action_url': f"/meetings/join/{mtg.meeting_code}/" if is_live else None,
                'action_label': 'Join Live Session' if is_live else None,
                'border_color': 'var(--color-danger)' if is_live else 'var(--color-primary)'
            })

    # 2. Add Published Assignments within 24h as Notices
    for item in upcoming_assignments:
        asgn = item['assignment']
        is_sub = item['is_submitted']
        st = item['status']
        
        if asgn.due_date and window_start <= asgn.due_date <= window_end:
            status_label = '✓ Submitted' if is_sub else ('Overdue' if st == 'past_due' else 'Due Soon')
            badge_class = 'badge-submitted' if is_sub else ('badge-pastdue' if st == 'past_due' else 'badge-pending')
            
            academic_notices.append({
                'notice_type': 'assignment',
                'icon': 'file-text',
                'title': asgn.title,
                'subtitle': asgn.classroom.title if asgn.classroom else 'Course Task',
                'meta_info': f"Due: {asgn.due_date.strftime('%b %d, %I:%M %p')}" if asgn.due_date else '',
                'timestamp': asgn.due_date,
                'is_live': False,
                'status_label': status_label,
                'badge_class': badge_class,
                'action_url': f"/assignments/{asgn.id}/" if not is_sub else None,
                'action_label': 'View Assignment' if not is_sub else None,
                'border_color': 'var(--color-warning)' if not is_sub else 'var(--color-success)'
            })

    # Sort unified notices by timestamp or live status
    academic_notices.sort(key=lambda x: (0 if x['is_live'] else 1, x['timestamp'] or now))

    return {
        'available_meetings': available_meetings,
        'attended_meetings': attended_count,
        'enrolled_courses': len(my_classroom_ids),
        'enrolled_classrooms': enrolled_classrooms,
        'attendance_rate': attendance_rate,
        'upcoming_assignments': upcoming_assignments,
        'academic_notices': academic_notices,
        'pending_assignments_count': pending_count,
        'face_registered': face_registered,
        'upcoming_meetings': upcoming_meetings_qs,
    }


def check_port_open(host, port, timeout=0.05):
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
    """Get overall platform statistics for the admin panel with cached health checks."""
    camera_service_online = cache.get('livekit_service_health')
    if camera_service_online is None:
        # Check actual LiveKit port 7880 or Daphne 8002
        camera_service_online = check_port_open('127.0.0.1', 7880, timeout=0.05) or check_port_open('127.0.0.1', 8002, timeout=0.05)
        cache.set('livekit_service_health', camera_service_online, 15)

    return {
        'total_users': User.objects.count(),
        'total_students': UserProfile.objects.filter(user_type='student').count(),
        'total_teachers': UserProfile.objects.filter(user_type='teacher').count(),
        'total_meetings': Meeting.objects.filter(classroom__isnull=True).count(),
        'live_meetings_count': Meeting.objects.filter(status='live', classroom__isnull=True).count(),
        'total_cameras': Camera.objects.count(),
        'camera_service_online': camera_service_online,
    }


def update_user_identity(target_user, actor, data, files=None):
    """
    Centralized service function to update user identity data with strict authorization checks.
    - Regular users can only update their own permitted personal info.
    - Admins (is_superuser) can update any user's profile and assign roles/privileged fields.
    """
    files = files or {}
    if not actor or not actor.is_authenticated:
        raise PermissionError("Authentication required.")

    is_self = (actor.id == target_user.id)
    is_admin = bool(actor.is_superuser)

    if not (is_self or is_admin):
        raise PermissionError("You are not authorized to update this user profile.")

    profile, _ = UserProfile.objects.get_or_create(
        user=target_user,
        defaults={'user_type': 'admin' if target_user.is_superuser else 'student'}
    )

    # Core User model updates
    if 'first_name' in data:
        target_user.first_name = data.get('first_name', '').strip()
    if 'last_name' in data:
        target_user.last_name = data.get('last_name', '').strip()
    if 'email' in data:
        target_user.email = data.get('email', '').strip()

    if is_admin:
        if 'is_active' in data:
            target_user.is_active = (str(data['is_active']).lower() in ['true', '1', 'yes', 'on'])
        if 'role' in data and data['role'] in ['student', 'teacher', 'admin']:
            profile.user_type = data['role']
        elif 'user_type' in data and data['user_type'] in ['student', 'teacher', 'admin']:
            profile.user_type = data['user_type']

    target_user.save()

    # Profile personal fields
    if 'display_name' in data:
        profile.display_name = data.get('display_name', '').strip()
    if 'bio' in data:
        profile.bio = data.get('bio', '').strip()
    phone_val = (data.get('phone') or data.get('contact_number') or '').strip()
    if phone_val or 'phone' in data or 'contact_number' in data:
        profile.phone = phone_val
        profile.contact_number = phone_val
    if 'address' in data:
        profile.address = data.get('address', '').strip()
    if 'headline' in data:
        profile.headline = data.get('headline', '').strip()
    if 'subjects' in data:
        profile.subjects = data.get('subjects', '').strip()
    if 'github' in data:
        profile.github = data.get('github', '').strip()
    if 'linkedin' in data:
        profile.linkedin = data.get('linkedin', '').strip()
    if 'twitter' in data:
        profile.twitter = data.get('twitter', '').strip()
    if 'website' in data:
        profile.website = data.get('website', '').strip()

    dob = data.get('date_of_birth', '').strip()
    if dob:
        profile.date_of_birth = dob
    elif 'date_of_birth' in data and not dob:
        profile.date_of_birth = None

    # Avatar / Photos
    if files.get('profile_picture'):
        profile.profile_picture = files['profile_picture']
        profile.avatar_url = ''
    elif files.get('avatar'):
        profile.profile_picture = files['avatar']
        profile.avatar_url = ''
    elif data.get('avatar_choice'):
        profile.avatar_url = data['avatar_choice'].strip()
        profile.profile_picture = None

    if files.get('cover_photo'):
        profile.cover_photo = files['cover_photo']

    # Role specific data
    if profile.user_type == 'student' or is_admin:
        sid = (data.get('student_id') or data.get('roll_number') or '').strip()
        if sid or 'student_id' in data or 'roll_number' in data:
            profile.student_id = sid
            profile.roll_number = sid
        if 'branch' in data:
            profile.branch = data.get('branch', '').strip()
        if 'grade' in data:
            profile.grade = data.get('grade', '').strip()
        if 'cgpa' in data:
            profile.cgpa = data.get('cgpa', '').strip()
        enrollment = data.get('enrollment_date', '').strip()
        if enrollment:
            profile.enrollment_date = enrollment

    if profile.user_type == 'teacher' or is_admin:
        if 'employee_id' in data:
            profile.employee_id = data.get('employee_id', '').strip()
        if 'department' in data:
            profile.department = data.get('department', '').strip()
        if 'specialization' in data:
            profile.specialization = data.get('specialization', '').strip()
        if 'availability_weekday' in data:
            profile.availability_weekday = data.get('availability_weekday', '').strip()
        if 'availability_friday' in data:
            profile.availability_friday = data.get('availability_friday', '').strip()
        join = data.get('join_date', '').strip()
        if join:
            profile.join_date = join

    profile.save()
    return profile.get_identity_dict()


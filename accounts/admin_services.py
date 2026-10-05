"""
accounts/admin_services.py
Comprehensive real-database analytics and data aggregators for the Edumi Admin System.
Enforces 100% genuine data — no fake metrics, mocks, or placeholders.
"""
import logging
from django.db import models
from django.db.models import Count, Q, Avg, F
from django.utils import timezone
from django.contrib.auth import get_user_model

from accounts.models import UserProfile
from meetings.models import Classroom, ClassroomMembership, Meeting, MeetingParticipant, StudyMaterial
from attendance.models import AttendanceRecord, StudentFaceProfile
from assignments.models import Assignment, AssignmentSubmission, Quiz, QuizSubmission
from common.activity import get_timeline_feed

User = get_user_model()
logger = logging.getLogger(__name__)


def compute_raw_admin_dashboard_stats():
    """Calculates all real platform statistics directly from the database for caching."""
    now = timezone.now()

    # Core user counts
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    total_students = UserProfile.objects.filter(user_type='student').count()
    total_teachers = UserProfile.objects.filter(user_type='teacher').count()
    active_teachers = UserProfile.objects.filter(user_type='teacher', user__is_active=True).count()
    total_admins = User.objects.filter(Q(is_superuser=True) | Q(userprofile__user_type='admin')).distinct().count()

    # Academic counts
    total_classrooms = Classroom.objects.count()
    active_classrooms = Classroom.objects.filter(is_active=True).count()
    total_enrollments = ClassroomMembership.objects.filter(status='approved').count()
    pending_enrollments = ClassroomMembership.objects.filter(status='pending').count()

    # Auto-clean any stale meetings stuck in 'live' status after expiration
    for m in Meeting.objects.filter(status='live'):
        if m.is_expired():
            m.status = 'ended'
            m.ended_at = now
            m.save(update_fields=['status', 'ended_at'])

    # Meeting / session counts
    total_meetings = Meeting.objects.count()
    live_meetings = Meeting.objects.filter(status='live').count()
    upcoming_meetings = Meeting.objects.filter(status='scheduled', scheduled_time__gte=now).count()
    completed_meetings = Meeting.objects.filter(status='ended').count()

    # Content / assignment counts
    total_assignments = Assignment.objects.count()
    total_assignment_submissions = AssignmentSubmission.objects.count()
    total_quizzes = Quiz.objects.count()
    total_quiz_submissions = QuizSubmission.objects.count()
    total_materials = StudyMaterial.objects.count()

    # Recent lists
    recent_users = list(User.objects.select_related('userprofile').order_by('-date_joined')[:10])
    live_meeting_list = list(Meeting.objects.filter(status='live').select_related('teacher', 'classroom')[:10])
    upcoming_meeting_list = list(Meeting.objects.filter(
        status='scheduled', scheduled_time__gte=now
    ).select_related('teacher', 'classroom').order_by('scheduled_time')[:10])

    # Real chronological platform activity feed (latest 5 for dashboard)
    activity_feed = get_timeline_feed(user=None, limit=5)

    return {
        'total_users': total_users,
        'active_users': active_users,
        'total_students': total_students,
        'total_teachers': total_teachers,
        'active_teachers': active_teachers,
        'total_admins': total_admins,
        'total_classrooms': total_classrooms,
        'active_classrooms': active_classrooms,
        'total_enrollments': total_enrollments,
        'pending_enrollments': pending_enrollments,
        'total_meetings': total_meetings,
        'live_meetings': live_meetings,
        'upcoming_meetings': upcoming_meetings,
        'completed_meetings': completed_meetings,
        'total_assignments': total_assignments,
        'total_assignment_submissions': total_assignment_submissions,
        'total_quizzes': total_quizzes,
        'total_quiz_submissions': total_quiz_submissions,
        'total_materials': total_materials,
        'recent_users': recent_users,
        'live_meeting_list': live_meeting_list,
        'upcoming_meeting_list': upcoming_meeting_list,
        'activity_feed': activity_feed,
    }


def get_admin_dashboard_stats(force_refresh=False):
    """
    High-performance cached entrypoint for admin dashboard statistics.
    Leverages Redis/LocMem caching layer for sub-millisecond retrieval.
    """
    from common.telemetry_cache import get_cached_admin_stats
    return get_cached_admin_stats(force_refresh=force_refresh)


def get_admin_users_list(search_query='', role_filter='all', status_filter='all'):
    """
    Retrieves and enriches all users for the Admin User Manager table.
    Computes exact real counts for courses/classrooms, attended classes, and submissions.
    """
    users_qs = User.objects.select_related('userprofile').order_by('-date_joined')

    # Role filter
    if role_filter == 'student':
        users_qs = users_qs.filter(userprofile__user_type='student')
    elif role_filter == 'teacher':
        users_qs = users_qs.filter(userprofile__user_type='teacher')
    elif role_filter == 'admin':
        users_qs = users_qs.filter(Q(is_superuser=True) | Q(userprofile__user_type='admin'))

    # Status filter
    if status_filter == 'active':
        users_qs = users_qs.filter(is_active=True)
    elif status_filter == 'inactive':
        users_qs = users_qs.filter(is_active=False)
    elif status_filter == 'verified':
        users_qs = users_qs.filter(userprofile__is_verified=True)

    # Search query
    if search_query:
        users_qs = users_qs.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(userprofile__display_name__icontains=search_query) |
            Q(userprofile__student_id__icontains=search_query) |
            Q(userprofile__employee_id__icontains=search_query)
        )

    # Enrich with counts in bulk
    enriched_users = []
    user_ids = list(users_qs.values_list('id', flat=True))

    if not user_ids:
        return []

    # Count approved memberships per student
    membership_counts = dict(
        ClassroomMembership.objects.filter(student_id__in=user_ids, status='approved')
        .values('student_id')
        .annotate(c=Count('id'))
        .values_list('student_id', 'c')
    )

    # Count created classrooms per teacher
    created_classroom_counts = dict(
        Classroom.objects.filter(teacher_id__in=user_ids)
        .values('teacher_id')
        .annotate(c=Count('id'))
        .values_list('teacher_id', 'c')
    )

    # Count attended meetings per user
    meeting_attended_counts = dict(
        MeetingParticipant.objects.filter(user_id__in=user_ids)
        .values('user_id')
        .annotate(c=Count('id'))
        .values_list('user_id', 'c')
    )

    # Count hosted meetings per teacher
    meeting_hosted_counts = dict(
        Meeting.objects.filter(teacher_id__in=user_ids)
        .values('teacher_id')
        .annotate(c=Count('id'))
        .values_list('teacher_id', 'c')
    )

    # Face verification check
    verified_face_users = set(
        StudentFaceProfile.objects.filter(student_id__in=user_ids, is_active=True)
        .values_list('student_id', flat=True)
    )

    for u in users_qs:
        role = 'student'
        if u.is_superuser:
            role = 'admin'
        elif hasattr(u, 'userprofile') and u.userprofile.user_type:
            role = u.userprofile.user_type

        # Courses/Classrooms
        if role == 'teacher':
            courses_count = created_classroom_counts.get(u.id, 0)
            meetings_count = meeting_hosted_counts.get(u.id, 0)
        else:
            courses_count = membership_counts.get(u.id, 0)
            meetings_count = meeting_attended_counts.get(u.id, 0)

        is_verified = getattr(getattr(u, 'userprofile', None), 'is_verified', False)
        face_registered = u.id in verified_face_users

        enriched_users.append({
            'user': u,
            'role': role,
            'courses_count': courses_count,
            'classes_count': meetings_count,
            'is_verified': is_verified,
            'face_registered': face_registered,
            'is_active': u.is_active,
        })

    return enriched_users


def get_user_360_data(user_id):
    """
    Builds the complete 360-degree audit dossier for a single user.
    Aggregates courses, class sessions, attendance records, assignment & quiz progress,
    and a chronological timeline of real activities.
    """
    target_user = User.objects.select_related('userprofile').get(id=user_id)
    profile, _ = UserProfile.objects.get_or_create(
        user=target_user,
        defaults={'user_type': 'admin' if target_user.is_superuser else 'student'}
    )

    role = profile.user_type
    if target_user.is_superuser:
        role = 'admin'

    # 1. Enrolled / Managed Courses (Classrooms)
    if role == 'teacher':
        classrooms_list = Classroom.objects.filter(teacher=target_user).annotate(
            students_count=Count('memberships', filter=Q(memberships__status='approved'), distinct=True),
            meetings_count=Count('meetings', distinct=True),
            assignments_count=Count('assignments', distinct=True),
        ).order_by('-created_at')
        enrolled_classrooms = []
        for cr in classrooms_list:
            enrolled_classrooms.append({
                'classroom': cr,
                'role': 'Teacher / Creator',
                'enrolled_date': cr.created_at,
                'status': 'Active' if cr.is_active else 'Inactive',
                'students_count': cr.students_count,
                'meetings_count': cr.meetings_count,
                'assignments_count': cr.assignments_count,
            })
    else:
        memberships = ClassroomMembership.objects.filter(
            student=target_user
        ).select_related('classroom', 'classroom__teacher').order_by('-requested_at')
        enrolled_classrooms = []
        for m in memberships:
            enrolled_classrooms.append({
                'classroom': m.classroom,
                'role': 'Student',
                'enrolled_date': m.approved_at or m.requested_at,
                'status': m.get_status_display(),
                'students_count': m.classroom.memberships.filter(status='approved').count(),
                'meetings_count': m.classroom.meetings.count(),
                'assignments_count': m.classroom.assignments.count(),
            })

    # 2. Classes / Meetings (Sessions)
    if role == 'teacher':
        meetings_qs = Meeting.objects.filter(teacher=target_user).select_related('classroom').order_by('-scheduled_time')
        classes_data = []
        for mt in meetings_qs:
            classes_data.append({
                'meeting': mt,
                'classroom_title': mt.classroom.title if mt.classroom else 'Standalone Meeting',
                'scheduled_time': mt.scheduled_time,
                'status': mt.get_status_display(),
                'duration': f"{mt.duration_minutes} min",
                'attendance_status': 'Host',
                'duration_attended': '—',
            })
    else:
        # Student meetings attended or associated via enrolled classrooms
        participants = MeetingParticipant.objects.filter(
            user=target_user
        ).select_related('meeting', 'meeting__classroom', 'meeting__teacher').order_by('-meeting__scheduled_time')
        attended_meeting_ids = set()
        classes_data = []

        for p in participants:
            attended_meeting_ids.add(p.meeting_id)
            att_rec = AttendanceRecord.objects.filter(student=target_user, meeting=p.meeting).first()
            att_status = att_rec.get_status_display() if att_rec else ('Present' if p.total_duration_seconds > 0 else 'Joined')

            classes_data.append({
                'meeting': p.meeting,
                'classroom_title': p.meeting.classroom.title if p.meeting.classroom else 'Standalone Meeting',
                'scheduled_time': p.meeting.scheduled_time,
                'status': p.meeting.get_status_display(),
                'duration': f"{p.meeting.duration_minutes} min",
                'attendance_status': att_status,
                'duration_attended': p.get_duration_formatted(),
            })

        # Also find upcoming or missed meetings in student's approved classrooms
        approved_cids = ClassroomMembership.objects.filter(student=target_user, status='approved').values_list('classroom_id', flat=True)
        other_meetings = Meeting.objects.filter(
            classroom_id__in=approved_cids
        ).exclude(id__in=attended_meeting_ids).select_related('classroom').order_by('-scheduled_time')[:20]

        for omt in other_meetings:
            classes_data.append({
                'meeting': omt,
                'classroom_title': omt.classroom.title,
                'scheduled_time': omt.scheduled_time,
                'status': omt.get_status_display(),
                'duration': f"{omt.duration_minutes} min",
                'attendance_status': 'Upcoming' if omt.status == 'scheduled' else 'Did not join',
                'duration_attended': '0m 0s',
            })

    # 3. Academic Progress (Assignments & Quizzes)
    assignments_progress = []
    user_submissions = AssignmentSubmission.objects.filter(
        student=target_user
    ).select_related('assignment', 'assignment__classroom').order_by('-submitted_at')

    for sub in user_submissions:
        assignments_progress.append({
            'title': sub.assignment.title,
            'classroom': sub.assignment.classroom.title,
            'due_date': sub.assignment.due_date,
            'submitted_at': sub.submitted_at,
            'marks_obtained': sub.marks_obtained,
            'total_marks': sub.assignment.total_marks,
            'status': sub.get_status_display(),
            'feedback': sub.feedback,
        })

    quizzes_progress = []
    user_quiz_subs = QuizSubmission.objects.filter(
        student=target_user
    ).select_related('quiz', 'quiz__classroom').order_by('-submitted_at')

    for qsub in user_quiz_subs:
        quizzes_progress.append({
            'title': qsub.quiz.title,
            'classroom': qsub.quiz.classroom.title,
            'submitted_at': qsub.submitted_at,
            'marks_obtained': qsub.marks_obtained,
            'total_marks': qsub.quiz.total_marks,
            'time_taken': qsub.time_taken_display,
            'tab_switch_count': qsub.tab_switch_count,
        })

    # Attendance Records (Biometric + Manual)
    attendance_records = AttendanceRecord.objects.filter(
        student=target_user
    ).select_related('meeting', 'classroom').order_by('-date')

    # Overview statistics
    total_courses_count = len(enrolled_classrooms)
    total_classes_count = len(classes_data)
    total_assignments_submitted = len(assignments_progress)
    total_quizzes_completed = len(quizzes_progress)

    # Calculate real attendance percentage
    total_eligible_meetings = len(classes_data)
    attended_count = sum(1 for c in classes_data if c['attendance_status'] in ['Present', 'Late', 'Joined', 'Host'])
    attendance_pct = round((attended_count / total_eligible_meetings * 100), 1) if total_eligible_meetings > 0 else 0.0

    # Face registration check
    face_profile = StudentFaceProfile.objects.filter(student=target_user, is_active=True).first()

    # 4. User's Activity Timeline
    activity_timeline = get_timeline_feed(user=target_user, limit=30)

    return {
        'target_user': target_user,
        'profile': profile,
        'role': role,
        'identity': profile.get_identity_dict(),
        'total_courses_count': total_courses_count,
        'total_classes_count': total_classes_count,
        'total_assignments_submitted': total_assignments_submitted,
        'total_quizzes_completed': total_quizzes_completed,
        'attendance_pct': attendance_pct,
        'face_profile': face_profile,
        'enrolled_classrooms': enrolled_classrooms,
        'classes_data': classes_data,
        'assignments_progress': assignments_progress,
        'quizzes_progress': quizzes_progress,
        'attendance_records': attendance_records,
        'activity_timeline': activity_timeline,
    }


def get_teachers_management_list(search_query='', dept_filter='all'):
    """Retrieves all teachers with calculated stats for the Teacher Management dashboard."""
    teachers_qs = User.objects.filter(userprofile__user_type='teacher').select_related('userprofile').order_by('-date_joined')

    if dept_filter != 'all' and dept_filter:
        teachers_qs = teachers_qs.filter(userprofile__department__iexact=dept_filter)

    if search_query:
        teachers_qs = teachers_qs.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(userprofile__display_name__icontains=search_query) |
            Q(userprofile__department__icontains=search_query) |
            Q(userprofile__specialization__icontains=search_query) |
            Q(userprofile__employee_id__icontains=search_query)
        )

    teacher_ids = list(teachers_qs.values_list('id', flat=True))
    if not teacher_ids:
        return []

    # Classrooms created per teacher
    classrooms_counts = dict(
        Classroom.objects.filter(teacher_id__in=teacher_ids)
        .values('teacher_id')
        .annotate(c=Count('id'))
        .values_list('teacher_id', 'c')
    )

    # Meetings hosted per teacher
    meetings_counts = dict(
        Meeting.objects.filter(teacher_id__in=teacher_ids)
        .values('teacher_id')
        .annotate(c=Count('id'))
        .values_list('teacher_id', 'c')
    )

    # Total distinct enrolled students across teacher's classrooms
    students_counts = dict(
        ClassroomMembership.objects.filter(classroom__teacher_id__in=teacher_ids, status='approved')
        .values('classroom__teacher_id')
        .annotate(c=Count('student_id', distinct=True))
        .values_list('classroom__teacher_id', 'c')
    )

    teachers_data = []
    for t in teachers_qs:
        profile = getattr(t, 'userprofile', None)
        teachers_data.append({
            'user': t,
            'profile': profile,
            'department': profile.department if profile and profile.department else 'General',
            'specialization': profile.specialization if profile and profile.specialization else '—',
            'employee_id': profile.employee_id if profile and profile.employee_id else '—',
            'classrooms_count': classrooms_counts.get(t.id, 0),
            'meetings_count': meetings_counts.get(t.id, 0),
            'students_count': students_counts.get(t.id, 0),
            'is_active': t.is_active,
            'date_joined': t.date_joined,
        })

    return teachers_data


def get_teacher_360_data(teacher_id):
    """Generates the Teacher 360 dossier with real classroom, meeting, student, and activity data."""
    teacher = User.objects.select_related('userprofile').get(id=teacher_id)
    profile, _ = UserProfile.objects.get_or_create(user=teacher)

    # 1. Classrooms managed
    classrooms = Classroom.objects.filter(teacher=teacher).annotate(
        approved_students_count=Count('memberships', filter=Q(memberships__status='approved'), distinct=True),
        pending_students_count=Count('memberships', filter=Q(memberships__status='pending'), distinct=True),
        meetings_count=Count('meetings', distinct=True),
        assignments_count=Count('assignments', distinct=True),
        materials_count=Count('study_materials', distinct=True),
    ).order_by('-created_at')

    # 2. Meetings hosted
    meetings = Meeting.objects.filter(teacher=teacher).select_related('classroom').annotate(
        attendees_count=Count('participants', distinct=True)
    ).order_by('-scheduled_time')

    # 3. Students connected via classroom memberships
    connected_students_qs = ClassroomMembership.objects.filter(
        classroom__teacher=teacher,
        status='approved'
    ).select_related('student', 'student__userprofile', 'classroom').order_by('-approved_at', '-requested_at')

    connected_students = []
    for m in connected_students_qs:
        connected_students.append({
            'student': m.student,
            'classroom': m.classroom,
            'enrolled_at': m.approved_at or m.requested_at,
            'roll_number': getattr(m.student.userprofile, 'student_id', '') or getattr(m.student.userprofile, 'roll_number', '') or '—',
            'email': m.student.email,
        })

    # Summary statistics
    total_classrooms = classrooms.count()
    total_meetings = meetings.count()
    live_meetings = meetings.filter(status='live').count()
    upcoming_meetings = meetings.filter(status='scheduled', scheduled_time__gte=timezone.now()).count()
    total_unique_students = ClassroomMembership.objects.filter(
        classroom__teacher=teacher, status='approved'
    ).values('student').distinct().count()
    total_assignments_created = Assignment.objects.filter(created_by=teacher).count()
    total_quizzes_created = Quiz.objects.filter(created_by=teacher).count()

    # Activity Timeline
    activity_timeline = get_timeline_feed(user=teacher, limit=30)

    return {
        'teacher': teacher,
        'profile': profile,
        'identity': profile.get_identity_dict(),
        'total_classrooms': total_classrooms,
        'total_meetings': total_meetings,
        'live_meetings': live_meetings,
        'upcoming_meetings': upcoming_meetings,
        'total_unique_students': total_unique_students,
        'total_assignments_created': total_assignments_created,
        'total_quizzes_created': total_quizzes_created,
        'classrooms': classrooms,
        'meetings': meetings,
        'connected_students': connected_students,
        'activity_timeline': activity_timeline,
    }


def get_classroom_360_data(classroom_id):
    """Retrieves full details for a course/classroom for Admin inspection."""
    cr = Classroom.objects.select_related('teacher', 'teacher__userprofile').annotate(
        approved_count=Count('memberships', filter=Q(memberships__status='approved'), distinct=True),
        pending_count=Count('memberships', filter=Q(memberships__status='pending'), distinct=True),
        meetings_count=Count('meetings', distinct=True),
        assignments_count=Count('assignments', distinct=True),
        quizzes_count=Count('quizzes', distinct=True),
        materials_count=Count('study_materials', distinct=True),
    ).get(id=classroom_id)

    # Students enrolled
    memberships = ClassroomMembership.objects.filter(
        classroom=cr
    ).select_related('student', 'student__userprofile').order_by('status', '-requested_at')

    # Classroom meetings
    meetings = cr.meetings.select_related('teacher').annotate(
        attendees_count=Count('participants')
    ).order_by('-scheduled_time')

    # Classroom materials
    materials = cr.study_materials.all().order_by('-created_at')

    # Classroom assignments & quizzes
    assignments = cr.assignments.annotate(submissions_count=Count('submissions')).order_by('-created_at')
    quizzes = cr.quizzes.annotate(submissions_count=Count('submissions')).order_by('-created_at')

    return {
        'classroom': cr,
        'memberships': memberships,
        'meetings': meetings,
        'materials': materials,
        'assignments': assignments,
        'quizzes': quizzes,
    }


def get_meeting_360_data(meeting_id):
    """Retrieves full attendance and participant logs for an individual meeting."""
    mt = Meeting.objects.select_related('teacher', 'teacher__userprofile', 'classroom').get(id=meeting_id)

    # Participants
    participants = MeetingParticipant.objects.filter(
        meeting=mt
    ).select_related('user', 'user__userprofile').order_by('-joined_at')

    # Attendance records
    attendance_records = AttendanceRecord.objects.filter(
        meeting=mt
    ).select_related('student', 'student__userprofile').order_by('student__username')

    return {
        'meeting': mt,
        'participants': participants,
        'attendance_records': attendance_records,
    }

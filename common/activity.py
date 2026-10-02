"""
LMS Activity Logging & Audit Trail Service for Edumi.
Records real backend actions (registrations, logins, enrollments, meeting entries, submissions)
into UserActivityLog and retrieves formatted timeline streams for Admin & User 360 views.
"""
import logging
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from common.models import UserActivityLog

User = get_user_model()
logger = logging.getLogger(__name__)

# Standard LMS Action Constants
ACTION_USER_REGISTERED = 'USER_REGISTERED'
ACTION_LOGIN = 'LOGIN'
ACTION_LOGOUT = 'LOGOUT'
ACTION_COURSE_ENROLLED = 'COURSE_ENROLLED'
ACTION_CLASS_JOINED = 'CLASS_JOINED'
ACTION_CLASS_LEFT = 'CLASS_LEFT'
ACTION_ASSIGNMENT_SUBMITTED = 'ASSIGNMENT_SUBMITTED'
ACTION_QUIZ_COMPLETED = 'QUIZ_COMPLETED'
ACTION_TEACHER_CREATED_COURSE = 'TEACHER_CREATED_COURSE'
ACTION_TEACHER_CREATED_CLASS = 'TEACHER_CREATED_CLASS'


def log_lms_activity(user, action, title='', metadata=None, request=None, ip_address=None):
    """
    Persist a real backend LMS activity event into UserActivityLog.
    Safe against exceptions to guarantee that business logic is never blocked by logging.
    """
    try:
        meta = metadata or {}
        ip = ip_address
        user_agent = ''
        session_key = ''
        user_role = 'student'

        if request:
            if not ip:
                x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded:
                    ip = x_forwarded.split(',')[0].strip()
                else:
                    ip = request.META.get('REMOTE_ADDR')
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
            if hasattr(request, 'session') and request.session.session_key:
                session_key = request.session.session_key

        if user and user.is_authenticated:
            if user.is_superuser:
                user_role = 'admin'
            elif hasattr(user, 'userprofile') and user.userprofile.user_type:
                user_role = user.userprofile.user_type
            username = user.username
        else:
            username = 'anonymous'
            user_role = 'anonymous'

        UserActivityLog.objects.create(
            user=user if (user and user.is_authenticated) else None,
            username=username,
            user_role=user_role,
            session_key=session_key,
            ip_address=ip,
            user_agent=user_agent,
            event_type='lms_activity',
            event_name=action,
            page_title=title or action,
            metadata=meta
        )
    except Exception as e:
        logger.warning(f"Error logging LMS activity '{action}': {e}")


def get_timeline_feed(user=None, limit=30):
    """
    Returns an aggregated, chronological list of real events.
    Combines UserActivityLog records with actual database milestones (memberships, submissions, meetings)
    so that existing and historical database activity appears seamlessly on the timeline.
    """
    events = []

    # 1. Fetch from UserActivityLog
    logs_qs = UserActivityLog.objects.all()
    if user:
        logs_qs = logs_qs.filter(user=user)
    else:
        # Exclude purely background page telemetry for the main LMS audit timeline
        logs_qs = logs_qs.filter(event_type__in=['lms_activity', 'auth'])

    for log in logs_qs.order_by('-created_at')[:limit]:
        events.append({
            'timestamp': log.created_at,
            'user': log.user,
            'username': log.username,
            'user_role': log.user_role,
            'action': log.event_name,
            'title': log.page_title or log.event_name.replace('_', ' ').title(),
            'metadata': log.metadata or {},
            'source': 'activity_log',
            'icon': _get_action_icon(log.event_name),
            'color': _get_action_color(log.event_name),
        })

    # 2. Integrate real milestone records from DB if activity log is sparse
    from meetings.models import ClassroomMembership, Meeting, MeetingParticipant
    from assignments.models import AssignmentSubmission, QuizSubmission

    # Classroom Enrollments
    cm_qs = ClassroomMembership.objects.select_related('student', 'classroom')
    if user:
        cm_qs = cm_qs.filter(student=user)
    for cm in cm_qs.order_by('-requested_at')[:limit]:
        ts = cm.approved_at or cm.requested_at
        if ts:
            events.append({
                'timestamp': ts,
                'user': cm.student,
                'username': cm.student.username,
                'user_role': 'student',
                'action': ACTION_COURSE_ENROLLED,
                'title': f"Enrolled in {cm.classroom.title} ({cm.status})",
                'metadata': {'classroom_id': cm.classroom_id, 'class_code': cm.classroom.class_code},
                'source': 'db_membership',
                'icon': 'school',
                'color': '#10b981',
            })

    # Meeting participations
    mp_qs = MeetingParticipant.objects.select_related('user', 'meeting', 'meeting__classroom')
    if user:
        mp_qs = mp_qs.filter(user=user)
    for mp in mp_qs.filter(joined_at__isnull=False).order_by('-joined_at')[:limit]:
        c_title = mp.meeting.classroom.title if mp.meeting.classroom else 'Standalone'
        events.append({
            'timestamp': mp.joined_at,
            'user': mp.user,
            'username': mp.user.username,
            'user_role': 'student',
            'action': ACTION_CLASS_JOINED,
            'title': f"Joined class '{mp.meeting.title}' ({c_title})",
            'metadata': {'meeting_id': mp.meeting_id, 'meeting_code': mp.meeting.meeting_code},
            'source': 'db_participant',
            'icon': 'video',
            'color': '#3b82f6',
        })

    # Assignment submissions
    as_qs = AssignmentSubmission.objects.select_related('student', 'assignment', 'assignment__classroom')
    if user:
        as_qs = as_qs.filter(student=user)
    for asub in as_qs.order_by('-submitted_at')[:limit]:
        events.append({
            'timestamp': asub.submitted_at,
            'user': asub.student,
            'username': asub.student.username,
            'user_role': 'student',
            'action': ACTION_ASSIGNMENT_SUBMITTED,
            'title': f"Submitted assignment '{asub.assignment.title}' ({asub.assignment.classroom.title})",
            'metadata': {'assignment_id': asub.assignment_id, 'marks': asub.marks_obtained},
            'source': 'db_assignment',
            'icon': 'file-text',
            'color': '#8b5cf6',
        })

    # Quiz submissions
    qs_qs = QuizSubmission.objects.select_related('student', 'quiz', 'quiz__classroom')
    if user:
        qs_qs = qs_qs.filter(student=user)
    for qsub in qs_qs.order_by('-submitted_at')[:limit]:
        events.append({
            'timestamp': qsub.submitted_at,
            'user': qsub.student,
            'username': qsub.student.username,
            'user_role': 'student',
            'action': ACTION_QUIZ_COMPLETED,
            'title': f"Completed quiz '{qsub.quiz.title}' ({qsub.quiz.classroom.title})",
            'metadata': {'quiz_id': qsub.quiz_id, 'marks': qsub.marks_obtained, 'time_taken': qsub.time_taken_seconds},
            'source': 'db_quiz',
            'icon': 'check-circle-2',
            'color': '#06b6d4',
        })

    # Teacher created classrooms
    if not user or (hasattr(user, 'userprofile') and user.userprofile.user_type == 'teacher'):
        from meetings.models import Classroom
        c_qs = Classroom.objects.select_related('teacher')
        if user:
            c_qs = c_qs.filter(teacher=user)
        for cr in c_qs.order_by('-created_at')[:limit]:
            events.append({
                'timestamp': cr.created_at,
                'user': cr.teacher,
                'username': cr.teacher.username,
                'user_role': 'teacher',
                'action': ACTION_TEACHER_CREATED_COURSE,
                'title': f"Teacher created course/classroom '{cr.title}' (Code: {cr.class_code})",
                'metadata': {'classroom_id': cr.id},
                'source': 'db_classroom',
                'icon': 'plus-circle',
                'color': '#f59e0b',
            })

    # Sort descending by timestamp and deduplicate similar timestamps (within 2 seconds)
    events.sort(key=lambda x: x['timestamp'] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    deduped = []
    seen = set()
    for ev in events:
        ts_str = ev['timestamp'].strftime('%Y-%m-%d %H:%M') if ev['timestamp'] else ''
        key = (ev['username'], ev['action'], ts_str, ev['title'])
        if key not in seen:
            seen.add(key)
            deduped.append(ev)
            if len(deduped) >= limit:
                break

    return deduped


def _get_action_icon(action):
    icons = {
        ACTION_USER_REGISTERED: 'user-plus',
        ACTION_LOGIN: 'log-in',
        ACTION_LOGOUT: 'log-out',
        ACTION_COURSE_ENROLLED: 'school',
        ACTION_CLASS_JOINED: 'video',
        ACTION_CLASS_LEFT: 'video-off',
        ACTION_ASSIGNMENT_SUBMITTED: 'file-check',
        ACTION_QUIZ_COMPLETED: 'check-circle-2',
        ACTION_TEACHER_CREATED_COURSE: 'layout-grid',
        ACTION_TEACHER_CREATED_CLASS: 'calendar',
    }
    return icons.get(action, 'activity')


def _get_action_color(action):
    colors = {
        ACTION_USER_REGISTERED: '#10b981',
        ACTION_LOGIN: '#6366f1',
        ACTION_LOGOUT: '#f43f5e',
        ACTION_COURSE_ENROLLED: '#10b981',
        ACTION_CLASS_JOINED: '#3b82f6',
        ACTION_CLASS_LEFT: '#64748b',
        ACTION_ASSIGNMENT_SUBMITTED: '#8b5cf6',
        ACTION_QUIZ_COMPLETED: '#06b6d4',
        ACTION_TEACHER_CREATED_COURSE: '#f59e0b',
        ACTION_TEACHER_CREATED_CLASS: '#ec4899',
    }
    return colors.get(action, '#6366f1')

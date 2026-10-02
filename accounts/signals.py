"""
accounts/signals.py
Django signals for Centralized Identity real-time synchronization.
Handles model updates for User, UserProfile, and StudentFaceProfile.
Uses transaction.on_commit to ensure DB safety before broadcasting WebSocket updates.
"""

import logging
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from accounts.identity import IdentityService
from accounts.models import UserProfile

User = get_user_model()
logger = logging.getLogger('accounts')


def _broadcast_identity_change(user_id):
    """
    Executes post-DB-commit cache invalidation and WebSocket group broadcasting.
    Targets private user group `user_{user_id}` and active classroom/meeting rooms.
    """
    # Invalidate cache
    IdentityService.invalidate_identity_cache(user_id)

    # Fetch updated identity dict
    updated_identity = IdentityService.get_identity_by_id(user_id)

    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    # Base payload
    event_data = {
        'type': 'send_notification',
        'data': {
            'type': 'identity_updated',
            'user_id': user_id,
            'identity': updated_identity,
        }
    }

    # 1. Broadcast to user's personal channel group
    def _send_personal():
        try:
            async_to_sync(channel_layer.group_send)(
                f"user_{user_id}",
                event_data
            )
        except Exception as e:
            logger.warning(f"Failed broadcasting identity update to user_{user_id}: {e}")

    transaction.on_commit(_send_personal)

    # 2. Broadcast to active meetings/classrooms where user is participant
    def _send_rooms():
        try:
            from meetings.models import ClassroomMembership, MeetingParticipant
            # Active classroom groups
            c_ids = ClassroomMembership.objects.filter(
                student_id=user_id, status='approved'
            ).values_list('classroom_id', flat=True)
            for cid in c_ids:
                async_to_sync(channel_layer.group_send)(
                    f"classroom_{cid}",
                    event_data
                )

            # Active meeting groups
            m_ids = MeetingParticipant.objects.filter(
                user_id=user_id, is_active=True
            ).values_list('meeting_id', flat=True)
            for mid in m_ids:
                async_to_sync(channel_layer.group_send)(
                    f"meeting_{mid}",
                    event_data
                )
        except Exception as e:
            logger.warning(f"Error broadcasting identity update to active rooms for user_{user_id}: {e}")

    transaction.on_commit(_send_rooms)


@receiver(post_save, sender=User)
def on_user_saved(sender, instance, created, **kwargs):
    """Handler for User model changes."""
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={'user_type': 'admin' if instance.is_superuser else 'student'}
        )
        try:
            from common.activity import log_lms_activity, ACTION_USER_REGISTERED
            log_lms_activity(instance, ACTION_USER_REGISTERED, title=f"User @{instance.username} registered account")
        except Exception as e:
            logger.warning(f"Error logging registration activity: {e}")

    user_id = instance.id
    transaction.on_commit(lambda: _broadcast_identity_change(user_id))


from django.contrib.auth.signals import user_logged_in, user_logged_out

@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    """Handler for user authentication logins."""
    try:
        from common.activity import log_lms_activity, ACTION_LOGIN
        log_lms_activity(user, ACTION_LOGIN, title=f"User @{user.username} logged into LMS", request=request)
    except Exception as e:
        logger.warning(f"Error logging login activity: {e}")


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    """Handler for user authentication logouts."""
    try:
        if user:
            from common.activity import log_lms_activity, ACTION_LOGOUT
            log_lms_activity(user, ACTION_LOGOUT, title=f"User @{user.username} logged out of LMS", request=request)
    except Exception as e:
        logger.warning(f"Error logging logout activity: {e}")


@receiver(post_save, sender=UserProfile)
def on_user_profile_saved(sender, instance, **kwargs):
    """Handler for UserProfile model changes."""
    user_id = instance.user_id
    transaction.on_commit(lambda: _broadcast_identity_change(user_id))


# Biometric Face Profile Signal Connection
try:
    from attendance.models import StudentFaceProfile

    @receiver(post_save, sender=StudentFaceProfile)
    @receiver(post_delete, sender=StudentFaceProfile)
    def on_face_profile_changed(sender, instance, **kwargs):
        """Handler for StudentFaceProfile changes."""
        user_id = instance.student_id
        transaction.on_commit(lambda: _broadcast_identity_change(user_id))
except Exception:
    pass


# LMS Academic Activity Signals (Classrooms, Meetings, Enrollments, Submissions)
try:
    from meetings.models import Classroom, Meeting, ClassroomMembership

    @receiver(post_save, sender=Classroom)
    def on_classroom_saved(sender, instance, created, **kwargs):
        if created and instance.teacher:
            try:
                from common.activity import log_lms_activity, ACTION_TEACHER_CREATED_COURSE
                log_lms_activity(
                    instance.teacher,
                    ACTION_TEACHER_CREATED_COURSE,
                    title=f"Created course/classroom '{instance.title}'",
                    metadata={'classroom_id': instance.id, 'class_code': instance.class_code}
                )
            except Exception:
                pass

    @receiver(post_save, sender=Meeting)
    def on_meeting_saved(sender, instance, created, **kwargs):
        if created and instance.teacher:
            try:
                from common.activity import log_lms_activity, ACTION_TEACHER_CREATED_CLASS
                log_lms_activity(
                    instance.teacher,
                    ACTION_TEACHER_CREATED_CLASS,
                    title=f"Scheduled class/meeting '{instance.title}'",
                    metadata={'meeting_id': instance.id, 'meeting_code': instance.meeting_code}
                )
            except Exception:
                pass

    @receiver(post_save, sender=ClassroomMembership)
    def on_membership_saved(sender, instance, created, **kwargs):
        if (created or instance.status == 'approved') and instance.student:
            try:
                from common.activity import log_lms_activity, ACTION_COURSE_ENROLLED
                log_lms_activity(
                    instance.student,
                    ACTION_COURSE_ENROLLED,
                    title=f"Enrolled in '{instance.classroom.title}'",
                    metadata={'classroom_id': instance.classroom_id, 'status': instance.status}
                )
            except Exception:
                pass
except Exception:
    pass


try:
    from assignments.models import AssignmentSubmission, QuizSubmission

    @receiver(post_save, sender=AssignmentSubmission)
    def on_assignment_submission_saved(sender, instance, created, **kwargs):
        if created and instance.student:
            try:
                from common.activity import log_lms_activity, ACTION_ASSIGNMENT_SUBMITTED
                log_lms_activity(
                    instance.student,
                    ACTION_ASSIGNMENT_SUBMITTED,
                    title=f"Submitted assignment '{instance.assignment.title}'",
                    metadata={'assignment_id': instance.assignment_id}
                )
            except Exception:
                pass

    @receiver(post_save, sender=QuizSubmission)
    def on_quiz_submission_saved(sender, instance, created, **kwargs):
        if created and instance.student:
            try:
                from common.activity import log_lms_activity, ACTION_QUIZ_COMPLETED
                log_lms_activity(
                    instance.student,
                    ACTION_QUIZ_COMPLETED,
                    title=f"Completed quiz '{instance.quiz.title}'",
                    metadata={'quiz_id': instance.quiz_id, 'marks': instance.marks_obtained}
                )
            except Exception:
                pass
except Exception:
    pass


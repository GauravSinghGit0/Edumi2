"""
Campus announcement delivery service.
Resolves targeted recipient cohorts, creates persistent notifications,
and broadcasts realtime events over WebSockets.
"""
import logging
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from accounts.notification_models import Notification
from common.models import Announcement

logger = logging.getLogger(__name__)
User = get_user_model()


def resolve_announcement_recipients(announcement):
    """
    Resolve recipient User QuerySet based on announcement audience specification.
    Supports:
      - 'all': All active users
      - 'students': Active users with student profile
      - 'teachers': Active users with teacher profile
      - 'course': Active students enrolled in the classroom + classroom instructor
      - 'department': Active users belonging to specified department
    """
    audience = announcement.audience
    target_id = announcement.target_id

    if audience == Announcement.AUDIENCE_STUDENTS:
        return User.objects.filter(is_active=True, userprofile__user_type='student')

    elif audience == Announcement.AUDIENCE_TEACHERS:
        return User.objects.filter(is_active=True, userprofile__user_type='teacher')

    elif audience == Announcement.AUDIENCE_COURSE:
        try:
            from academics.models import ClassroomMembership, Classroom
            student_ids = list(ClassroomMembership.objects.filter(
                classroom_id=target_id,
                status='approved'
            ).values_list('student_id', flat=True))

            teacher_id = Classroom.objects.filter(id=target_id).values_list('teacher_id', flat=True).first()
            if teacher_id and teacher_id not in student_ids:
                student_ids.append(teacher_id)

            return User.objects.filter(id__in=student_ids, is_active=True)
        except Exception as e:
            logger.error(f"Error resolving classroom recipients for course ID {target_id}: {e}")
            return User.objects.none()

    elif audience == Announcement.AUDIENCE_DEPARTMENT:
        if not target_id:
            return User.objects.none()
        return User.objects.filter(
            is_active=True,
            userprofile__department__iexact=target_id
        )

    else:  # Announcement.AUDIENCE_ALL
        return User.objects.filter(is_active=True)


def deliver_announcement(announcement, sender=None):
    """
    Delivers an announcement to resolved audience members:
    1. Bulk creates Notification entries in the database.
    2. Broadcasts realtime notification payload via Channels WebSocket layer.
    3. Updates announcement delivery metadata (is_sent, sent_at, recipient_count).
    """
    recipients_qs = resolve_announcement_recipients(announcement)
    recipient_users = list(recipients_qs)

    now = timezone.now()
    if not recipient_users:
        announcement.is_sent = True
        announcement.sent_at = now
        announcement.recipient_count = 0
        announcement.save(update_fields=['is_sent', 'sent_at', 'recipient_count'])
        return 0

    notifications = [
        Notification(
            recipient=user,
            notification_type='system',
            title=announcement.title[:200],
            message=announcement.body,
            link='/notifications/',
            related_user=sender
        )
        for user in recipient_users
    ]

    with transaction.atomic():
        Notification.objects.bulk_create(notifications, batch_size=500)
        announcement.is_sent = True
        announcement.sent_at = now
        announcement.recipient_count = len(recipient_users)
        announcement.save(update_fields=['is_sent', 'sent_at', 'recipient_count'])

    # WebSocket broadcast
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            ws_payload = {
                "type": "announcement",
                "title": announcement.title,
                "message": announcement.body,
                "audience": announcement.audience,
                "sender": sender.username if sender else "Administrator",
                "sent_at": now.strftime("%Y-%m-%d %H:%M:%S")
            }

            if announcement.audience == Announcement.AUDIENCE_ALL:
                async_to_sync(channel_layer.group_send)(
                    "public_notifications",
                    {
                        "type": "send_notification",
                        "data": ws_payload
                    }
                )
            else:
                for user in recipient_users:
                    async_to_sync(channel_layer.group_send)(
                        f"user_{user.id}",
                        {
                            "type": "send_notification",
                            "data": ws_payload
                        }
                    )
    except Exception as e:
        logger.warning(f"Announcement WebSocket broadcast failed: {e}")

    return len(recipient_users)

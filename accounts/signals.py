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
    try:
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            event_data
        )
    except Exception as e:
        logger.warning(f"Failed broadcasting identity update to user_{user_id}: {e}")

    # 2. Broadcast to active meetings/classrooms where user is participant
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


@receiver(post_save, sender=User)
def on_user_saved(sender, instance, created, **kwargs):
    """Handler for User model changes."""
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={'user_type': 'admin' if instance.is_superuser else 'student'}
        )
    user_id = instance.id
    transaction.on_commit(lambda: _broadcast_identity_change(user_id))


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

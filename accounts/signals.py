"""
Signals for Centralized User Identity Management in Edumi2 LMS.
Ensures every User instance has a corresponding UserProfile and keeps roles synchronized.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserProfile

User = get_user_model()


@receiver(post_save, sender=User)
def create_or_sync_user_profile(sender, instance, created, **kwargs):
    """
    Ensure every User has a UserProfile (Single Source of Truth).
    If a new user is created, provision a UserProfile with appropriate default role.
    If an existing user is elevated to is_superuser, sync user_type to 'admin'.
    """
    if created:
        user_type = 'admin' if instance.is_superuser else 'student'
        is_verified = bool(instance.is_superuser)
        from django.utils import timezone
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                'user_type': user_type,
                'is_verified': is_verified,
                'email_verified_at': timezone.now() if is_verified else None
            }
        )
    else:
        try:
            profile = instance.userprofile
            updated_fields = []
            if instance.is_superuser and profile.user_type != 'admin':
                profile.user_type = 'admin'
                updated_fields.append('user_type')
            if instance.is_superuser and not profile.is_verified:
                from django.utils import timezone
                profile.is_verified = True
                profile.email_verified_at = timezone.now()
                updated_fields.extend(['is_verified', 'email_verified_at'])
            if updated_fields:
                profile.save(update_fields=updated_fields)
        except UserProfile.DoesNotExist:
            user_type = 'admin' if instance.is_superuser else 'student'
            is_verified = bool(instance.is_superuser)
            from django.utils import timezone
            UserProfile.objects.get_or_create(
                user=instance,
                defaults={
                    'user_type': user_type,
                    'is_verified': is_verified,
                    'email_verified_at': timezone.now() if is_verified else None
                }
            )

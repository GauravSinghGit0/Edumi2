"""
Common model mixins used across all apps
"""
from django.db import models
from django.utils import timezone
from django.conf import settings


class TimestampMixin(models.Model):
    """
    Adds created_at and updated_at fields to any model
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


class SoftDeleteMixin(models.Model):
    """
    Adds soft delete functionality to models
    """
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at'])


class ActiveStatusMixin(models.Model):
    """
    Adds is_active field for easy active/inactive toggling
    """
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True


class UserActivityLog(TimestampMixin):
    """
    Persistent audit and telemetry log for user actions, clicks, views, and system events.
    Captures full user identity, IP address, device telemetry, and interaction metrics.
    """
    EVENT_TYPES = [
        ('page_view', 'Page View'),
        ('click', 'Click Interaction'),
        ('form_submit', 'Form Submission'),
        ('media_event', 'Media Interaction'),
        ('http_request', 'HTTP API Request'),
        ('auth', 'Authentication Event'),
        ('custom', 'Custom Event'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
        db_index=True
    )
    username = models.CharField(max_length=150, blank=True, db_index=True)
    user_role = models.CharField(max_length=50, blank=True)
    session_key = models.CharField(max_length=100, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.TextField(blank=True)
    device_type = models.CharField(max_length=30, blank=True)
    browser = models.CharField(max_length=50, blank=True)
    os = models.CharField(max_length=50, blank=True)

    event_type = models.CharField(max_length=50, choices=EVENT_TYPES, db_index=True)
    event_name = models.CharField(max_length=100, db_index=True)
    page_url = models.TextField(blank=True)
    page_title = models.CharField(max_length=255, blank=True)
    target_element = models.CharField(max_length=255, blank=True)
    target_text = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_type', 'created_at']),
            models.Index(fields=['username', 'created_at']),
            models.Index(fields=['ip_address', 'created_at']),
        ]

    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {self.username or 'anon'} - {self.event_name} ({self.ip_address})"


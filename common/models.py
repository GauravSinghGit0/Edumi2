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


class AdminAuditTrailQuerySet(models.QuerySet):
    def update(self, **kwargs):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("AdminAuditTrail records are immutable and append-only.")

    def delete(self):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("AdminAuditTrail records are append-only and cannot be deleted.")


class AdminAuditTrail(models.Model):
    """
    Immutable, append-only security and administrative audit trail.
    Records every governance, access control, user modification, course management,
    and bulk action executed by administrators.
    """
    ACTION_USER_CREATED = 'USER_CREATED'
    ACTION_USER_UPDATED = 'USER_UPDATED'
    ACTION_USER_SUSPENDED = 'USER_SUSPENDED'
    ACTION_USER_ACTIVATED = 'USER_ACTIVATED'
    ACTION_USER_DELETED = 'USER_DELETED'
    ACTION_ROLE_CHANGED = 'ROLE_CHANGED'
    ACTION_PASSWORD_RESET = 'PASSWORD_RESET'
    ACTION_CLASSROOM_CREATED = 'CLASSROOM_CREATED'
    ACTION_CLASSROOM_ARCHIVED = 'CLASSROOM_ARCHIVED'
    ACTION_ENROLLMENT_APPROVED = 'ENROLLMENT_APPROVED'
    ACTION_ENROLLMENT_REJECTED = 'ENROLLMENT_REJECTED'
    ACTION_DATA_EXPORTED = 'DATA_EXPORTED'
    ACTION_SETTINGS_CHANGED = 'SETTINGS_CHANGED'
    ACTION_BULK_ACTION = 'BULK_ACTION'

    ACTION_TYPE_CHOICES = [
        (ACTION_USER_CREATED, 'User Created'),
        (ACTION_USER_UPDATED, 'User Updated'),
        (ACTION_USER_SUSPENDED, 'User Suspended'),
        (ACTION_USER_ACTIVATED, 'User Activated'),
        (ACTION_USER_DELETED, 'User Deleted'),
        (ACTION_ROLE_CHANGED, 'Role Changed'),
        (ACTION_PASSWORD_RESET, 'Password Reset'),
        (ACTION_CLASSROOM_CREATED, 'Classroom Created'),
        (ACTION_CLASSROOM_ARCHIVED, 'Classroom Archived'),
        (ACTION_ENROLLMENT_APPROVED, 'Enrollment Approved'),
        (ACTION_ENROLLMENT_REJECTED, 'Enrollment Rejected'),
        (ACTION_DATA_EXPORTED, 'Data Exported'),
        (ACTION_SETTINGS_CHANGED, 'Settings Changed'),
        (ACTION_BULK_ACTION, 'Bulk Action'),
    ]

    timestamp = models.DateTimeField(default=timezone.now, db_index=True, editable=False)
    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admin_audit_trail_entries',
        db_index=True
    )
    action_type = models.CharField(max_length=50, choices=ACTION_TYPE_CHOICES, db_index=True)
    target_type = models.CharField(max_length=100, blank=True, db_index=True)
    target_id = models.CharField(max_length=100, blank=True, db_index=True)
    target_label = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.TextField(blank=True)
    changes_json = models.JSONField(default=dict, blank=True)

    objects = AdminAuditTrailQuerySet.as_manager()

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Admin Audit Trail'
        verbose_name_plural = 'Admin Audit Trails'
        indexes = [
            models.Index(fields=['action_type', 'timestamp']),
            models.Index(fields=['target_type', 'target_id']),
            models.Index(fields=['admin_user', 'timestamp']),
        ]

    def save(self, *args, **kwargs):
        if self.pk and AdminAuditTrail.objects.filter(pk=self.pk).exists():
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("AdminAuditTrail records are immutable and append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("AdminAuditTrail records are append-only and cannot be deleted.")

    def __str__(self):
        admin_name = self.admin_user.username if self.admin_user else "System"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {admin_name} -> {self.action_type} on {self.target_type} ({self.target_label})"


class Announcement(TimestampMixin, SoftDeleteMixin, models.Model):
    """Campus-wide or targeted broadcast announcement."""
    AUDIENCE_ALL = 'all'
    AUDIENCE_STUDENTS = 'students'
    AUDIENCE_TEACHERS = 'teachers'
    AUDIENCE_COURSE = 'course'
    AUDIENCE_DEPARTMENT = 'department'

    AUDIENCE_CHOICES = [
        (AUDIENCE_ALL, 'All Users'),
        (AUDIENCE_STUDENTS, 'All Students'),
        (AUDIENCE_TEACHERS, 'All Teachers'),
        (AUDIENCE_COURSE, 'Specific Course'),
        (AUDIENCE_DEPARTMENT, 'Specific Department'),
    ]

    title = models.CharField(max_length=255)
    body = models.TextField()
    audience = models.CharField(max_length=50, choices=AUDIENCE_CHOICES, default=AUDIENCE_ALL, db_index=True)
    target_id = models.CharField(max_length=100, blank=True, null=True, help_text="Course ID or Department name")
    target_label = models.CharField(max_length=255, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_announcements'
    )
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_sent = models.BooleanField(default=False, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_sent', 'scheduled_at']),
            models.Index(fields=['audience', '-created_at']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_audience_display()})"


class SiteSetting(models.Model):
    """
    Centralized key-value platform configuration stored with section grouping and caching.
    Supports Institution, Academic, Attendance, Security, and Email/SMTP settings.
    """
    SECTION_CHOICES = [
        ('institution', 'Institution'),
        ('academic', 'Academic'),
        ('attendance', 'Attendance'),
        ('security', 'Security'),
        ('email', 'Email / SMTP'),
    ]

    key = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.JSONField(default=dict)
    section = models.CharField(max_length=50, choices=SECTION_CHOICES, default='institution', db_index=True)
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_site_settings'
    )

    class Meta:
        ordering = ['section', 'key']
        verbose_name = 'Site Setting'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return f"[{self.section}] {self.key}"

    @classmethod
    def get_setting(cls, key, default=None):
        from django.core.cache import cache
        cache_key = f"site_setting_{key}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val
        try:
            obj = cls.objects.filter(key=key).first()
            if obj:
                val = obj.value
                cache.set(cache_key, val, timeout=300)
                return val
        except Exception:
            pass
        return default

    @classmethod
    def set_setting(cls, key, value, section='institution', description='', user=None):
        from django.core.cache import cache
        obj, created = cls.objects.get_or_create(
            key=key,
            defaults={'section': section, 'value': value, 'description': description, 'updated_by': user}
        )
        if not created:
            obj.value = value
            obj.section = section
            if description:
                obj.description = description
            if user:
                obj.updated_by = user
            obj.save()
        cache.set(f"site_setting_{key}", value, timeout=300)
        cache.delete(f"site_settings_section_{section}")
        return obj

    @classmethod
    def get_section(cls, section, defaults=None):
        from django.core.cache import cache
        cache_key = f"site_settings_section_{section}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        res = dict(defaults or {})
        try:
            qs = cls.objects.filter(section=section)
            for item in qs:
                res[item.key] = item.value
            cache.set(cache_key, res, timeout=300)
        except Exception:
            pass
        return res


def log_admin_action(*args, **kwargs):
    from common.activity import log_admin_action as _impl
    return _impl(*args, **kwargs)


class AdminRole(TimestampMixin, models.Model):
    """
    Granular role-based access control (RBAC) model for administrators.
    Replaces binary admin check with configurable permission flags.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default='')
    is_system_role = models.BooleanField(default=False, help_text="Built-in system roles cannot be deleted")

    # Permission flags
    manage_users = models.BooleanField(default=False, help_text="Create, edit, suspend, import, and delete users")
    manage_courses = models.BooleanField(default=False, help_text="Create, edit, archive courses, and approve enrollments")
    manage_sessions = models.BooleanField(default=False, help_text="Schedule meetings, view past sessions, and monitor/force-end live rooms")
    view_audit = models.BooleanField(default=False, help_text="View security audit logs, activity feeds, and system telemetry")
    manage_settings = models.BooleanField(default=False, help_text="Configure institution, security, attendance, and email settings, and post announcements")
    manage_cameras = models.BooleanField(default=False, help_text="Manage classroom cameras, RTSP streams, and media library")
    export_data = models.BooleanField(default=False, help_text="Export CSV/PDF reports and user/course datasets")

    class Meta:
        ordering = ['name']
        verbose_name = 'Admin Role'
        verbose_name_plural = 'Admin Roles'

    def __str__(self):
        return self.name

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'is_system_role': self.is_system_role,
            'manage_users': self.manage_users,
            'manage_courses': self.manage_courses,
            'manage_sessions': self.manage_sessions,
            'view_audit': self.view_audit,
            'manage_settings': self.manage_settings,
            'manage_cameras': self.manage_cameras,
            'export_data': self.export_data,
        }

    @classmethod
    def seed_default_roles(cls):
        """Seed the 4 default system roles if they do not exist."""
        roles = {
            'Super Admin': {
                'description': 'Full unrestricted administrative access across the entire Edumi platform',
                'manage_users': True,
                'manage_courses': True,
                'manage_sessions': True,
                'view_audit': True,
                'manage_settings': True,
                'manage_cameras': True,
                'export_data': True,
            },
            'Academic Admin': {
                'description': 'Manage courses, syllabus, curriculum, sessions, and academic exports',
                'manage_users': False,
                'manage_courses': True,
                'manage_sessions': True,
                'view_audit': False,
                'manage_settings': False,
                'manage_cameras': False,
                'export_data': True,
            },
            'Attendance Auditor': {
                'description': 'Audit logs, compliance reports, biometric logs, and telemetry data export',
                'manage_users': False,
                'manage_courses': False,
                'manage_sessions': False,
                'view_audit': True,
                'manage_settings': False,
                'manage_cameras': False,
                'export_data': True,
            },
            'IT Admin': {
                'description': 'Infrastructure control, camera fleet, RTSP gateways, system health, and technical settings',
                'manage_users': False,
                'manage_courses': False,
                'manage_sessions': False,
                'view_audit': True,
                'manage_settings': True,
                'manage_cameras': True,
                'export_data': False,
            },
        }
        created_or_updated = []
        for name, perms in roles.items():
            role, created = cls.objects.get_or_create(
                name=name,
                defaults={'is_system_role': True, **perms}
            )
            created_or_updated.append(role)
        return created_or_updated





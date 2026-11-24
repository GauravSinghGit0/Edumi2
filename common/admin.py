from django.contrib import admin
from .models import UserActivityLog, AdminAuditTrail, Announcement, SiteSetting, AdminRole


@admin.register(AdminAuditTrail)
class AdminAuditTrailAdmin(admin.ModelAdmin):
    list_display = (
        'timestamp',
        'admin_user',
        'action_type',
        'target_type',
        'target_label',
        'target_id',
        'ip_address'
    )
    list_filter = (
        'action_type',
        'target_type',
        'timestamp'
    )
    search_fields = (
        'admin_user__username',
        'target_label',
        'target_id',
        'ip_address',
        'action_type'
    )
    readonly_fields = [f.name for f in AdminAuditTrail._meta.fields]
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False  # Append-only: created exclusively via log_admin_action()

    def has_change_permission(self, request, obj=None):
        return False  # Append-only: immutable records

    def has_delete_permission(self, request, obj=None):
        return False  # Append-only: cannot be deleted from admin


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'username',
        'user_role',
        'event_type',
        'event_name',
        'ip_address',
        'device_type',
        'browser',
        'target_element',
        'target_text'
    )
    list_filter = (
        'event_type',
        'user_role',
        'device_type',
        'browser',
        'created_at'
    )
    search_fields = (
        'username',
        'ip_address',
        'event_name',
        'page_url',
        'target_text',
        'target_element',
        'session_key'
    )
    readonly_fields = [f.name for f in UserActivityLog._meta.fields]
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False  # Telemetry logs are append-only via the system

    def has_change_permission(self, request, obj=None):
        return False  # Prevent editing logs

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # Only superadmins can delete logs


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'audience', 'target_label', 'is_sent', 'scheduled_at', 'sent_at', 'recipient_count', 'created_by')
    list_filter = ('audience', 'is_sent', 'created_at')
    search_fields = ('title', 'body', 'target_label', 'created_by__username')
    date_hierarchy = 'created_at'


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'section', 'description', 'updated_at', 'updated_by')
    list_filter = ('section', 'updated_at')
    search_fields = ('key', 'description')
    ordering = ('section', 'key')


@admin.register(AdminRole)
class AdminRoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_system_role', 'manage_users', 'manage_courses', 'manage_sessions', 'view_audit', 'manage_settings', 'manage_cameras', 'export_data')
    list_filter = ('is_system_role',)
    search_fields = ('name', 'description')


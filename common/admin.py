from django.contrib import admin
from .models import UserActivityLog


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

from django.contrib import admin
from .models import Camera, CameraPermission, HeadCountLog, HeadCountSession

@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ('name', 'ip_address', 'port', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'ip_address')

@admin.register(CameraPermission)
class CameraPermissionAdmin(admin.ModelAdmin):
    list_display = ('camera', 'teacher', 'granted_by', 'granted_at')
    list_filter = ('granted_at',)
    search_fields = ('camera__name', 'teacher__username')
    raw_id_fields = ('camera', 'teacher', 'granted_by')

@admin.register(HeadCountLog)
class HeadCountLogAdmin(admin.ModelAdmin):
    list_display = ('camera_name', 'camera_type', 'head_count', 'confidence_score', 'date', 'hour', 'classroom')
    list_filter = ('camera_type', 'date', 'hour', 'classroom')
    search_fields = ('camera_name',)
    readonly_fields = ('timestamp', 'date', 'hour')
    raw_id_fields = ('classroom', 'recorded_by')
    date_hierarchy = 'date'

@admin.register(HeadCountSession)
class HeadCountSessionAdmin(admin.ModelAdmin):
    list_display = ('camera_name', 'camera_type', 'status', 'started_by', 'started_at', 'total_captures', 'average_head_count')
    list_filter = ('status', 'camera_type', 'started_at')
    search_fields = ('camera_name',)
    readonly_fields = ('started_at', 'stopped_at')
    raw_id_fields = ('classroom', 'started_by')
    date_hierarchy = 'started_at'

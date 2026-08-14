from django.contrib import admin
from .models import MobileCamera, MobileCameraPermission


@admin.register(MobileCamera)
class MobileCameraAdmin(admin.ModelAdmin):
    list_display = ('name', 'camera_type', 'ip_address', 'port', 'is_active', 'created_at')
    list_filter = ('camera_type', 'is_active', 'created_at')
    search_fields = ('name', 'ip_address')
    list_editable = ('is_active',)


@admin.register(MobileCameraPermission)
class MobileCameraPermissionAdmin(admin.ModelAdmin):
    list_display = ('mobile_camera', 'teacher', 'granted_by', 'granted_at')
    list_filter = ('granted_at',)
    search_fields = ('mobile_camera__name', 'teacher__username')
    raw_id_fields = ('mobile_camera', 'teacher', 'granted_by')

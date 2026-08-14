from django.contrib import admin
from .models import (
    StudentFaceProfile, ClassSchedule, AttendanceRecord,
    FaceRecognitionLog, AttendanceSettings
)


@admin.register(StudentFaceProfile)
class StudentFaceProfileAdmin(admin.ModelAdmin):
    list_display  = ('student', 'is_active', 'face_quality_score', 'face_photo', 'created_at', 'last_verified_at')
    list_filter   = ('is_active',)
    search_fields = ('student__username', 'student__email')
    readonly_fields = ('face_embedding_encrypted', 'embedding_checksum',
                       'created_at', 'updated_at', 'last_verified_at', 'face_photo_preview')

    def face_photo_preview(self, obj):
        if obj.face_photo:
            from django.utils.html import format_html
            return format_html('<img src="{}" style="max-height:200px;border-radius:8px;">', obj.face_photo.url)
        return "No photo"
    face_photo_preview.short_description = "Face Photo"

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(ClassSchedule)
class ClassScheduleAdmin(admin.ModelAdmin):
    list_display  = ('classroom', 'day_of_week', 'start_time', 'end_time', 'is_active')
    list_filter   = ('is_active', 'day_of_week')
    search_fields = ('classroom__title',)


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display  = ('student', 'classroom', 'meeting', 'date', 'status',
                     'verification_method', 'face_match_confidence')
    list_filter   = ('status', 'verification_method', 'date')
    search_fields = ('student__username', 'classroom__title')
    readonly_fields = ('face_match_confidence', 'face_verified_at', 'created_at', 'updated_at')


@admin.register(FaceRecognitionLog)
class FaceRecognitionLogAdmin(admin.ModelAdmin):
    list_display  = ('student', 'meeting', 'event_type', 'confidence_score', 'timestamp')
    list_filter   = ('event_type',)
    search_fields = ('student__username',)
    readonly_fields = ('timestamp',)
    # Read-only audit log — no add/change permission
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False


@admin.register(AttendanceSettings)
class AttendanceSettingsAdmin(admin.ModelAdmin):
    list_display = ('classroom', 'face_recognition_enabled', 'confidence_threshold',
                    'presence_duration_seconds', 'recognition_interval_seconds')

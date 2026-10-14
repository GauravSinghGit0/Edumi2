from django.contrib import admin
from .models import Meeting, MeetingParticipant, Classroom, ClassroomMembership, StudyMaterial, MaterialUnit


class ClassroomMembershipInline(admin.TabularInline):
    model = ClassroomMembership
    extra = 0
    raw_id_fields = ('student', 'approved_by')


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ('title', 'class_code', 'teacher', 'auto_approve', 'is_active', 'created_at')
    list_filter = ('is_active', 'auto_approve', 'created_at')
    search_fields = ('title', 'class_code', 'teacher__username', 'teacher__email')
    raw_id_fields = ('teacher',)
    inlines = (ClassroomMembershipInline,)


@admin.register(ClassroomMembership)
class ClassroomMembershipAdmin(admin.ModelAdmin):
    list_display = ('student', 'classroom', 'status', 'requested_at', 'approved_by')
    list_filter = ('status', 'requested_at')
    search_fields = ('student__username', 'student__email', 'classroom__title', 'classroom__class_code')
    raw_id_fields = ('student', 'classroom', 'approved_by')


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ['title', 'teacher', 'classroom', 'meeting_code', 'scheduled_time', 'status', 'sleep_status']
    list_filter = ['status', 'meeting_type', 'scheduled_time']
    search_fields = ['title', 'meeting_code', 'teacher__username']
    raw_id_fields = ('teacher', 'classroom')


@admin.register(MeetingParticipant)
class MeetingParticipantAdmin(admin.ModelAdmin):
    list_display = ['user', 'meeting', 'joined_at', 'is_active', 'total_duration_seconds']
    list_filter = ['is_active', 'joined_at']
    raw_id_fields = ('user', 'meeting')


@admin.register(MaterialUnit)
class MaterialUnitAdmin(admin.ModelAdmin):
    list_display = ('title', 'classroom', 'order', 'created_at')
    list_filter = ('classroom', 'created_at')
    search_fields = ('title', 'classroom__title')


@admin.register(StudyMaterial)
class StudyMaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'classroom', 'material_type', 'file_size_bytes', 'uploaded_by', 'rag_indexed', 'is_published', 'created_at')
    list_filter = ('material_type', 'rag_indexed', 'is_published', 'created_at')
    search_fields = ('title', 'classroom__title', 'uploaded_by__username')
    raw_id_fields = ('classroom', 'uploaded_by')


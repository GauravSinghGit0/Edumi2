from django.contrib import admin
from .models import Classroom, ClassroomMembership

@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ('class_code', 'title', 'teacher', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('class_code', 'title', 'teacher__username')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(ClassroomMembership)
class ClassroomMembershipAdmin(admin.ModelAdmin):
    list_display = ('student', 'classroom', 'status', 'requested_at')
    list_filter = ('status', 'requested_at')
    search_fields = ('student__username', 'classroom__title')

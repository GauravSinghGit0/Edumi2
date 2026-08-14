from django.contrib import admin
from .models import VideoProject, EditOperation


class EditOperationInline(admin.TabularInline):
    model = EditOperation
    extra = 0
    readonly_fields = ["operation_type", "description", "created_at"]


@admin.register(VideoProject)
class VideoProjectAdmin(admin.ModelAdmin):
    list_display = ["title", "owner", "status", "duration_seconds", "created_at"]
    list_filter = ["status"]
    search_fields = ["title", "owner__username"]
    inlines = [EditOperationInline]


@admin.register(EditOperation)
class EditOperationAdmin(admin.ModelAdmin):
    list_display = ["project", "operation_type", "created_at"]
    list_filter = ["operation_type"]

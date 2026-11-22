from django.contrib import admin
from .models import RagSession, RagQueryLog, RagInstructorSetting


@admin.register(RagSession)
class RagSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'title', 'active_mode', 'strict_mode', 'created_at']
    list_filter = ['active_mode', 'strict_mode', 'created_at']
    search_fields = ['user__username', 'title']


@admin.register(RagQueryLog)
class RagQueryLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'mode', 'retrieved_chunks_count', 'not_found', 'created_at']
    list_filter = ['mode', 'not_found', 'created_at']
    search_fields = ['user__username', 'prompt', 'response']


@admin.register(RagInstructorSetting)
class RagInstructorSettingAdmin(admin.ModelAdmin):
    list_display = ['classroom', 'strict_material_mode', 'allow_outside_knowledge', 'updated_at']

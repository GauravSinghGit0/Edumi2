from django.contrib import admin
from .models import Meeting, MeetingParticipant

@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ['title', 'teacher', 'meeting_code', 'scheduled_time', 'status']
    list_filter = ['status', 'scheduled_time']
    search_fields = ['title', 'meeting_code', 'teacher__username']

@admin.register(MeetingParticipant)
class MeetingParticipantAdmin(admin.ModelAdmin):
    list_display = ['user', 'meeting', 'joined_at', 'is_active']
    list_filter = ['is_active', 'joined_at']

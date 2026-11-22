from django.contrib import admin
from .models import Meeting, MeetingParticipant, MeetingChat, MeetingSummary, KickedParticipant

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


@admin.register(MeetingChat)
class MeetingChatAdmin(admin.ModelAdmin):
    list_display = ['meeting', 'user', 'timestamp']
    raw_id_fields = ('meeting', 'user')


@admin.register(MeetingSummary)
class MeetingSummaryAdmin(admin.ModelAdmin):
    list_display = ['meeting', 'generated_at']
    raw_id_fields = ('meeting',)


@admin.register(KickedParticipant)
class KickedParticipantAdmin(admin.ModelAdmin):
    list_display = ['meeting', 'user', 'kicked_at', 'banned_until']
    raw_id_fields = ('meeting', 'user')

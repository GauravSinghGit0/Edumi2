from django.contrib import admin
from .models import Video, VideoQuality, VideoChunk


class VideoQualityInline(admin.TabularInline):
    model = VideoQuality
    extra = 0


class VideoChunkInline(admin.TabularInline):
    model = VideoChunk
    extra = 0


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'uploaded_by', 'uploaded_at', 'is_processed']
    list_filter = ['uploaded_at', 'is_processed']
    search_fields = ['title', 'uploaded_by__username']
    inlines = [VideoQualityInline]


@admin.register(VideoQuality)
class VideoQualityAdmin(admin.ModelAdmin):
    list_display = ['video', 'quality', 'created_at']
    list_filter = ['quality', 'created_at']
    search_fields = ['video__title']
    inlines = [VideoChunkInline]


@admin.register(VideoChunk)
class VideoChunkAdmin(admin.ModelAdmin):
    list_display = ['quality', 'chunk_number', 'start_time', 'end_time']
    list_filter = ['created_at']
    search_fields = ['quality__video__title']
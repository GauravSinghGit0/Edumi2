"""
Video models for handling video storage, multiple qualities, and chunked streaming.
"""
from uuid import uuid4
from django.db import models
from django.conf import settings
from common.validators import validate_video_file, validate_image_file


def video_upload_path(instance, filename):
    """Generate unique upload path for video files."""
    ext = filename.split('.')[-1].lower()
    return f'videos/{uuid4()}.{ext}'


def video_quality_upload_path(instance, filename):
    """Generate unique upload path for quality-specific video files."""
    ext = filename.split('.')[-1].lower()
    return f'videos/qualities/{uuid4()}.{ext}'


class Video(models.Model):
    """Main video model storing the original video and metadata."""
    
    VIDEO_QUALITY_CHOICES = [
        ('1080p', '1080p'),
        ('720p', '720p'),
        ('480p', '480p'),
        ('360p', '360p'),
    ]
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    original_file = models.FileField(upload_to=video_upload_path, validators=[validate_video_file])
    thumbnail = models.ImageField(upload_to='videos/thumbnails/', blank=True, null=True, validators=[validate_image_file])
    file_size = models.PositiveBigIntegerField(blank=True, null=True)
    duration_seconds = models.PositiveIntegerField(blank=True, null=True)
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    views_count = models.PositiveIntegerField(default=0)
    likes_count = models.PositiveIntegerField(default=0)
    
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='videos'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    is_processed = models.BooleanField(default=False)
    is_chunked = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return self.title


class VideoQuality(models.Model):
    """Model for storing different quality versions of a video."""
    
    video = models.ForeignKey(
        Video, 
        on_delete=models.CASCADE, 
        related_name='qualities'
    )
    quality = models.CharField(
        max_length=20, 
        choices=Video.VIDEO_QUALITY_CHOICES
    )
    file = models.FileField(upload_to=video_quality_upload_path)
    file_size = models.PositiveBigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('video', 'quality')
    
    def __str__(self):
        return f"{self.video.title} - {self.quality}"


class VideoChunk(models.Model):
    """Model for storing 10-second video chunks for streaming."""
    
    quality = models.ForeignKey(
        VideoQuality, 
        on_delete=models.CASCADE, 
        related_name='chunks'
    )
    chunk_number = models.PositiveIntegerField()
    start_time = models.FloatField()  # in seconds
    end_time = models.FloatField()    # in seconds
    file = models.FileField(upload_to='videos/chunks/')
    file_size = models.PositiveBigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['chunk_number']
        unique_together = ('quality', 'chunk_number')
    
    def __str__(self):
        return f"{self.quality} - Chunk {self.chunk_number}"
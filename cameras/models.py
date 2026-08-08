from django.db import models
from django.contrib.auth import get_user_model
import logging
from .ffmpeg_helpers import get_ffmpeg_binary

logger = logging.getLogger(__name__)
User = get_user_model()

class Camera(models.Model):
    CAMERA_TYPE_CHOICES = (
        ('rtsp', 'RTSP Camera'),
        ('ip_webcam', 'IP Webcam (Android)'),
        ('droidcam', 'DroidCam (iPhone)'),
    )
    
    name = models.CharField(max_length=100)
    camera_type = models.CharField(max_length=20, choices=CAMERA_TYPE_CHOICES, default='rtsp')
    ip_address = models.CharField(max_length=50)
    port = models.IntegerField(default=554)
    username = models.CharField(max_length=100, blank=True)
    password = models.CharField(max_length=100, blank=True)
    stream_path = models.CharField(max_length=200, blank=True)
    livekit_room = models.CharField(max_length=100, blank=True) # Linked LiveKit room
    is_live = models.BooleanField(default=False)
    live_teacher = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='live_cameras')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    def get_stream_url(self):
        from urllib.parse import quote
        if self.stream_path and (self.stream_path.startswith('rtsp://') or self.stream_path.startswith('http://') or self.stream_path.startswith('https://')):
            return self.stream_path

        path = self.stream_path if self.stream_path else ''
        if path and not path.startswith('/'):
            path = '/' + path

        if self.camera_type == 'rtsp':
            if self.username and self.password:
                safe_user = quote(self.username, safe='')
                safe_pass = quote(self.password, safe='')
                return f"rtsp://{safe_user}:{safe_pass}@{self.ip_address}:{self.port}{path}"
            return f"rtsp://{self.ip_address}:{self.port}{path}"
        elif self.camera_type == 'ip_webcam':
            return f"http://{self.ip_address}:{self.port}/video"
        elif self.camera_type == 'droidcam':
            return f"http://{self.ip_address}:{self.port}/mjpegfeed"
        return f"http://{self.ip_address}:{self.port}{path}" if self.ip_address else ""
    
    def get_full_rtsp_url(self):
        """Alias for compatibility with camera service"""
        return self.get_stream_url()
    
    def has_permission(self, user):
        """Check if user has permission to access this camera"""
        if user.is_superuser:
            return True
        return CameraPermission.objects.filter(camera=self, teacher=user).exists()
    
    def get_authorized_teachers(self):
        """Get all teachers with access to this camera"""
        return User.objects.filter(camerapermission__camera=self)


class CameraPermission(models.Model):
    """Permission model to grant teachers access to specific cameras"""
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'userprofile__user_type': 'teacher'})
    granted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='granted_permissions')
    granted_at = models.DateTimeField(auto_now_add=True)
    # If True, students can view this camera in meetings
    show_to_students = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('camera', 'teacher')
        verbose_name = 'Camera Permission'
        verbose_name_plural = 'Camera Permissions'
    
    def __str__(self):
        return f"{self.teacher.username} - {self.camera.name}"


def get_recording_upload_path(instance, filename):
    return f"recordings/{instance.teacher.username}/recordings/{filename}"

def get_thumbnail_upload_path(instance, filename):
    return f"recordings/{instance.teacher.username}/thumbnails/{filename}"

class CameraRecording(models.Model):
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, null=True, blank=True)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    video_file = models.FileField(upload_to=get_recording_upload_path)
    thumbnail = models.ImageField(upload_to=get_thumbnail_upload_path, blank=True)
    duration = models.DurationField(null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True) # In bytes
    is_published = models.BooleanField(default=False)
    is_chunked = models.BooleanField(default=False) # New: indicate if stored in chunks
    recording_status = models.CharField(max_length=20, choices=(
        ('recording', 'Recording'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ), default='recording')
    edit_start_time = models.FloatField(default=0.0, null=True, blank=True) # Trim start (seconds)
    edit_end_time = models.FloatField(null=True, blank=True) # Trim end (seconds)
    created_at = models.DateTimeField(auto_now_add=True)
    views_count = models.PositiveIntegerField(default=0)
    likes_count = models.PositiveIntegerField(default=0)

    def generate_chunked_thumbnail(self):
        """Generate a thumbnail for a chunked recording from its first chunk in DB"""
        import tempfile
        import subprocess
        import os
        from django.conf import settings
        
        first_chunk = self.chunks.order_by('sequence').first()
        if not first_chunk or not first_chunk.data:
            logger.warning("No chunks found for chunked thumbnail generation")
            return None
            
        with tempfile.NamedTemporaryFile(suffix='.ts', delete=False) as temp_ts:
            temp_ts.write(first_chunk.data)
            temp_ts_path = temp_ts.name
            
        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'recordings', self.teacher.username, 'thumbnails')
        os.makedirs(thumbnail_dir, exist_ok=True)
        thumbnail_filename = f'{self.id}_thumbnail.jpg'
        thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)
        
        cmd = [
            get_ffmpeg_binary(), '-y',
            '-i', temp_ts_path,
            '-vframes', '1',
            '-vf', 'scale=640:360',
            thumbnail_path
        ]
        
        try:
            logger.debug(f"Running FFmpeg for chunked thumbnail: {' '.join(cmd)}")
            subprocess.run(cmd, capture_output=True, check=True, timeout=30)
            self.thumbnail = f'recordings/{self.teacher.username}/thumbnails/{thumbnail_filename}'
            self.save()
            logger.info("Chunked thumbnail generated successfully!")
            return self.thumbnail
        except Exception as e:
            logger.error(f"Error generating chunked thumbnail: {e}")
            return None
        finally:
            if os.path.exists(temp_ts_path):
                os.remove(temp_ts_path)

    def generate_thumbnail(self, time_sec=1.0):
        """Generate a thumbnail from the video file at the given time (in seconds)"""
        import subprocess
        import os
        from django.conf import settings

        if not self.video_file or not self.video_file.path or not os.path.exists(self.video_file.path):
            logger.warning("Video file not found, skipping thumbnail generation")
            return None

        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'recordings', 'thumbnails')
        os.makedirs(thumbnail_dir, exist_ok=True)
        thumbnail_path = os.path.join(thumbnail_dir, f'{self.id}_thumbnail.jpg')
        
        # FFmpeg command to extract thumbnail
        cmd = [
            get_ffmpeg_binary(), '-y',
            '-ss', str(time_sec),
            '-i', self.video_file.path,
            '-vframes', '1',
            '-vf', 'scale=640:360',
            thumbnail_path
        ]
        
        try:
            logger.debug(f"Running FFmpeg: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, check=True, timeout=60)
            logger.debug(f"FFmpeg output: {result.stdout.decode()}")
            if result.stderr:
                logger.debug(f"FFmpeg stderr: {result.stderr.decode()}")
                
            # Save relative path
            self.thumbnail = f'recordings/thumbnails/{self.id}_thumbnail.jpg'
            self.save()
            logger.info("Thumbnail saved successfully!")
            return self.thumbnail
        except FileNotFoundError:
            logger.warning("FFmpeg not found, skipping thumbnail generation")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg timed out, skipping thumbnail generation")
            return None
        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}")
            logger.exception("Thumbnail generation exception")
            return None

    def apply_trim(self):
        """Apply trim from edit_start_time to edit_end_time and replace the original video"""
        import subprocess
        import os
        from django.conf import settings

        if not self.video_file or not self.video_file.path or not os.path.exists(self.video_file.path):
            return False

        if self.edit_start_time is None or self.edit_start_time < 0:
            self.edit_start_time = 0.0

        video_dir = os.path.join(settings.MEDIA_ROOT, 'recordings', str(self.created_at.year), str(self.created_at.month), str(self.created_at.day))
        os.makedirs(video_dir, exist_ok=True)
        trimmed_path = os.path.join(video_dir, f'{self.id}_trimmed.mp4')

        # Build FFmpeg trim command
        cmd = [get_ffmpeg_binary(), '-y', '-i', self.video_file.path]

        if self.edit_start_time is not None and self.edit_start_time > 0:
            cmd.extend(['-ss', str(self.edit_start_time)])

        if self.edit_end_time is not None and self.edit_end_time > 0:
            cmd.extend(['-to', str(self.edit_end_time)])

        cmd.extend([
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-movflags', '+faststart',
            trimmed_path
        ])

        try:
            subprocess.run(cmd, capture_output=True, check=True, timeout=300)
            
            # Backup original, then replace with trimmed
            original_path = self.video_file.path
            backup_path = f'{original_path}.bak'
            os.rename(original_path, backup_path)
            os.rename(trimmed_path, original_path)

            self.video_file = f'recordings/{self.created_at.year}/{self.created_at.month}/{self.created_at.day}/{self.id}_trimmed.mp4'
            self.save()
            self.generate_thumbnail(time_sec=1.0)

            # Delete backup if everything succeeded
            if os.path.exists(backup_path):
                os.remove(backup_path)
            return True
        except Exception as e:
            logger.error(f"Error trimming video: {e}")
            if os.path.exists(trimmed_path):
                os.remove(trimmed_path)
            return False

    def __str__(self):
        return f"{self.title} - {self.teacher.username}"

class RecordingChunk(models.Model):
    recording = models.ForeignKey(CameraRecording, on_delete=models.CASCADE, related_name='chunks')
    sequence = models.IntegerField()
    data = models.BinaryField() # The actual video data for this chunk
    duration = models.FloatField(default=10.0) # Chunk duration in seconds
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sequence']
        unique_together = ('recording', 'sequence')

    def __str__(self):
        return f"Chunk {self.sequence} for {self.recording.title}"


class HeadCountLog(models.Model):
    """Stores head count data from camera feeds for attendance tracking"""
    CAMERA_TYPE_CHOICES = (
        ('rtsp', 'RTSP Camera'),
        ('mobile', 'Mobile Camera'),
    )
    
    # Camera reference (can be RTSP or Mobile camera)
    camera_type = models.CharField(max_length=10, choices=CAMERA_TYPE_CHOICES, default='rtsp')
    camera_id = models.IntegerField()  # ID of Camera or MobileCamera
    camera_name = models.CharField(max_length=100)  # Store name for historical records
    
    # Classroom association (optional - for class-wise grouping)
    classroom = models.ForeignKey(
        'meetings.Classroom', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='head_count_logs'
    )
    
    # Count data
    head_count = models.IntegerField(default=0)
    confidence_score = models.FloatField(default=0.0)  # Average detection confidence
    
    # Timestamp for day-wise, time-wise filtering
    timestamp = models.DateTimeField(auto_now_add=True)
    date = models.DateField()  # Separate date field for easy filtering
    hour = models.IntegerField()  # Hour of the day (0-23)
    
    # Snapshot (optional - stores annotated frame with green boxes)
    snapshot = models.ImageField(upload_to='head_count_snapshots/', blank=True, null=True)
    
    # Metadata
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='head_count_records'
    )
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['date', 'camera_type', 'camera_id']),
            models.Index(fields=['classroom', 'date']),
            models.Index(fields=['hour', 'date']),
        ]
        verbose_name = 'Head Count Log'
        verbose_name_plural = 'Head Count Logs'
    
    def __str__(self):
        return f"{self.camera_name} - {self.head_count} heads @ {self.timestamp}"
    
    def save(self, *args, **kwargs):
        # Auto-populate date and hour from timestamp
        if self.timestamp:
            self.date = self.timestamp.date()
            self.hour = self.timestamp.hour
        super().save(*args, **kwargs)


class HeadCountSession(models.Model):
    """Active head counting session for a camera"""
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('stopped', 'Stopped'),
    )
    
    camera_type = models.CharField(max_length=10, choices=HeadCountLog.CAMERA_TYPE_CHOICES, default='rtsp')
    camera_id = models.IntegerField()
    camera_name = models.CharField(max_length=100)
    classroom = models.ForeignKey(
        'meetings.Classroom', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='head_count_sessions'
    )
    started_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='head_count_sessions')
    started_at = models.DateTimeField(auto_now_add=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    
    # Interval settings
    capture_interval = models.IntegerField(default=30)  # Seconds between captures
    
    # Summary stats
    total_captures = models.IntegerField(default=0)
    average_head_count = models.FloatField(default=0.0)
    max_head_count = models.IntegerField(default=0)
    min_head_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Head Count Session'
        verbose_name_plural = 'Head Count Sessions'
    
    def __str__(self):
        return f"Session for {self.camera_name} ({self.status})"

from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class MobileCamera(models.Model):
    """Mobile IP Camera model for IP Webcam (Android) and DroidCam (iPhone)"""
    
    CAMERA_TYPE_CHOICES = (
        ('ip_webcam', 'IP Webcam (Android)'),
        ('droidcam', 'DroidCam (iPhone)'),
        ('other', 'Other Mobile Camera'),
    )
    
    name = models.CharField(max_length=100)
    camera_type = models.CharField(max_length=20, choices=CAMERA_TYPE_CHOICES, default='ip_webcam')
    ip_address = models.CharField(max_length=50)
    port = models.IntegerField(default=8080)
    username = models.CharField(max_length=100, blank=True, help_text="Optional authentication username")
    password = models.CharField(max_length=100, blank=True, help_text="Optional authentication password")
    stream_path = models.CharField(max_length=200, default='/video', help_text="e.g., /video for IP Webcam, /mjpegfeed for DroidCam")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_camera_type_display()})"
    
    def get_stream_url(self):
        """Get the HTTP stream URL for mobile camera"""
        if self.username and self.password:
            return f"http://{self.username}:{self.password}@{self.ip_address}:{self.port}{self.stream_path}"
        return f"http://{self.ip_address}:{self.port}{self.stream_path}"
    
    def has_permission(self, user):
        """Check if user has permission to access this mobile camera"""
        # Admin always has access
        if user.is_superuser:
            return True
        # Check if teacher has explicit permission
        return MobileCameraPermission.objects.filter(mobile_camera=self, teacher=user).exists()
    
    def get_authorized_teachers(self):
        """Get all teachers with access to this mobile camera"""
        return User.objects.filter(mobilecamerapermission__mobile_camera=self)


class MobileCameraPermission(models.Model):
    """Permission model to grant teachers access to specific mobile cameras"""
    mobile_camera = models.ForeignKey(MobileCamera, on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'userprofile__user_type': 'teacher'})
    granted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='granted_mobile_permissions')
    granted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('mobile_camera', 'teacher')
        verbose_name = 'Mobile Camera Permission'
        verbose_name_plural = 'Mobile Camera Permissions'
    
    def __str__(self):
        return f"{self.teacher.username} - {self.mobile_camera.name}"

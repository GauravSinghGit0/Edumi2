from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class UserProfile(models.Model):
    USER_TYPE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('admin', 'Admin'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, db_index=True)
    
    # Profile Information
    bio = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    avatar_url = models.CharField(max_length=500, blank=True, null=True)
    display_name = models.CharField(max_length=100, blank=True, null=True)
    cover_photo = models.ImageField(upload_to='cover_photos/', blank=True, null=True)
    headline = models.CharField(max_length=255, blank=True, null=True)
    cgpa = models.CharField(max_length=10, blank=True, null=True)
    subjects = models.TextField(blank=True, null=True)
    github = models.URLField(blank=True, null=True)
    availability_weekday = models.CharField(max_length=100, blank=True, null=True, default="09:00 – 17:00")
    availability_friday = models.CharField(max_length=100, blank=True, null=True, default="10:00 – 14:00")
    
    # Student Specific
    student_id = models.CharField(max_length=20, blank=True, null=True, db_index=True, verbose_name="Roll Number")
    roll_number = models.CharField(max_length=50, blank=True, null=True)
    branch = models.CharField(max_length=100, blank=True, null=True)
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    grade = models.CharField(max_length=20, blank=True, null=True)
    enrollment_date = models.DateField(blank=True, null=True)
    
    # Teacher Specific
    employee_id = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    specialization = models.CharField(max_length=200, blank=True, null=True)
    join_date = models.DateField(blank=True, null=True)
    
    # Social Links
    linkedin = models.URLField(blank=True, null=True)
    twitter = models.URLField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(null=True, blank=True, help_text='Timestamp of last activity')
    
    def __str__(self):
        return f"{self.user.username} - {self.user_type}"
    
    def get_display_name(self):
        if self.display_name:
            return self.display_name
        if self.user.first_name and self.user.last_name:
            return f"{self.user.first_name} {self.user.last_name}"
        return self.user.username
    
    def get_profile_picture_url(self):
        if self.profile_picture:
            try:
                if hasattr(self.profile_picture, 'url') and self.profile_picture.name:
                    return self.profile_picture.url
            except Exception:
                pass
        if self.avatar_url:
            return self.avatar_url
        display_name = self.get_display_name() or self.user.username
        import urllib.parse
        return f"https://ui-avatars.com/api/?name={urllib.parse.quote(display_name)}&background=1877f2&color=fff&size=200"


class StudentPhoto(models.Model):
    """
    Admin-only photo uploaded by a student.
    Visible in the frontend upload form but the image itself is hidden from everyone except admins.
    """
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='student_photos')
    photo = models.ImageField(upload_to='student_photos/')
    caption = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.student.username} — {self.uploaded_at:%Y-%m-%d}"


class UserAchievement(models.Model):
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='achievements')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    date_str = models.CharField(max_length=100, blank=True, null=True)
    icon_type = models.CharField(max_length=50, default='award')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.profile.user.username} - {self.title}"


# Import messaging models
from .messaging_models import Conversation, Message

# Import notification model
from .notification_models import Notification

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
    
    # Verification & Security
    is_verified = models.BooleanField(default=False, db_index=True, help_text='Designates whether user has verified their email address.')
    email_verified_at = models.DateTimeField(null=True, blank=True, help_text='Timestamp of email verification')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(null=True, blank=True, help_text='Timestamp of last activity')
    
    def verify_email(self):
        """Mark profile email as verified."""
        from django.utils import timezone
        self.is_verified = True
        self.email_verified_at = timezone.now()
        self.save(update_fields=['is_verified', 'email_verified_at'])

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

    @property
    def role(self):
        return self.user_type

    @property
    def is_student_role(self):
        return self.user_type == 'student'

    @property
    def is_teacher_role(self):
        return self.user_type == 'teacher'

    @property
    def is_admin_role(self):
        return self.user_type == 'admin' or (self.user and self.user.is_superuser)

    def get_identity_dict(self):
        """Standardized serializable identity representation across LMS modules."""
        return {
            'user_id': self.user_id,
            'username': self.user.username,
            'display_name': self.get_display_name(),
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'email': self.user.email,
            'role': self.user_type,
            'is_verified': bool(self.is_verified),
            'is_superuser': bool(self.user.is_superuser),
            'pfp_url': self.get_profile_picture_url(),
            'phone': self.phone or self.contact_number or '',
            'bio': self.bio or '',
            'headline': self.headline or '',
            'student_id': self.student_id or self.roll_number or '',
            'roll_number': self.roll_number or self.student_id or '',
            'branch': self.branch or '',
            'grade': self.grade or '',
            'employee_id': self.employee_id or '',
            'department': self.department or '',
            'specialization': self.specialization or '',
        }

    def get_dashboard_url(self):
        """Returns the appropriate landing dashboard URL for this user."""
        if self.user.is_superuser or self.user_type == 'admin':
            return '/admin/'
        elif self.user_type == 'teacher':
            return '/teacher-dashboard/'
        elif self.user_type == 'student':
            return '/student-dashboard/'
        return '/home/'


class EmailVerificationOTP(models.Model):
    """
    Enterprise-grade database-backed OTP persistence for email verification.
    Stores SHA-256 hashed 6-digit codes with TTL, single-use status, and attempt throttling.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verification_otps', db_index=True)
    otp_hash = models.CharField(max_length=128, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    is_used = models.BooleanField(default=False, db_index=True)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_used', 'expires_at']),
        ]

    def __str__(self):
        return f"OTP for {self.user.username} (used={self.is_used})"


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

__all__ = [
    'UserProfile',
    'EmailVerificationOTP',
    'UserAchievement',
    'Conversation',
    'Message',
    'Notification',
]

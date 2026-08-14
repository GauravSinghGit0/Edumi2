from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import random
import string

User = get_user_model()

class Classroom(models.Model):
    """Virtual classroom that persists across multiple meeting sessions"""
    class_code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    password = models.CharField(max_length=128)  # Will be hashed
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_classrooms')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title} ({self.class_code})"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Classroom'
        verbose_name_plural = 'Classrooms'
    
    def get_approved_students(self):
        """Get all approved students in this classroom"""
        return User.objects.filter(
            classroom_memberships__classroom=self,
            classroom_memberships__status='approved'
        )
    
    def get_approved_memberships(self):
        """Get all approved memberships (includes membership objects)"""
        return self.memberships.filter(status='approved').select_related('student')
    
    def get_pending_requests(self):
        """Get all pending join requests"""
        return self.memberships.filter(status='pending').select_related('student')
    
    def has_active_meeting(self):
        """Check if classroom has an active meeting"""
        return self.meetings.filter(status='live').exists()
    
    def get_active_meeting(self):
        """Get the current active meeting if any"""
        return self.meetings.filter(status='live').first()

class ClassroomMembership(models.Model):
    """Tracks student membership and approval status in classrooms"""
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('denied', 'Denied'),
        ('removed', 'Removed'),
        ('left', 'Left'),
    ]
    
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='memberships')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='classroom_memberships')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_memberships')
    
    class Meta:
        unique_together = ['classroom', 'student']
        ordering = ['-requested_at']
        verbose_name = 'Classroom Membership'
        verbose_name_plural = 'Classroom Memberships'
    
    def __str__(self):
        return f"{self.student.username} - {self.classroom.title} ({self.status})"

class Meeting(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('live', 'Live'),
        ('ended', 'Ended'),
        ('cancelled', 'Cancelled'),
    ]
    
    SLEEP_STATUS_CHOICES = [
        ('active', 'Active'),
        ('sleeping', 'Sleeping'),
    ]
    
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='meetings', null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hosted_meetings')
    meeting_type = models.CharField(max_length=20, choices=[('classroom', 'Classroom'), ('temporary', 'Temporary')], default='temporary')
    meeting_code = models.CharField(max_length=20, unique=True)
    scheduled_time = models.DateTimeField()
    duration_minutes = models.IntegerField(default=60)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled', db_index=True)
    sleep_status = models.CharField(max_length=20, choices=SLEEP_STATUS_CHOICES, default='active', db_index=True)
    max_participants = models.IntegerField(default=100)
    allow_screen_share = models.BooleanField(default=True)
    allow_chat = models.BooleanField(default=True)
    record_meeting = models.BooleanField(default=False)
    global_mute = models.BooleanField(default=False)
    global_camera_off = models.BooleanField(default=False)
    global_screenshare_off = models.BooleanField(default=False)
    # Controls whether students can see the teacher's camera feed
    student_can_view_camera = models.BooleanField(default=True)
    # Controls whether students can see the teacher's screen share
    student_can_view_screenshare = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.title} - {self.meeting_code}"
    
    class Meta:
        ordering = ['-scheduled_time']
        constraints = [
            # No two active/live/scheduled meetings with the same title in the same classroom
            models.UniqueConstraint(
                fields=['classroom', 'title'],
                condition=models.Q(status__in=['scheduled', 'live']),
                name='unique_active_meeting_title_per_classroom'
            ),
            # No two active/live/scheduled standalone meetings with the same title per teacher
            models.UniqueConstraint(
                fields=['teacher', 'title'],
                condition=models.Q(status__in=['scheduled', 'live'], classroom__isnull=True),
                name='unique_active_standalone_meeting_title_per_teacher'
            ),
        ]
    
    def is_sleeping(self):
        """Check if meeting is in sleep mode"""
        return self.sleep_status == 'sleeping'
    
    def can_join(self):
        """Check if users can join this meeting"""
        return self.status == 'live' and self.sleep_status == 'active'
    
    def put_to_sleep(self):
        """Put meeting to sleep mode"""
        self.sleep_status = 'sleeping'
        self.save(update_fields=['sleep_status'])
    
    def unfreeze(self):
        """Unfreeze/wake up the meeting"""
        self.sleep_status = 'active'
        self.save(update_fields=['sleep_status'])

class MeetingParticipant(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    total_duration_seconds = models.IntegerField(default=0)
    
    # Per-participant permissions (managed by teacher)
    audio_permitted = models.BooleanField(default=True)
    video_permitted = models.BooleanField(default=True)
    screenshare_permitted = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['meeting', 'user']
    
    def __str__(self):
        return f"{self.user.username} in {self.meeting.title}"

    def get_duration_formatted(self):
        minutes = self.total_duration_seconds // 60
        seconds = self.total_duration_seconds % 60
        return f"{minutes}m {seconds}s"

class MeetingAttendanceLog(models.Model):
    """Logs every entry and exit for detailed attendance reporting"""
    EVENT_CHOICES = [
        ('join', 'Joined'),
        ('leave', 'Left'),
    ]
    participant = models.ForeignKey(MeetingParticipant, on_delete=models.CASCADE, related_name='attendance_logs')
    event_type = models.CharField(max_length=10, choices=EVENT_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)

class MeetingChat(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='chats')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.user.username}: {self.message[:20]}"

class MeetingSummary(models.Model):
    meeting = models.OneToOneField(Meeting, on_delete=models.CASCADE, related_name='summary')
    summary_text = models.TextField()
    key_points = models.JSONField(default=list)  # Storing as list of strings
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Summary for {self.meeting.title}"

class KickedParticipant(models.Model):
    """Tracks students kicked from meetings and their ban duration"""
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='kicked_users')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    kicked_at = models.DateTimeField(auto_now_add=True)
    banned_until = models.DateTimeField()
    
    class Meta:
        unique_together = ['meeting', 'user']
    
    def is_banned(self):
        return timezone.now() < self.banned_until
    
    def __str__(self):
        return f"{self.user.username} kicked from {self.meeting.meeting_code}"

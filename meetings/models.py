from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from common.encryption import EncryptedTextField

User = get_user_model()


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

    classroom = models.ForeignKey('academics.Classroom', on_delete=models.CASCADE, related_name='meetings', null=True, blank=True)
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
    student_can_view_camera = models.BooleanField(default=True)
    student_can_view_screenshare = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_extended = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} - {self.meeting_code}"

    class Meta:
        ordering = ['-scheduled_time']
        constraints = [
            models.UniqueConstraint(
                fields=['classroom', 'title'],
                condition=models.Q(status__in=['scheduled', 'live']),
                name='unique_active_meeting_title_per_classroom'
            ),
            models.UniqueConstraint(
                fields=['teacher', 'title'],
                condition=models.Q(status__in=['scheduled', 'live'], classroom__isnull=True),
                name='unique_active_standalone_meeting_title_per_teacher'
            ),
        ]

    def is_sleeping(self):
        return self.sleep_status == 'sleeping'

    def can_join(self):
        return self.status == 'live' and self.sleep_status == 'active'

    def is_expired(self):
        start = self.started_at or self.scheduled_time
        if not start:
            return False
        from datetime import timedelta
        expiration_time = start + timedelta(minutes=self.duration_minutes)
        return timezone.now() >= expiration_time

    def is_teacher_present(self):
        return MeetingParticipant.objects.filter(
            meeting=self,
            user=self.teacher,
            is_active=True
        ).exists()

    def put_to_sleep(self):
        self.sleep_status = 'sleeping'
        self.save(update_fields=['sleep_status'])

    def unfreeze(self):
        self.sleep_status = 'active'
        self.save(update_fields=['sleep_status'])


class MeetingParticipant(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    total_duration_seconds = models.IntegerField(default=0)

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
    message = EncryptedTextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.user.username}: {self.message[:20]}"


class MeetingSummary(models.Model):
    meeting = models.OneToOneField(Meeting, on_delete=models.CASCADE, related_name='summary')
    summary_text = models.TextField()
    key_points = models.JSONField(default=list)
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Summary for {self.meeting.title}"


class KickedParticipant(models.Model):
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


# ──────────────────────────────────────────────────────────────────────────────
# Phase 1C: Backward Compatibility Layer & Model Aliases
# Models migrated to 'academics' and 'course_materials' apps
# ──────────────────────────────────────────────────────────────────────────────
from academics.models import Classroom as AcademicsClassroom
from academics.models import ClassroomMembership as AcademicsClassroomMembership
from course_materials.models import MaterialUnit as LibraryMaterialUnit
from course_materials.models import StudyMaterial as LibraryStudyMaterial
from course_materials.models import MaterialChunk as LibraryMaterialChunk
from course_materials.models import MaterialBookmark as LibraryMaterialBookmark
from course_materials.models import study_material_upload_path

Classroom = AcademicsClassroom
ClassroomMembership = AcademicsClassroomMembership
MaterialUnit = LibraryMaterialUnit
StudyMaterial = LibraryStudyMaterial
MaterialChunk = LibraryMaterialChunk
MaterialBookmark = LibraryMaterialBookmark

__all__ = [
    'Meeting',
    'MeetingParticipant',
    'MeetingAttendanceLog',
    'MeetingChat',
    'MeetingSummary',
    'KickedParticipant',
    'Classroom',
    'ClassroomMembership',
    'MaterialUnit',
    'StudyMaterial',
    'MaterialChunk',
    'MaterialBookmark',
    'study_material_upload_path',
]

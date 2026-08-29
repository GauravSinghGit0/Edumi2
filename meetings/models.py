from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class Classroom(models.Model):
    """Virtual classroom that persists across multiple meeting sessions"""
    class_code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    password = models.CharField(max_length=128)  # Will be hashed
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_classrooms')
    description = models.TextField(blank=True)
    auto_approve = models.BooleanField(default=False, help_text="Automatically approve students who join with valid class code & password")
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

    def get_or_create_conversation(self):
        """Get or create the group conversation for this classroom and ensure teacher and approved students are participants."""
        from accounts.messaging_models import Conversation
        conversation, created = Conversation.objects.get_or_create(classroom=self)
        if not conversation.participants.filter(id=self.teacher_id).exists():
            conversation.participants.add(self.teacher)
        approved_students = self.get_approved_students()
        for student in approved_students:
            if not conversation.participants.filter(id=student.id).exists():
                conversation.participants.add(student)
        return conversation

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
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_extended = models.BooleanField(default=False)
    
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

    def is_expired(self):
        """Check if scheduled duration time limit has passed."""
        start = self.started_at or self.scheduled_time
        if not start:
            return False
        from datetime import timedelta
        expiration_time = start + timedelta(minutes=self.duration_minutes)
        return timezone.now() >= expiration_time

    def is_teacher_present(self):
        """Check if the teacher or host is currently connected and active in the meeting."""
        return MeetingParticipant.objects.filter(
            meeting=self,
            user=self.teacher,
            is_active=True
        ).exists()
    
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

from common.encryption import EncryptedTextField

class MeetingChat(models.Model):
    """Represents a chat message during a meeting (AES-256 encrypted at rest)"""
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


def study_material_upload_path(instance, filename):
    """Store material under classroom directory"""
    return f"study_materials/{instance.classroom_id}/{filename}"


class MaterialUnit(models.Model):
    """Curriculum unit or topic folder inside a classroom"""
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='material_units')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = 'Material Unit'
        verbose_name_plural = 'Material Units'

    def __str__(self):
        return f"{self.classroom.title} - {self.title}"

    def get_published_materials(self):
        return self.materials.filter(is_published=True).order_by('-created_at')


class StudyMaterial(models.Model):
    """Represents a digital study resource, document, lecture recording, or link"""
    MATERIAL_TYPES = [
        ('document', 'Document / PDF / Word'),
        ('slides', 'Presentation / Slides'),
        ('notes', 'Lecture Notes / Markdown'),
        ('video', 'Video / Lecture Recording'),
        ('link', 'External Web Link / Resource'),
        ('book', 'e-Book / Reference Book'),
    ]

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='study_materials')
    unit = models.ForeignKey(MaterialUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name='materials')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    material_type = models.CharField(max_length=20, choices=MATERIAL_TYPES, default='document')
    file = models.FileField(upload_to=study_material_upload_path, null=True, blank=True)
    external_url = models.URLField(max_length=500, blank=True, null=True)
    content_text = models.TextField(blank=True, help_text="Rich text / markdown notes content")
    file_size_bytes = models.BigIntegerField(default=0)
    file_extension = models.CharField(max_length=20, blank=True)
    is_published = models.BooleanField(default=True, db_index=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_materials')
    download_count = models.IntegerField(default=0)
    view_count = models.IntegerField(default=0)
    
    # ── RAG (Retrieval-Augmented Generation) & AI Semantic Pipeline ──
    extracted_text = models.TextField(blank=True, help_text="Parsed plaintext for LLM/RAG search indexing")
    summary_ai = models.TextField(blank=True, help_text="AI-generated conceptual summary")
    key_topics = models.JSONField(default=list, blank=True, help_text="Extracted keywords/topics for hybrid search")
    rag_indexed = models.BooleanField(default=False, db_index=True, help_text="True if document chunks are embedded in vector store")
    rag_indexed_at = models.DateTimeField(null=True, blank=True)
    rag_metadata = models.JSONField(default=dict, blank=True, help_text="Vector IDs, model version & chunking metadata")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Study Material'
        verbose_name_plural = 'Study Materials'

    def __str__(self):
        return f"{self.title} ({self.get_material_type_display()})"

    def get_file_size_formatted(self):
        """Format byte count into human-readable size"""
        bytes_val = self.file_size_bytes or (self.file.size if self.file else 0)
        if not bytes_val:
            return ""
        if bytes_val < 1024:
            return f"{bytes_val} B"
        elif bytes_val < 1024 * 1024:
            return f"{bytes_val / 1024:.1f} KB"
        elif bytes_val < 1024 * 1024 * 1024:
            return f"{bytes_val / (1024 * 1024):.1f} MB"
        return f"{bytes_val / (1024 * 1024 * 1024):.1f} GB"

    def get_icon_name(self):
        icons = {
            'document': 'file-text',
            'slides': 'presentation',
            'notes': 'book-open',
            'video': 'video',
            'link': 'external-link',
            'book': 'bookmark',
        }
        return icons.get(self.material_type, 'file')

    def get_badge_color(self):
        colors = {
            'document': '#ef4444',
            'slides': '#f59e0b',
            'notes': '#3b82f6',
            'video': '#8b5cf6',
            'link': '#10b981',
            'book': '#6366f1',
        }
        return colors.get(self.material_type, '#64748b')

    def is_bookmarked_by(self, user):
        if not user or not user.is_authenticated:
            return False
        return self.bookmarks.filter(user=user).exists()


class MaterialChunk(models.Model):
    """Segmented text chunk for RAG embedding and vector similarity retrieval"""
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.IntegerField(default=0)
    chunk_text = models.TextField()
    token_count = models.IntegerField(default=0)
    page_number = models.IntegerField(null=True, blank=True)
    embedding_id = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['material', 'chunk_index']
        verbose_name = 'Material Chunk'
        verbose_name_plural = 'Material Chunks'

    def __str__(self):
        return f"{self.material.title} [Chunk #{self.chunk_index}]"


class MaterialBookmark(models.Model):
    """User bookmark for quick library access"""
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE, related_name='bookmarks')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='material_bookmarks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['material', 'user']
        ordering = ['-created_at']


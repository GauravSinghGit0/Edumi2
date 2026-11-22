from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class Classroom(models.Model):
    """
    Virtual classroom that persists across multiple meeting sessions.
    MIGRATED from meetings.models.Classroom in Phase 1B.
    Physical table remains 'meetings_classroom' for zero-downtime migration.
    """
    class_code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    password = models.CharField(max_length=128)
    teacher = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_classrooms')
    description = models.TextField(blank=True)
    auto_approve = models.BooleanField(default=False, help_text="Automatically approve students who join with valid class code & password")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meetings_classroom'  # CRITICAL: Reuse existing table
        ordering = ['-created_at']
        verbose_name = 'Classroom'
        verbose_name_plural = 'Classrooms'

    def __str__(self):
        return f"{self.title} ({self.class_code})"

    def get_approved_students(self):
        """Get all approved students in this classroom"""
        return User.objects.filter(
            classroom_memberships__classroom=self,
            classroom_memberships__status='approved'
        )

    def get_approved_memberships(self):
        """Get all approved memberships"""
        return self.memberships.filter(status='approved').select_related('student')

    def get_pending_requests(self):
        """Get all pending join requests"""
        return self.memberships.filter(status='pending').select_related('student')

    def auto_clean_stale_meetings(self):
        """Auto-clean expired or abandoned live meetings for this classroom."""
        from django.apps import apps
        Meeting = apps.get_model('meetings', 'Meeting')
        live_meetings = Meeting.objects.filter(classroom=self, status='live')
        for m in live_meetings:
            if hasattr(m, 'is_expired') and m.is_expired():
                m.status = 'ended'
                m.ended_at = timezone.now()
                m.save(update_fields=['status', 'ended_at'])

    def has_active_meeting(self):
        """Check if classroom has an active meeting"""
        from django.apps import apps
        Meeting = apps.get_model('meetings', 'Meeting')
        self.auto_clean_stale_meetings()
        return Meeting.objects.filter(classroom=self, status='live').exists()

    def get_active_meeting(self):
        """Get the current active meeting if any"""
        from django.apps import apps
        Meeting = apps.get_model('meetings', 'Meeting')
        self.auto_clean_stale_meetings()
        return Meeting.objects.filter(classroom=self, status='live').first()

    def get_or_create_conversation(self):
        """Get or create group conversation for this classroom"""
        from django.apps import apps
        Conversation = apps.get_model('accounts', 'Conversation')
        conversation, created = Conversation.objects.get_or_create(classroom=self)
        if not conversation.participants.filter(id=self.teacher_id).exists():
            conversation.participants.add(self.teacher)
        approved_students = self.get_approved_students()
        for student in approved_students:
            if not conversation.participants.filter(id=student.id).exists():
                conversation.participants.add(student)
        return conversation


class ClassroomMembership(models.Model):
    """
    Student membership and approval status in classrooms.
    MIGRATED from meetings.models.ClassroomMembership in Phase 1B.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('denied', 'Denied'),
        ('removed', 'Removed'),
        ('left', 'Left'),
    ]

    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='classroom_memberships'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_memberships'
    )

    class Meta:
        db_table = 'meetings_classroommembership'  # CRITICAL: Reuse existing table
        unique_together = ['classroom', 'student']
        ordering = ['-requested_at']
        verbose_name = 'Classroom Membership'
        verbose_name_plural = 'Classroom Memberships'

    def __str__(self):
        return f"{self.student.username} - {self.classroom.title} ({self.status})"


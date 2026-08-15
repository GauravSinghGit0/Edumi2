from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Notification(models.Model):
    """Notification system for all important events"""
    NOTIFICATION_TYPES = [
        ('message', 'New Message'),
        ('meeting_scheduled', 'Meeting Scheduled'),
        ('meeting_started', 'Meeting Started'),
        ('meeting_cancelled', 'Meeting Cancelled'),
        ('classroom_joined', 'Classroom Join Request'),
        ('classroom_approved', 'Classroom Request Approved'),
        ('classroom_denied', 'Classroom Request Denied'),
        ('classroom_removed', 'Removed from Classroom'),
        ('student_joined', 'Student Joined Classroom'),
        ('meeting_reminder', 'Meeting Reminder'),
        ('system', 'System Notification'),
    ]
    
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True, null=True)  # URL to navigate to
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Optional references to related objects
    related_user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='related_notifications')
    related_meeting_id = models.IntegerField(null=True, blank=True)
    related_classroom_id = models.IntegerField(null=True, blank=True)
    related_message_id = models.IntegerField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.recipient.username} - {self.title}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])
    
    @classmethod
    def create_message_notification(cls, recipient, sender, conversation_id):
        """Create notification for new message"""
        return cls.objects.create(
            recipient=recipient,
            notification_type='message',
            title=f'New message from {sender.get_full_name() or sender.username}',
            message=f'{sender.get_full_name() or sender.username} sent you a message',
            link=f'/accounts/inbox/{conversation_id}/',
            related_user=sender
        )
    
    @classmethod
    def create_meeting_scheduled_notification(cls, recipient, meeting, teacher):
        """Create notification when meeting is scheduled"""
        return cls.objects.create(
            recipient=recipient,
            notification_type='meeting_scheduled',
            title='New Meeting Scheduled',
            message=f'{teacher.get_full_name() or teacher.username} scheduled "{meeting.title}" for {meeting.scheduled_time.strftime("%b %d, %Y at %I:%M %p")}',
            link=f'/meetings/join/{meeting.meeting_code}/',
            related_user=teacher,
            related_meeting_id=meeting.id
        )
    
    @classmethod
    def create_meeting_started_notification(cls, recipient, meeting):
        """Create notification when meeting starts"""
        return cls.objects.create(
            recipient=recipient,
            notification_type='meeting_started',
            title='Meeting Started',
            message=f'"{meeting.title}" has started. Join now!',
            link=f'/meetings/join/{meeting.meeting_code}/',
            related_meeting_id=meeting.id
        )
    
    @classmethod
    def create_meeting_cancelled_notification(cls, recipient, meeting):
        """Create notification when meeting is cancelled"""
        return cls.objects.create(
            recipient=recipient,
            notification_type='meeting_cancelled',
            title='Meeting Cancelled',
            message=f'"{meeting.title}" scheduled for {meeting.scheduled_time.strftime("%b %d, %Y at %I:%M %p")} has been cancelled',
            related_meeting_id=meeting.id
        )
    
    @classmethod
    def create_classroom_join_request_notification(cls, teacher, student, classroom):
        """Create notification when student requests to join classroom"""
        return cls.objects.create(
            recipient=teacher,
            notification_type='classroom_joined',
            title='New Classroom Join Request',
            message=f'{student.get_full_name() or student.username} requested to join "{classroom.title}"',
            link=f'/meetings/classroom/{classroom.id}/',
            related_user=student,
            related_classroom_id=classroom.id
        )
    
    @classmethod
    def create_classroom_approved_notification(cls, student, classroom, teacher):
        """Create notification when join request is approved"""
        return cls.objects.create(
            recipient=student,
            notification_type='classroom_approved',
            title='Classroom Request Approved',
            message=f'Your request to join "{classroom.title}" has been approved',
            link=f'/meetings/classroom/{classroom.id}/',
            related_user=teacher,
            related_classroom_id=classroom.id
        )
    
    @classmethod
    def create_classroom_denied_notification(cls, student, classroom):
        """Create notification when join request is denied"""
        return cls.objects.create(
            recipient=student,
            notification_type='classroom_denied',
            title='Classroom Request Denied',
            message=f'Your request to join "{classroom.title}" was not approved',
            link='/meetings/student-classrooms/',
            related_classroom_id=classroom.id
        )
    
    @classmethod
    def create_classroom_removed_notification(cls, student, classroom):
        """Create notification when student is removed from classroom"""
        return cls.objects.create(
            recipient=student,
            notification_type='classroom_removed',
            title='Removed from Classroom',
            message=f'You have been removed from "{classroom.title}"',
            link='/meetings/student-classrooms/',
            related_classroom_id=classroom.id
        )
    
    @classmethod
    def create_student_joined_notification(cls, teacher, student, classroom):
        """Create notification when student joins classroom (after approval)"""
        return cls.objects.create(
            recipient=teacher,
            notification_type='student_joined',
            title='Student Joined Classroom',
            message=f'{student.get_full_name() or student.username} joined "{classroom.title}"',
            link=f'/meetings/classroom/{classroom.id}/',
            related_user=student,
            related_classroom_id=classroom.id
        )
    
    @classmethod
    def create_meeting_reminder_notification(cls, recipient, meeting):
        """Create notification as meeting reminder (15 minutes before)"""
        return cls.objects.create(
            recipient=recipient,
            notification_type='meeting_reminder',
            title='Meeting Starting Soon',
            message=f'"{meeting.title}" starts in 15 minutes',
            link=f'/meetings/join/{meeting.meeting_code}/',
            related_meeting_id=meeting.id
        )
    
    @classmethod
    def create_broadcast_notification(cls, recipient, title, message, sender=None):
        """Create broadcast notification for all users"""
        return cls.objects.create(
            recipient=recipient,
            notification_type='system',
            title=title,
            message=message,
            link='/notifications/',
            related_user=sender
        )
    
    @classmethod
    def get_unread_count(cls, user):
        """Get count of unread notifications for user"""
        return cls.objects.filter(recipient=user, is_read=False).count()
    
    @classmethod
    def mark_all_as_read(cls, user):
        """Mark all notifications as read for user"""
        cls.objects.filter(recipient=user, is_read=False).update(is_read=True)

from .notification_models import Notification
from django.contrib.auth import get_user_model
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

User = get_user_model()


def send_ws_notification(recipient_id, data):
    """Generic helper to send WebSocket notification to a user"""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"user_{recipient_id}",
            {
                "type": "send_notification",
                "data": data
            }
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"WebSocket notification failed for user {recipient_id}: {e}"
        )

def notify_new_message(sender, recipient, conversation_id, content="New message received", created_at=None,
                       sender_name=None, sender_role=None, sender_pfp=None, message_id=None,
                       image_url=None, file_url=None, file_name=None):
    """Send notification when a new message is sent with full centralized profile identity."""
    if sender != recipient:  # Don't notify yourself
        Notification.create_message_notification(recipient, sender, conversation_id)
        
        profile = getattr(sender, 'userprofile', None)
        if not sender_name:
            sender_name = (profile.get_display_name() if profile else sender.get_full_name()) or sender.username
        if not sender_pfp:
            sender_pfp = profile.get_profile_picture_url() if profile else f"https://ui-avatars.com/api/?name={sender.username}&background=6366f1&color=fff"
        if not sender_role:
            is_teacher = bool((profile and profile.user_type == 'teacher') or sender.is_superuser)
            sender_role = 'Teacher' if is_teacher else 'Student'

        payload = {
            "type": "new_message",
            "message_id": message_id,
            "sender": sender.username,
            "sender_name": sender_name,
            "sender_role": sender_role,
            "sender_pfp": sender_pfp,
            "conversation_id": conversation_id,
            "message": content,
            "image_url": image_url,
            "file_url": file_url,
            "file_name": file_name,
        }
        if created_at is not None:
            payload["created_at"] = created_at

        # Broadcast via WebSocket
        send_ws_notification(recipient.id, payload)


def notify_meeting_scheduled(meeting, classroom=None):
    """Send notification when a meeting is scheduled"""
    teacher = meeting.teacher
    
    if classroom:
        # Notify all approved students in the classroom
        students = classroom.get_approved_students()
        for student in students:
            Notification.create_meeting_scheduled_notification(student, meeting, teacher)
            send_ws_notification(student.id, {
                "type": "meeting_scheduled",
                "title": meeting.title,
                "meeting_id": meeting.id
            })
    # For non-classroom meetings, you could notify specific participants if needed


def notify_meeting_started(meeting, classroom=None):
    """Send notification when a meeting starts"""
    if classroom:
        # Notify all approved students in the classroom
        students = classroom.get_approved_students()
        for student in students:
            Notification.create_meeting_started_notification(student, meeting)
            send_ws_notification(student.id, {
                "type": "meeting_started",
                "meeting_id": meeting.id,
                "title": meeting.title,
                "classroom": classroom.title
            })
    else:
        # Notify all participants
        participants = meeting.participants.all()
        for participant in participants:
            if participant.user != meeting.teacher:
                Notification.create_meeting_started_notification(participant.user, meeting)
                send_ws_notification(participant.user.id, {
                    "type": "meeting_started",
                    "meeting_id": meeting.id,
                    "title": meeting.title
                })


def notify_meeting_cancelled(meeting, classroom=None):
    """Send notification when a meeting is cancelled"""
    if classroom:
        # Notify all approved students in the classroom
        students = classroom.get_approved_students()
        for student in students:
            Notification.create_meeting_cancelled_notification(student, meeting)
            send_ws_notification(student.id, {
                "type": "meeting_cancelled",
                "title": meeting.title
            })
    else:
        # Notify all participants
        participants = meeting.participants.all()
        for participant in participants:
            if participant.user != meeting.teacher:
                Notification.create_meeting_cancelled_notification(participant.user, meeting)
                send_ws_notification(participant.user.id, {
                    "type": "meeting_cancelled",
                    "title": meeting.title
                })


def notify_classroom_join_request(student, classroom):
    """Send notification to teacher when student requests to join classroom"""
    teacher = classroom.teacher
    Notification.create_classroom_join_request_notification(teacher, student, classroom)
    send_ws_notification(teacher.id, {
        "type": "classroom_request",
        "student_name": student.username,
        "classroom_title": classroom.title
    })


def notify_classroom_request_approved(student, classroom, teacher):
    """Send notification to student when their join request is approved"""
    Notification.create_classroom_approved_notification(student, classroom, teacher)
    send_ws_notification(student.id, {
        "type": "classroom_approved",
        "classroom_title": classroom.title,
        "teacher_name": teacher.username
    })

def notify_classroom_request_denied(student, classroom):
    """Send notification to student when their join request is denied"""
    Notification.objects.create(
        recipient=student,
        notification_type='classroom_denied',
        title='Join Request Denied',
        message=f'Your request to join "{classroom.title}" was denied.',
    )
    send_ws_notification(student.id, {
        "type": "classroom_denied",
        "classroom_title": classroom.title
    })

def notify_student_removed_from_classroom(student, classroom):
    """Send notification to student when they are removed from classroom"""
    Notification.objects.create(
        recipient=student,
        notification_type='classroom_removed',
        title='Removed from Classroom',
        message=f'You have been removed from "{classroom.title}".',
    )
    send_ws_notification(student.id, {
        "type": "classroom_removed",
        "classroom_title": classroom.title
    })


def notify_student_joined_classroom(student, classroom):
    """Send notification to teacher when a student joins their classroom"""
    teacher = classroom.teacher
    Notification.create_student_joined_notification(teacher, student, classroom)
    send_ws_notification(teacher.id, {
        "type": "student_joined",
        "student_name": student.username,
        "classroom_title": classroom.title
    })


def notify_meeting_reminder(meeting, classroom=None):
    """Send reminder notification 15 minutes before meeting starts"""
    if classroom:
        # Notify all approved students in the classroom
        students = classroom.get_approved_students()
        for student in students:
            Notification.create_meeting_reminder_notification(student, meeting)
    else:
        # Notify all participants
        participants = meeting.participants.all()
        for participant in participants:
            if participant.user != meeting.teacher:
                Notification.create_meeting_reminder_notification(participant.user, meeting)

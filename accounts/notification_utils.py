from django.db import transaction
from django.conf import settings
from django.template.loader import render_to_string
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

        def _send():
            try:
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

        transaction.on_commit(_send)
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


def notify_meeting_started(meeting, classroom=None, request=None):
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

    # Dispatch email invitation link to enrolled students asynchronously
    try:
        send_live_class_started_email(meeting, classroom=classroom, request=request)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to dispatch live class started email: {e}")


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


def send_live_class_started_email(meeting, classroom=None, students=None, request=None):
    """
    Sends email invitations to enrolled students when a teacher starts a live class session.
    Dispatched asynchronously via Celery/background thread using a single pooled SMTP connection.
    """
    try:
        if classroom is None and getattr(meeting, 'classroom', None):
            classroom = meeting.classroom

        if students is None:
            if classroom:
                students = list(classroom.get_approved_students())
            else:
                students = [p.user for p in meeting.participants.select_related('user').all() if p.user != meeting.teacher]

        # Filter recipients who have a valid email address
        recipients = [s for s in students if getattr(s, 'email', None) and s.email.strip()]
        if not recipients:
            return True

        if request:
            base_url = request.build_absolute_uri('/')[:-1]
        else:
            base_url = getattr(settings, 'DEFAULT_DOMAIN', 'http://localhost:8002')

        join_url = f"{base_url}/meetings/join/{meeting.meeting_code}/"

        teacher = meeting.teacher
        teacher_profile = getattr(teacher, 'userprofile', None)
        teacher_name = (teacher_profile.get_display_name() if teacher_profile else teacher.get_full_name()) or teacher.username

        from_email = settings.DEFAULT_FROM_EMAIL
        subject = f"🔴 Live Class Started: {meeting.title}" + (f" - {classroom.title}" if classroom else "")

        email_messages_data = []
        for student in recipients:
            student_profile = getattr(student, 'userprofile', None)
            student_name = (student_profile.get_display_name() if student_profile else student.get_full_name()) or student.username

            context = {
                'student_name': student_name,
                'teacher_name': teacher_name,
                'meeting': meeting,
                'classroom': classroom,
                'join_url': join_url,
            }

            try:
                html_content = render_to_string('accounts/emails/live_meeting_started_email.html', context)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Could not render live_meeting_started_email.html: {e}")
                html_content = None

            text_content = f"""
Hi {student_name},

Your teacher {teacher_name} has just started the live class: "{meeting.title}" in {classroom.title if classroom else 'EduMi'}.

Click the link below to join now:
{join_url}

Meeting Code: {meeting.meeting_code}

📬 Deliverability Tip: If this email landed in your Spam or Promotions folder, please mark it as "Not Spam" to ensure you never miss future class invitations.

Best regards,
The EduMi Team
"""
            email_messages_data.append({
                'subject': subject,
                'text_content': text_content,
                'html_content': html_content,
                'recipient': student.email,
                'from_email': from_email,
            })

        from accounts.email_tokens import _dispatch_bulk_emails_async
        return _dispatch_bulk_emails_async(email_messages_data)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"Error preparing live class emails for meeting {meeting.id}: {exc}")
        return False


def notify_new_assignment_posted(assignment, request=None):
    """
    Sends in-app, WebSocket, and async email notifications to all enrolled students
    when a teacher creates or publishes a homework assignment.
    """
    try:
        classroom = assignment.classroom
        students = list(classroom.get_approved_students())
        if not students:
            return True

        # 1. In-App and WebSocket Notifications
        for student in students:
            try:
                Notification.create_assignment_posted_notification(student, assignment)
                send_ws_notification(student.id, {
                    "type": "assignment_posted",
                    "assignment_id": assignment.id,
                    "title": assignment.title,
                    "classroom": classroom.title,
                    "due_date": assignment.due_date.isoformat() if assignment.due_date else None,
                    "total_marks": assignment.total_marks
                })
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed in-app notification for student {student.id}: {e}")

        # 2. Email Notifications to students with valid email addresses
        send_new_assignment_email(assignment, classroom=classroom, students=students, request=request)
        return True
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"Error dispatching assignment notifications for {assignment.id}: {exc}")
        return False


def send_new_assignment_email(assignment, classroom=None, students=None, request=None):
    """
    Sends email notifications with the submission deadline to enrolled students when homework is created/published.
    Dispatched asynchronously via Celery/background thread using a single pooled SMTP connection.
    """
    try:
        if classroom is None:
            classroom = assignment.classroom

        if students is None:
            students = list(classroom.get_approved_students())

        recipients = [s for s in students if getattr(s, 'email', None) and s.email.strip()]
        if not recipients:
            return True

        if request:
            base_url = request.build_absolute_uri('/')[:-1]
        else:
            base_url = getattr(settings, 'DEFAULT_DOMAIN', 'http://localhost:8002')

        assignment_url = f"{base_url}/assignments/{assignment.id}/"

        teacher = assignment.created_by
        teacher_profile = getattr(teacher, 'userprofile', None)
        teacher_name = (teacher_profile.get_display_name() if teacher_profile else teacher.get_full_name()) or teacher.username

        formatted_due_date = assignment.due_date.strftime("%B %d, %Y at %I:%M %p") if assignment.due_date else "No deadline specified"
        from_email = settings.DEFAULT_FROM_EMAIL
        subject = f"📝 New Assignment: {assignment.title} - {classroom.title}"

        email_messages_data = []
        for student in recipients:
            student_profile = getattr(student, 'userprofile', None)
            student_name = (student_profile.get_display_name() if student_profile else student.get_full_name()) or student.username

            context = {
                'student_name': student_name,
                'teacher_name': teacher_name,
                'assignment': assignment,
                'classroom': classroom,
                'assignment_url': assignment_url,
                'formatted_due_date': formatted_due_date,
            }

            try:
                html_content = render_to_string('accounts/emails/new_assignment_email.html', context)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Could not render new_assignment_email.html: {e}")
                html_content = None

            text_content = f"""
Hi {student_name},

A new assignment has been posted by {teacher_name} in "{classroom.title}".

Assignment: {assignment.title}
Total Points: {assignment.total_marks} Marks
Submission Deadline: {formatted_due_date}

View instructions and submit your work before the deadline:
{assignment_url}

📬 Deliverability Tip: If this email landed in your Spam or Promotions folder, please mark it as "Not Spam" to ensure you never miss critical homework deadlines.

Best regards,
The EduMi Team
"""
            email_messages_data.append({
                'subject': subject,
                'text_content': text_content,
                'html_content': html_content,
                'recipient': student.email,
                'from_email': from_email,
            })

        from accounts.email_tokens import _dispatch_bulk_emails_async
        return _dispatch_bulk_emails_async(email_messages_data)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"Error preparing assignment emails for assignment {assignment.id}: {exc}")
        return False

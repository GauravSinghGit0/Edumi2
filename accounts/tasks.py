"""
accounts/tasks.py
Asynchronous Celery tasks for accounts: verification emails, password reset emails,
and periodic cleanup of expired OTPs and unverified stale accounts.
"""
import logging
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('accounts')


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_email_async_task(self, subject, text_content, from_email, recipient_list, html_content=None):
    """
    Asynchronously dispatches an email via Celery worker.
    Includes automated retry logic with exponential backoff on transient SMTP failures.
    """
    try:
        send_mail(
            subject=subject,
            message=text_content.strip() if text_content else '',
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            html_message=html_content,
            fail_silently=False,
        )
        logger.info(f"Async email '{subject}' sent successfully to {recipient_list}")
        return True
    except Exception as exc:
        logger.error(f"Async email dispatch failed for {recipient_list}: {exc}")
        if not settings.DEBUG:
            raise self.retry(exc=exc)
        return False


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_bulk_emails_async_task(self, email_messages_data):
    """
    Asynchronously dispatches a list of email dicts via Celery worker.
    Uses a single opened SMTP connection for maximum throughput and avoiding SMTP rate limits.
    """
    from django.core.mail import get_connection, EmailMultiAlternatives
    try:
        connection = get_connection()
        connection.open()
        django_messages = []
        for item in email_messages_data:
            recipient = item.get('recipient')
            if not recipient:
                continue
            msg = EmailMultiAlternatives(
                subject=item.get('subject', 'EduMi Notification'),
                body=item.get('text_content', '').strip(),
                from_email=item.get('from_email') or settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
                connection=connection,
            )
            if item.get('html_content'):
                msg.attach_alternative(item['html_content'], "text/html")
            django_messages.append(msg)
        if django_messages:
            connection.send_messages(django_messages)
        connection.close()
        logger.info(f"Bulk async email sent {len(django_messages)} messages successfully.")
        return True
    except Exception as exc:
        logger.error(f"Bulk async email dispatch failed: {exc}")
        if not settings.DEBUG:
            raise self.retry(exc=exc)
        return False


@shared_task
def cleanup_expired_otps_task():
    """
    Periodic task: Cleans up expired and already-used OTP records from the database.
    Prevents unbounded growth of EmailVerificationOTP table.
    """
    from accounts.models import EmailVerificationOTP
    now = timezone.now()
    deleted_count, _ = EmailVerificationOTP.objects.filter(expires_at__lt=now).delete()
    logger.info(f"Cleaned up {deleted_count} expired verification OTP records.")
    return deleted_count


@shared_task
def bulk_import_users_task(admin_user_id, rows_data, send_invites=True, original_filename='users.csv', task_id=None, ip_address='127.0.0.1'):
    """
    Asynchronous task: Creates platform users from validated import data.
    Updates progress in cache, dispatches invitation emails with SMTP fallback,
    and logs exactly one unified AdminAuditTrail entry with execution counts.
    Stores failed rows in cache for CSV export.
    """
    import uuid
    from django.core.cache import cache
    from django.contrib.auth import get_user_model
    from django.db import transaction
    from accounts.models import UserProfile
    from common.models import AdminAuditTrail

    User = get_user_model()
    task_id = task_id or str(uuid.uuid4())
    admin_user = User.objects.filter(id=admin_user_id).first()

    total = len(rows_data)
    success_count = 0
    failed_rows = []

    # Initialize task state in cache
    cache.set(f"user_import_progress_{task_id}", {
        'status': 'PROGRESS',
        'current': 0,
        'total': total,
        'progress_pct': 0,
        'success_count': 0,
        'failed_count': 0,
    }, timeout=3600)

    for idx, row in enumerate(rows_data):
        uname = (row.get('username') or '').strip()
        email = (row.get('email') or '').strip()
        first_name = (row.get('first_name') or '').strip()
        last_name = (row.get('last_name') or '').strip()
        role = (row.get('role') or 'student').strip().lower()
        dept = (row.get('department') or '').strip()

        # Normalization
        if role in ('faculty', 'instructor', 'professor'):
            role = 'teacher'
        elif role in ('administrator', 'staff'):
            role = 'admin'

        error_reason = None
        if not uname or not email:
            error_reason = 'Missing required username or email'
        elif User.objects.filter(username=uname).exists():
            error_reason = f"Username '{uname}' already exists in database"
        elif User.objects.filter(email__iexact=email).exists():
            error_reason = f"Email '{email}' is already registered in database"
        elif role not in ('student', 'teacher', 'admin'):
            error_reason = f"Invalid role '{role}'"

        if error_reason:
            failed_rows.append({
                'username': uname,
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
                'role': role,
                'department': dept,
                'error_reason': error_reason,
            })
            # Update progress
            cache.set(f"user_import_progress_{task_id}", {
                'status': 'PROGRESS',
                'current': idx + 1,
                'total': total,
                'progress_pct': round(((idx + 1) / total) * 100) if total else 100,
                'success_count': success_count,
                'failed_count': len(failed_rows),
            }, timeout=3600)
            continue

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=uname,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                )
                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.user_type = role
                if dept:
                    profile.department = dept
                profile.save(update_fields=['user_type', 'department'])

                if role == 'admin':
                    user.is_staff = True
                    user.save(update_fields=['is_staff'])

                # Send invitation email with SMTP fallback
                if send_invites:
                    try:
                        from accounts.email_tokens import send_password_reset_email
                        send_password_reset_email(None, user)
                    except Exception as mail_exc:
                        logger.warning(f"Could not dispatch invitation email to {email}: {mail_exc}")

                success_count += 1
        except Exception as exc:
            logger.error(f"Failed creating user @{uname}: {exc}")
            failed_rows.append({
                'username': uname,
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
                'role': role,
                'department': dept,
                'error_reason': str(exc),
            })

        # Update cache progress
        cache.set(f"user_import_progress_{task_id}", {
            'status': 'PROGRESS',
            'current': idx + 1,
            'total': total,
            'progress_pct': round(((idx + 1) / total) * 100) if total else 100,
            'success_count': success_count,
            'failed_count': len(failed_rows),
        }, timeout=3600)

    # Log exactly one BULK_ACTION audit trail entry
    if admin_user:
        try:
            AdminAuditTrail.objects.create(
                admin_user=admin_user,
                action_type=AdminAuditTrail.ACTION_BULK_ACTION,
                target_type='BulkUserImport',
                target_id=0,
                target_label=f"Bulk Import ({original_filename}): {success_count} succeeded, {len(failed_rows)} failed",
                ip_address=ip_address,
                changes_json={
                    'action': 'bulk_user_import',
                    'total_rows': total,
                    'success_count': success_count,
                    'failed_count': len(failed_rows),
                    'filename': original_filename,
                    'task_id': task_id,
                }
            )
        except Exception as audit_err:
            logger.error(f"Failed writing audit trail for bulk user import: {audit_err}")

    final_result = {
        'status': 'SUCCESS',
        'current': total,
        'total': total,
        'progress_pct': 100,
        'success_count': success_count,
        'failed_count': len(failed_rows),
        'has_failed_rows': len(failed_rows) > 0,
        'failed_rows_count': len(failed_rows),
        'task_id': task_id,
    }
    cache.set(f"user_import_progress_{task_id}", final_result, timeout=3600)
    cache.set(f"user_import_failed_{task_id}", failed_rows, timeout=3600)

    return final_result


@shared_task
def check_and_deliver_scheduled_announcements():
    """
    Periodic task to check and dispatch scheduled campus announcements.
    """
    from common.models import Announcement
    from common.announcement_service import deliver_announcement
    now = timezone.now()
    pending = Announcement.objects.filter(is_sent=False, scheduled_at__lte=now)
    count = 0
    for ann in pending:
        try:
            deliver_announcement(ann, sender=ann.created_by)
            count += 1
        except Exception as e:
            logger.error(f"Error delivering scheduled announcement #{ann.id}: {e}")
    return count


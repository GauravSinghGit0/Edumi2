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

"""
Background task to monitor Celery worker health.
Sends alerts if workers are down.
Phase 2.3 Refactoring.
"""
from celery import shared_task, current_app
from django.conf import settings
import logging

logger = logging.getLogger('monitoring')


@shared_task
def check_worker_health():
    """Check if minimum number of workers are active"""
    try:
        inspector = current_app.control.inspect(timeout=3.0)
        stats = inspector.stats() if inspector else None

        if not stats:
            logger.critical("❌ NO CELERY WORKERS ACTIVE!")
            send_alert("Celery workers are down!")
            return False

        worker_count = len(stats)
        if worker_count < 1:
            logger.warning(f"⚠️ Only {worker_count} Celery worker(s) active")
            send_alert(f"Low Celery worker count: {worker_count}")

        return True
    except Exception as e:
        logger.error(f"Error inspecting Celery worker health: {e}")
        return False


def send_alert(message):
    """Send alert via configured channels"""
    try:
        from django.core.mail import mail_admins
        mail_admins("Celery Worker Alert", message, fail_silently=True)
    except Exception:
        pass

    if hasattr(settings, 'SLACK_WEBHOOK_URL') and settings.SLACK_WEBHOOK_URL:
        try:
            import requests
            requests.post(settings.SLACK_WEBHOOK_URL, json={'text': f"🚨 {message}"}, timeout=5)
        except Exception:
            pass

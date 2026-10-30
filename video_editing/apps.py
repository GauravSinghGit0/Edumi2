import logging

from django.apps import AppConfig

logger = logging.getLogger("video_editing")


class EditorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "video_editing"

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_reconcile_stale_exports, sender=self)


def _reconcile_stale_exports(sender, **kwargs):
    """Mark VideoProject rows stuck in 'processing' as 'error'.

    Called after every migrate and once per server-process start.
    A 30-minute grace period avoids prematurely killing a long render.
    """
    try:
        from datetime import timedelta
        from django.utils import timezone
        from .models import VideoProject

        cutoff = timezone.now() - timedelta(minutes=30)
        stale_qs = VideoProject.objects.filter(
            status="processing", updated_at__lt=cutoff
        )
        count = stale_qs.update(
            status="error",
            error_message="Export interrupted by server restart or timeout.",
        )
        if count:
            logger.warning(
                "Reconciled %d stale 'processing' VideoProject(s) to 'error'.",
                count,
            )
    except Exception:
        pass

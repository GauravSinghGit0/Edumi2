import os
import logging
from celery import Celery

logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'edumi_core.settings')

app = Celery('edumi_core')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# namespace='CELERY' means all celery-related configuration keys
# should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

from celery.schedules import crontab

app.conf.beat_schedule = {
    'check-worker-health': {
        'task': 'monitoring.celery_health.check_worker_health',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
    },
}


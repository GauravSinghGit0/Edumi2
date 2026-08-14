from celery import shared_task
from videos.views_logic.utils import process_video_sync

@shared_task
def process_video(video_id):
    """Asynchronously process video qualities and chunks."""
    process_video_sync(video_id)

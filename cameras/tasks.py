import os
import subprocess
import logging
from celery import shared_task
from django.conf import settings
from .models import CameraRecording
from .ffmpeg_helpers import get_ffmpeg_binary

logger = logging.getLogger('cameras')

@shared_task
def process_recording_task(recording_id):
    """Background task to generate thumbnails and optimize video (keeping MKV format)"""
    try:
        rec = CameraRecording.objects.get(id=recording_id)
        current_path = rec.video_file.path
        
        # 1. Wait for file to be released (if FFmpeg is still closing it)
        import time
        max_retries = 10
        for i in range(max_retries):
            try:
                with open(current_path, 'rb+') as f:
                    break
            except IOError:
                logger.info(f"File {current_path} is locked, waiting... ({i+1}/{max_retries})")
                time.sleep(2)
        
        # We no longer remux to MP4 as per user request (prevents corruption)
        # Browsers can play MKV if codecs are compatible (H264/H265 + AAC)
        video_path = current_path
        
        # 2. Generate Thumbnail
        thumbnail_filename = f"thumb_{rec.id}.jpg"
        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'recordings', 'thumbnails')
        os.makedirs(thumbnail_dir, exist_ok=True)
        thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)
        
        # Try to get frame at 1 second, or 0 if it fails
        thumb_cmd = [
            get_ffmpeg_binary(), '-y', '-i', video_path,
            '-ss', '00:00:01', '-vframes', '1',
            '-q:v', '2', thumbnail_path
        ]
        
        subprocess.run(thumb_cmd, capture_output=True)
        
        if not os.path.exists(thumbnail_path):
            # Fallback to start of video
            thumb_cmd[4] = '00:00:00'
            subprocess.run(thumb_cmd, capture_output=True)
        
        if os.path.exists(thumbnail_path):
            rec.thumbnail.name = os.path.join('recordings', 'thumbnails', thumbnail_filename).replace('\\', '/')

        # 3. Finalize
        rec.recording_status = 'completed'
        rec.save()
        
        logger.info(f"Processed recording {recording_id} (MKV) successfully")
        return True
    except Exception as e:
        logger.error(f"Error processing recording {recording_id}: {e}")
        try:
            rec = CameraRecording.objects.get(id=recording_id)
            rec.recording_status = 'failed'
            rec.save()
        except: pass
        return False

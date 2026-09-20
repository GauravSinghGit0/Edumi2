from celery import shared_task
from .models import VideoProject
from . import ffmpeg_utils
from .views import _apply_new_working_file
from .timeline_compiler import compile_timeline_to_ffmpeg
import logging

logger = logging.getLogger(__name__)

@shared_task
def export_video_task(project_id, timeline_json):
    """
    Background celery task that processes a JSON timeline export using FFmpeg.
    """
    try:
        project = VideoProject.objects.get(pk=project_id)
        project.status = "processing"
        project.save(update_fields=['status'])
        
        logger.info(f"Starting Celery video export for Project {project_id}")
        
        tmp_output_path = ffmpeg_utils._tmp_path(".mp4")
        compile_timeline_to_ffmpeg(project, timeline_json, tmp_output_path)
        
        # Apply the compiled file as the new working file
        _apply_new_working_file(project, tmp_output_path, "timeline_export", "Exported JSON Timeline")
        
        project.status = "ready"
        project.save(update_fields=['status'])
        logger.info(f"Successfully finished Celery video export for Project {project_id}")
        
    except VideoProject.DoesNotExist:
        logger.error(f"Celery task failed: VideoProject {project_id} not found.")
    except Exception as e:
        logger.error(f"Celery task failed for Project {project_id}: {str(e)}")
        # Try to save error to project
        try:
            project = VideoProject.objects.get(pk=project_id)
            project.status = "error"
            project.error_message = str(e)
            project.save(update_fields=['status', 'error_message'])
        except Exception:
            pass


@shared_task
def extract_metadata_and_proxies_task(project_id):
    """
    Asynchronously extracts video metadata (duration, resolution, has_audio)
    and initializes clips_json in the background.
    """
    import json
    import os
    try:
        project = VideoProject.objects.get(pk=project_id)
        logger.info(f"Extracting metadata asynchronously for project {project_id}")
        meta = ffmpeg_utils.get_metadata(project.original_file.path)
        
        project.duration_seconds = meta.get("duration", 0.0)
        project.width = meta.get("width", 1920)
        project.height = meta.get("height", 1080)
        project.has_audio = meta.get("has_audio", True)
        project.status = "ready"
        
        # Initialize timeline_state if empty
        if not project.timeline_state:
            orig_filename = os.path.basename(project.original_file.name)
            if len(orig_filename) > 32:
                orig_filename = (project.title or "Clip") + ".mp4"
            has_aud = meta.get("has_audio", True)
            dur = meta.get("duration", 0.0) or 0.0
            bg_audios = []
            if has_aud and dur > 0:
                bg_audios.append({
                    "name": f"Audio Stream — {orig_filename}",
                    "filename": orig_filename,
                    "path": project.original_file.path if project.original_file else "",
                    "start": 0.0,
                    "end": dur,
                    "trimStart": 0.0,
                    "trimEnd": dur,
                    "bg_volume": 1.0,
                    "video_volume": 0.0,
                    "is_detached": True
                })

            project.timeline_state = {
                "trim": {"start": 0.0, "end": dur, "mode": "extract", "fade_in": False, "fade_out": False},
                "speed": 1.0,
                "audio": {"volume": 1.0, "muted": False},
                "text_overlays": [],
                "background_audios": bg_audios,
                "resize": None,
                "effects": {"grayscale": False, "rotate": 0, "fade": None},
                "clips": [{
                    "title": orig_filename,
                    "start": 0.0,
                    "end": dur,
                    "trimStart": 0.0,
                    "trimEnd": dur,
                    "duration": dur
                }]
            }
        
        project.save(update_fields=["duration_seconds", "width", "height", "has_audio", "status", "timeline_state"])
        logger.info(f"Asynchronous metadata extraction success for project {project_id}")
    except Exception as e:
        logger.error(f"Asynchronous metadata extraction failed for project {project_id}: {str(e)}")
        try:
            project = VideoProject.objects.get(pk=project_id)
            project.status = "error"
            project.error_message = f"Metadata extraction failed: {str(e)}"
            project.save(update_fields=["status", "error_message"])
        except Exception:
            pass

@shared_task
def generate_hls_proxy(project_id):
    """
    Generates a 480p HLS proxy for a video project.
    """
    import os
    import subprocess
    from django.conf import settings
    
    try:
        project = VideoProject.objects.get(pk=project_id)
        project.proxy_status = "processing"
        project.save(update_fields=["proxy_status"])
        
        logger.info(f"Generating HLS proxy for Project {project_id}")
        
        input_path = project.original_file.path
        
        # Create output directory for the HLS stream
        proxy_dir = os.path.join(settings.MEDIA_ROOT, 'proxies', str(project.owner_id), str(project_id))
        os.makedirs(proxy_dir, exist_ok=True)
        
        playlist_path = os.path.join(proxy_dir, 'proxy.m3u8')
        
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-preset", "superfast",
            "-threads", "0",
            "-profile:v", "baseline", "-level", "3.0",
            "-s", "854x480", "-start_number", "0",
            "-hls_time", "10", "-hls_list_size", "0",
            "-f", "hls", playlist_path
        ]
        
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.returncode != 0:
            raise Exception(f"FFmpeg HLS proxy failed: {process.stderr.decode('utf-8', errors='ignore')}")
            
        project.proxy_url = f"{settings.MEDIA_URL}proxies/{project.owner_id}/{project_id}/proxy.m3u8"
        project.proxy_status = "completed"
        project.save(update_fields=["proxy_status", "proxy_url"])
        logger.info(f"HLS proxy generation completed for Project {project_id}")
        
    except Exception as e:
        logger.error(f"HLS proxy generation failed for Project {project_id}: {str(e)}")
        try:
            project = VideoProject.objects.get(pk=project_id)
            project.proxy_status = "failed"
            project.save(update_fields=["proxy_status"])
        except Exception:
            pass

@shared_task
def cleanup_stale_temp_uploads(max_age_hours=24):
    """
    Periodic maintenance task: Cleans up abandoned chunk uploads in temp_uploads older than max_age_hours.
    Prevents storage disk exhaustion when users abandon uploads halfway.
    """
    import os
    import time
    import shutil
    from django.conf import settings

    temp_root = os.path.join(settings.MEDIA_ROOT, 'temp_uploads')
    if not os.path.exists(temp_root):
        return 0

    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    cleaned_count = 0

    for item in os.listdir(temp_root):
        item_path = os.path.join(temp_root, item)
        try:
            if os.path.isdir(item_path):
                mtime = os.path.getmtime(item_path)
                if mtime < cutoff:
                    shutil.rmtree(item_path, ignore_errors=True)
                    cleaned_count += 1
        except Exception as e:
            logger.warning(f"Error cleaning stale upload {item_path}: {e}")

    logger.info(f"Cleaned up {cleaned_count} stale upload directories.")
    return cleaned_count

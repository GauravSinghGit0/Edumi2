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
        
        # Initialize clips_json
        orig_filename = os.path.basename(project.original_file.name)
        if len(orig_filename) > 32:
            orig_filename = project.title + ".mp4"
        project.clips_json = json.dumps([
            {"title": orig_filename, "duration": meta.get("duration", 0.0)}
        ])
        
        project.save(update_fields=["duration_seconds", "width", "height", "has_audio", "status", "clips_json"])
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

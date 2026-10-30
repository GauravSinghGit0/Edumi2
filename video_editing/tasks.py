from celery import shared_task
from .models import VideoProject
from . import ffmpeg_utils
from .views import _apply_new_working_file
from .timeline_compiler import compile_timeline_to_ffmpeg
import logging

logger = logging.getLogger(__name__)

def dispatch_async(task_func, *args, **kwargs):
    """
    Safely dispatches a background task.
    If Celery is active and configured, calls task_func.delay(*args, **kwargs).
    Otherwise falls back instantly to a daemon Thread with zero blocking or delay.
    """
    import threading
    use_thread = True
    try:
        if hasattr(task_func, 'delay'):
            task_func.delay(*args, **kwargs)
            use_thread = False
    except Exception:
        use_thread = True

    if use_thread:
        fn = getattr(task_func, 'run', task_func)
        threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()


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
        
        # Apply the compiled file as the export artifact without destroying source proxies or project duration
        _apply_new_working_file(
            project,
            tmp_output_path,
            "timeline_export",
            "Exported JSON Timeline",
            clear_proxies=False,
            update_metadata=False,
            save_operation_file=False,
        )
        
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
        
        # Initialize timeline_state if empty or if clip duration was 0
        dur = meta.get("duration", 0.0) or 0.0
        orig_filename = os.path.basename(project.original_file.name)
        if len(orig_filename) > 32:
            orig_filename = (project.title or "Clip") + ".mp4"
        has_aud = meta.get("has_audio", True)
        
        should_reinit = (
            not project.timeline_state or
            not project.timeline_state.get("clips") or
            float(project.timeline_state["clips"][0].get("duration", 0.0)) <= 0
        )
        if should_reinit:
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

        # Dispatch filmstrip & waveform generation IMMEDIATELY (takes <2 seconds from original file)
        dispatch_async(generate_filmstrip_task, project.id)
        if project.has_audio:
            dispatch_async(generate_waveform_task, project.id)

        # Always build a small 360p MP4 proxy (libx264, preset veryfast, -g 15, -movflags +faststart, -threads 2)
        try:
            from django.conf import settings
            from cameras.ffmpeg_helpers import get_ffmpeg_binary
            import subprocess

            proxy_dir = os.path.join(settings.MEDIA_ROOT, 'proxies', str(project.owner_id), str(project.id))
            os.makedirs(proxy_dir, exist_ok=True)
            proxy_mp4_path = os.path.join(proxy_dir, 'proxy.mp4')

            ffmpeg_bin = get_ffmpeg_binary()
            creation_flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) if os.name == "nt" else 0
            audio_args = ["-c:a", "aac", "-b:a", "64k"] if project.has_audio else ["-an"]
            proxy_cmd = [
                ffmpeg_bin, "-y",
                "-i", project.original_file.path,
                "-vf", "scale=-2:360",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-g", "15",
                "-threads", "2",
                *audio_args,
                "-movflags", "+faststart",
                proxy_mp4_path
            ]
            res = subprocess.run(
                proxy_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=600,
                creationflags=creation_flags
            )
            if res.returncode == 0 and os.path.exists(proxy_mp4_path) and os.path.getsize(proxy_mp4_path) > 0:
                project.proxy_url = f"{settings.MEDIA_URL}proxies/{project.owner_id}/{project.id}/proxy.mp4"
                project.proxy_status = "completed"
                project.save(update_fields=["proxy_url", "proxy_status"])
                logger.info(f"360p MP4 proxy built successfully for project {project_id}")
            else:
                logger.warning(f"360p MP4 proxy exited with code {res.returncode} for project {project_id}")
        except Exception as pe:
            logger.error(f"360p MP4 proxy generation failed for project {project_id}: {pe}")

        # If long-form video (> 1 hour), also dispatch HLS proxy for multi-bitrate streaming
        if (project.duration_seconds or 0.0) > 3600:
            try:
                dispatch_async(generate_hls_proxy, project.id)
            except Exception as he:
                logger.warning(f"HLS proxy dispatch skipped for project {project_id}: {he}")
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
def generate_filmstrip_task(project_id):
    """
    Background celery task: Generates WebP filmstrip thumbnails from the 360p proxy MP4
    (or original if proxy not ready). Density: ~1 frame every 5s, capped at 240 frames, 160px wide.
    """
    import math
    import os
    from django.conf import settings
    from common.compression_service import EduMiCompressionService

    try:
        project = VideoProject.objects.get(pk=project_id)
        dur = project.duration_seconds or 0.0
        if dur <= 0:
            return

        proxy_dir = os.path.join(settings.MEDIA_ROOT, 'proxies', str(project.owner_id), str(project.id))
        proxy_mp4 = os.path.join(proxy_dir, 'proxy.mp4')
        input_path = proxy_mp4 if (project.proxy_status == 'completed' and os.path.exists(proxy_mp4) and os.path.getsize(proxy_mp4) > 0) else project.original_file.path

        filmstrip_dir = os.path.join(proxy_dir, 'filmstrip')
        os.makedirs(filmstrip_dir, exist_ok=True)

        expected_count = min(240, max(12, int(math.ceil(dur / 5.0))))

        EduMiCompressionService.generate_filmstrip_thumbnails(
            input_path,
            filmstrip_dir,
            count=expected_count,
            thumb_width=160,
            quality=75,
            duration=dur
        )
        logger.info(f"Filmstrip generated for project {project_id}: {expected_count} frames at 160px WebP.")
    except Exception as e:
        logger.error(f"Filmstrip generation failed for project {project_id}: {e}")
@shared_task
def generate_waveform_task(project_id):
    """
    Background celery task: Runs FFmpeg to extract mono 8 kHz audio,
    computes ~1 peak per 50ms window (400 samples), and saves waveform.json
    next to the proxy files for instant zero-lag timeline visualization.
    """
    import os
    import json
    import array
    import subprocess
    from django.conf import settings
    from cameras.ffmpeg_helpers import get_ffmpeg_binary

    try:
        project = VideoProject.objects.get(pk=project_id)
        if not project.has_audio:
            logger.info(f"Skipping waveform generation for project {project_id}: no audio track.")
            return

        media_file = project.working_file or project.original_file
        if not media_file or not os.path.exists(media_file.path):
            logger.warning(f"Waveform generation skipped for project {project_id}: media file not found.")
            return

        proxy_dir = os.path.join(settings.MEDIA_ROOT, 'proxies', str(project.owner_id), str(project.id))
        os.makedirs(proxy_dir, exist_ok=True)
        waveform_path = os.path.join(proxy_dir, 'waveform.json')

        ffmpeg_bin = get_ffmpeg_binary()
        cmd = [
            ffmpeg_bin, "-y",
            "-i", media_file.path,
            "-vn",
            "-ac", "1",
            "-ar", "8000",
            "-f", "s16le",
            "pipe:1"
        ]

        creation_flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) if os.name == "nt" else 0
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags
        )

        samples_per_peak = 400  # 50ms at 8000 Hz = 400 samples
        bytes_per_chunk = samples_per_peak * 2  # 16-bit PCM = 2 bytes/sample
        peaks = []
        max_seen = 1

        while True:
            raw_bytes = proc.stdout.read(bytes_per_chunk)
            if not raw_bytes:
                break
            sample_arr = array.array('h')
            sample_arr.frombytes(raw_bytes)
            if sample_arr:
                peak_val = max(abs(s) for s in sample_arr)
                if peak_val > max_seen:
                    max_seen = peak_val
                peaks.append(peak_val)

        proc.stdout.close()
        proc.wait()

        norm_factor = max_seen if max_seen > 0 else 32767
        normalized_peaks = [round(p / norm_factor, 3) for p in peaks]

        result_data = {
            "status": "ready",
            "sample_rate": 8000,
            "window_ms": 50,
            "duration": project.duration_seconds or 0.0,
            "peaks": normalized_peaks
        }

        with open(waveform_path, "w", encoding="utf-8") as wf:
            json.dump(result_data, wf)

        logger.info(f"Waveform generation completed for project {project_id}: {len(normalized_peaks)} peaks saved.")
    except Exception as e:
        logger.error(f"Waveform generation failed for project {project_id}: {e}")

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

        # M3 Winner: Fast 360p Ultrafast Proxy (sub-100ms canvas scrubbing)
        from common.compression_service import EduMiCompressionService
        ok = EduMiCompressionService.generate_hls_proxy_stream(input_path, playlist_path)
        if not ok or not os.path.exists(playlist_path):
            raise Exception("FFmpeg HLS proxy generation failed or output playlist not found")

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

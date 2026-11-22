"""
Shared utility functions for video editing views.
Phase 4.1 refactor.
"""
import os
import json
import subprocess
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.files import File
from ..models import VideoProject, EditOperation
from .. import ffmpeg_utils
from common.validators import (
    check_uploaded_file,
    sanitize_filename,
    get_file_extension,
    get_safe_temp_upload_dir,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_AUDIO_EXTENSIONS,
    MAX_VIDEO_SIZE,
    MAX_AUDIO_SIZE,
    MAX_IMAGE_SIZE,
)


@login_required
def serve_media_ranges(request, path):
    """
    Streaming media endpoint for video editor timelines.
    Consolidated into protected_media_serve to enforce global access controls.
    """
    from common.media_views import protected_media_serve
    return protected_media_serve(request, path)


def _get_owned_project(request, pk):
    """Get project if user is owner or superuser, else None."""
    project = get_object_or_404(VideoProject, pk=pk)
    if not request.user.is_superuser and project.owner_id != request.user.id:
        return None
    return project


def _apply_new_working_file(project, output_path, operation_type, description, parameters=None, clear_proxies=True, update_metadata=True, save_operation_file=True):
    """Helper to update project after a successful edit operation."""
    import shutil
    # Deactivate previous working file if it was generated
    old_working = project.working_file.path if project.working_file else None

    # Attach new working file
    with open(output_path, 'rb') as f:
        filename = os.path.basename(output_path)
        project.working_file.save(filename, File(f), save=False)

    # Clear old proxies if requested
    if clear_proxies:
        proxy_dir = os.path.join(settings.MEDIA_ROOT, "proxies", str(project.owner_id), str(project.pk))
        if os.path.exists(proxy_dir):
            shutil.rmtree(proxy_dir, ignore_errors=True)
        project.proxy_url = ""
        project.proxy_status = "none"

    # Update metadata
    if update_metadata:
        try:
            meta = ffmpeg_utils.get_metadata(output_path)
            project.duration_seconds = meta.get("duration", project.duration_seconds)
            project.width = meta.get("width", project.width)
            project.height = meta.get("height", project.height)
            project.has_audio = meta.get("has_audio", project.has_audio)
        except Exception:
            pass

    project.status = "ready"
    project.save()

    # Log operation
    EditOperation.objects.create(
        project=project,
        operation_type=operation_type,
        description=description,
        parameters=parameters or {},
        video_file=project.working_file if save_operation_file else None,
    )

    # Clean up temp file
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except OSError:
            pass

    # Clean up old generated file (don't delete original)
    if old_working and old_working != project.original_file.path and os.path.exists(old_working):
        try:
            os.remove(old_working)
        except OSError:
            pass


def extract_video_metadata(file_path):
    """Extract video metadata using ffprobe"""
    from cameras.ffmpeg_helpers import get_ffmpeg_binary
    try:
        ffmpeg_bin = get_ffmpeg_binary()
        ffprobe_path = ffmpeg_bin.replace('ffmpeg.exe', 'ffprobe.exe').replace('ffmpeg', 'ffprobe')
        cmd = [
            ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        metadata = {
            'duration': float(data.get('format', {}).get('duration', 0)),
            'size': int(data.get('format', {}).get('size', 0)),
            'format_name': data.get('format', {}).get('format_name', ''),
        }
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                metadata['width'] = stream.get('width')
                metadata['height'] = stream.get('height')
                metadata['codec'] = stream.get('codec_name')
                break
        return metadata
    except Exception:
        return None


def generate_thumbnail(video_path, output_path, timestamp=1.0):
    """Generate thumbnail from video at specified timestamp"""
    from cameras.ffmpeg_helpers import get_ffmpeg_binary
    try:
        ffmpeg_path = get_ffmpeg_binary()
        cmd = [
            ffmpeg_path,
            '-y',
            '-ss', str(timestamp),
            '-i', video_path,
            '-vframes', '1',
            '-vf', 'scale=320:-1',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False

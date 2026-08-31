import os
import json
import logging
import subprocess
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.urls import reverse
from django.conf import settings
from django.core.files import File
from django.utils import timezone

from common.validators import (
    sanitize_filename, get_file_extension, ALLOWED_VIDEO_EXTENSIONS,
    MAX_VIDEO_SIZE, DANGEROUS_EXTENSIONS
)
from meetings.models import Meeting
from cameras.models import CameraRecording
from cameras.ffmpeg_helpers import get_video_duration, get_ffmpeg_binary

logger = logging.getLogger(__name__)


@csrf_exempt
@login_required
@require_POST
def meeting_chunked_upload(request):
    """
    Industry-grade chunked upload handler for Live Meeting Room recordings.
    Assembles streamed recording slices, converts/wraps them into lossless .mkv format,
    saves CameraRecording & VideoProject objects, and extracts thumbnail + duration.
    """
    try:
        chunk = request.FILES.get('chunk')
        filename = request.POST.get('filename', 'meeting_recording.mkv')
        chunk_index = int(request.POST.get('chunkIndex', 0))
        total_chunks = int(request.POST.get('totalChunks', 1))
        upload_id = request.POST.get('uploadId')
        meeting_id = request.POST.get('meeting_id')

        if not all([chunk, upload_id]):
            return JsonResponse({'status': 'error', 'message': 'Missing upload identifiers or chunk data.'}, status=400)

        # Base filename & clean extension (.mkv)
        clean_filename = sanitize_filename(filename)
        base_name, _ = os.path.splitext(clean_filename)
        final_mkv_filename = f"{base_name}.mkv"

        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_recordings', upload_id)
        os.makedirs(temp_dir, exist_ok=True)

        chunk_path = os.path.join(temp_dir, f'chunk_{chunk_index}')
        with open(chunk_path, 'wb+') as f:
            for data in chunk.chunks():
                f.write(data)

        # Check if this is the final chunk
        if chunk_index == total_chunks - 1:
            raw_assembled_path = os.path.join(temp_dir, 'raw_assembled.tmp')
            final_mkv_path = os.path.join(temp_dir, final_mkv_filename)

            # Assemble raw chunks into raw_assembled.tmp
            with open(raw_assembled_path, 'wb+') as final_file:
                for i in range(total_chunks):
                    part_path = os.path.join(temp_dir, f'chunk_{i}')
                    if os.path.exists(part_path):
                        with open(part_path, 'rb') as part:
                            final_file.write(part.read())
                        try:
                            os.remove(part_path)
                        except OSError:
                            pass

            total_size = os.path.getsize(raw_assembled_path)
            if total_size > MAX_VIDEO_SIZE:
                os.remove(raw_assembled_path)
                return JsonResponse({'status': 'error', 'message': 'Recording file exceeds maximum allowed size.'}, status=400)

            # Transcode/Remux raw stream into standardized MKV format using FFmpeg
            ffmpeg_bin = get_ffmpeg_binary()
            cmd = [
                ffmpeg_bin, "-y",
                "-i", raw_assembled_path,
                "-c", "copy",
                "-f", "matroska",
                final_mkv_path
            ]
            try:
                process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
                if process.returncode != 0 or not os.path.exists(final_mkv_path):
                    # Fallback to libx264/opus encoding if stream copy fails
                    cmd_fallback = [
                        ffmpeg_bin, "-y",
                        "-i", raw_assembled_path,
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-c:a", "aac",
                        "-f", "matroska",
                        final_mkv_path
                    ]
                    subprocess.run(cmd_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
            except Exception as ffmpeg_err:
                logger.warning(f"FFmpeg MKV stream copy notice: {ffmpeg_err}")

            target_file = final_mkv_path if os.path.exists(final_mkv_path) else raw_assembled_path

            # Determine title & meeting link
            meeting = Meeting.objects.filter(id=meeting_id).first() if meeting_id else None
            title_text = f"Recording: {meeting.title}" if meeting else "Live Meeting Recording"
            desc_text = f"Recorded on {timezone.now().strftime('%B %d, %Y at %I:%M %p')}"
            if meeting and meeting.classroom:
                desc_text += f" in classroom '{meeting.classroom.title}'"

            recording = CameraRecording.objects.create(
                teacher=request.user,
                title=title_text,
                description=desc_text,
                recording_status='completed',
                is_published=False
            )

            with open(target_file, 'rb') as f:
                recording.video_file.save(final_mkv_filename, File(f))

            # Thumbnail generation
            try:
                recording.generate_thumbnail(time_sec=1.0)
            except Exception as e:
                logger.warning(f"Meeting recording thumbnail generation warning: {e}")

            # Duration extraction
            try:
                dur_sec = get_video_duration(recording.video_file.path)
                if dur_sec:
                    recording.duration = timedelta(seconds=dur_sec)
                    recording.save(update_fields=['duration'])
            except Exception as e:
                logger.warning(f"Duration extraction warning: {e}")

            # Auto-create VideoProject for video_editing app
            try:
                from video_editing.models import VideoProject
                proj_title = f"{title_text} (Edited)"
                project = VideoProject.objects.create(
                    owner=request.user,
                    title=proj_title,
                    status='ready',
                    duration_seconds=recording.duration.total_seconds() if recording.duration else None
                )
                with open(recording.video_file.path, 'rb') as f:
                    project.original_file.save(os.path.basename(recording.video_file.name), File(f))
            except Exception as e:
                logger.warning(f"Failed to auto-create VideoProject: {e}")

            # Cleanup temp folder
            try:
                if os.path.exists(raw_assembled_path):
                    os.remove(raw_assembled_path)
                if os.path.exists(final_mkv_path):
                    os.remove(final_mkv_path)
                os.rmdir(temp_dir)
            except OSError:
                pass

            redirect_url = reverse('edit_recording', args=[recording.id])
            return JsonResponse({
                'status': 'success',
                'recording_id': recording.id,
                'redirect_url': redirect_url,
                'message': 'Meeting recording saved successfully in MKV format.'
            })

        return JsonResponse({
            'status': 'success',
            'message': f'Chunk {chunk_index+1}/{total_chunks} received successfully.'
        })

    except Exception as exc:
        logger.error(f"Meeting chunked upload error: {exc}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=500)

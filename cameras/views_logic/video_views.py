
import os
import re
import logging
from django.shortcuts import render, redirect, get_object_or_404, reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
from django.db.models import Q
from django.core.files import File
from django.conf import settings
from ..models import Camera, CameraRecording, RecordingChunk
from .utils import get_video_stream

from common.validators import (
    check_uploaded_file,
    sanitize_filename,
    get_file_extension,
    validate_file_signature,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    DANGEROUS_EXTENSIONS,
    MAX_VIDEO_SIZE,
    MAX_IMAGE_SIZE,
)

logger = logging.getLogger(__name__)

User = get_user_model()


@login_required
def stream_video(request, recording_id):
    """View to serve video files in chunks (YouTube style) - Optimized for 4hr+ videos"""
    recording = get_object_or_404(CameraRecording, id=recording_id)

    # Check permissions
    if not (request.user.is_superuser or
            recording.teacher == request.user or
            (recording.is_published and hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'student')):
        return HttpResponse("Unauthorized", status=403)

    file_path = recording.video_file.path
    if not os.path.exists(file_path) or os.path.isdir(file_path):
        return HttpResponse("Video file not found", status=404)

    size = os.path.getsize(file_path)
    range_header = request.META.get('HTTP_RANGE', None)

    content_type = 'video/mp4'
    if file_path.endswith('.mkv'):
        content_type = 'video/x-matroska'
    elif file_path.endswith('.webm'):
        content_type = 'video/webm'

    if range_header:
        # Standard Range request parsing
        match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else size - 1

            # Ensure boundaries
            start = max(0, min(start, size - 1))
            end = max(start, min(end, size - 1))

            content_length = end - start + 1

            response = StreamingHttpResponse(
                get_video_stream(file_path, start, end),
                status=206,
                content_type=content_type
            )
            response['Content-Range'] = f'bytes {start}-{end}/{size}'
            response['Accept-Ranges'] = 'bytes'
            response['Content-Length'] = str(content_length)
            return response

    # Default to full file streaming if no range or invalid range
    response = StreamingHttpResponse(get_video_stream(file_path, 0, size - 1), content_type=content_type)
    response['Accept-Ranges'] = 'bytes'
    response['Content-Length'] = str(size)
    return response


@login_required
def upload_video(request):
    """View for teachers to upload video lectures"""
    logger.info("Upload video view called!")
    logger.info(f"Method: {request.method}")
    if not (request.user.is_superuser or (hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'teacher')):
        return redirect('dashboard')

    if request.method == 'POST':
        logger.info("POST request received!")
        logger.debug(f"POST keys: {request.POST.keys()}")
        logger.debug(f"FILES keys: {request.FILES.keys()}")
        
        try:
            title = request.POST.get('title')
            description = request.POST.get('description')
            video_file = request.FILES.get('video')
            thumbnail_file = request.FILES.get('thumbnail')
            camera_id = request.POST.get('camera')

            if not title:
                return JsonResponse({'status': 'error', 'message': 'Title is required.'})
                
            if not video_file:
                return JsonResponse({'status': 'error', 'message': 'Please select a video file.'})

            # Validate video file
            is_valid, err_msg = check_uploaded_file(
                video_file,
                allowed_extensions=ALLOWED_VIDEO_EXTENSIONS,
                max_size=MAX_VIDEO_SIZE,
                file_category="video"
            )
            if not is_valid:
                return JsonResponse({'status': 'error', 'message': err_msg}, status=400)

            # Validate thumbnail if provided
            if thumbnail_file:
                is_thumb_valid, thumb_err = check_uploaded_file(
                    thumbnail_file,
                    allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
                    max_size=MAX_IMAGE_SIZE,
                    file_category="thumbnail"
                )
                if not is_thumb_valid:
                    return JsonResponse({'status': 'error', 'message': f"Thumbnail error: {thumb_err}"}, status=400)

            camera = None
            if camera_id:
                camera = Camera.objects.filter(id=camera_id).first()

            recording = CameraRecording.objects.create(
                teacher=request.user,
                camera=camera,
                title=title,
                description=description,
                video_file=video_file,
                recording_status='completed',
                is_published=False  # Teacher must manually publish
            )
            logger.info(f"Created recording with ID: {recording.id}")
            
            if thumbnail_file:
                recording.thumbnail = thumbnail_file
                recording.save()
                logger.info("Thumbnail saved!")
            else:
                # Auto-generate a thumbnail if none provided
                logger.info("Generating thumbnail...")
                recording.generate_thumbnail(time_sec=1.0)

            # Auto-extract duration from uploaded video
            try:
                from ..ffmpeg_helpers import get_video_duration
                from datetime import timedelta
                duration_sec = get_video_duration(recording.video_file.path)
                if duration_sec:
                    recording.duration = timedelta(seconds=duration_sec)
                    recording.save()
                    logger.info(f"Set duration of uploaded video to {recording.duration}")
            except Exception as e:
                logger.warning(f"Failed to auto-extract uploaded video duration: {e}")
            
            logger.info("Upload successful!")
            redirect_url = reverse('edit_recording', args=[recording.id])
            return JsonResponse({'status': 'success', 'redirect_url': redirect_url})
            
        except Exception as e:
            logger.error(f"Error in upload: {str(e)}")
            logger.exception("Upload exception traceback")
            return JsonResponse({'status': 'error', 'message': f'Error: {str(e)}'})

    cameras = Camera.objects.all() if request.user.is_superuser else Camera.objects.filter(camerapermission__teacher=request.user)
    return render(request, 'cameras/upload_video.html', {'cameras': cameras})


@csrf_exempt
@login_required
def camera_chunked_upload(request):
    """Chunked video upload for lecture recordings with background tab & retry resilience."""
    if request.method == 'POST':
        chunk = request.FILES.get('chunk')
        filename = request.POST.get('filename')
        chunk_index = int(request.POST.get('chunkIndex', 0))
        total_chunks = int(request.POST.get('totalChunks', 1))
        upload_id = request.POST.get('uploadId')
        title = request.POST.get('title', 'Untitled Lecture')
        description = request.POST.get('description', '')
        camera_id = request.POST.get('camera')
        thumbnail_file = request.FILES.get('thumbnail')

        if not all([chunk, filename, upload_id]):
            return JsonResponse({'status': 'error', 'message': 'Missing chunk data'}, status=400)

        clean_filename = sanitize_filename(filename)
        ext = get_file_extension(clean_filename)

        if ext in DANGEROUS_EXTENSIONS:
            return JsonResponse({'status': 'error', 'message': f"Files with extension '.{ext}' are not allowed."}, status=400)

        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            allowed_str = ', '.join([f'.{e}' for e in sorted(ALLOWED_VIDEO_EXTENSIONS)])
            return JsonResponse({'status': 'error', 'message': f"Unsupported video type '.{ext}'. Allowed types: {allowed_str}"}, status=400)

        if thumbnail_file:
            is_thumb_valid, thumb_err = check_uploaded_file(
                thumbnail_file,
                allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
                max_size=MAX_IMAGE_SIZE,
                file_category="thumbnail"
            )
            if not is_thumb_valid:
                return JsonResponse({'status': 'error', 'message': f"Thumbnail error: {thumb_err}"}, status=400)

        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_uploads', upload_id)
        os.makedirs(temp_dir, exist_ok=True)

        chunk_path = os.path.join(temp_dir, f'chunk_{chunk_index}')
        with open(chunk_path, 'wb+') as f:
            for data in chunk.chunks():
                f.write(data)

        if chunk_index == total_chunks - 1:
            # Final chunk received, assemble video file
            final_file_path = os.path.join(temp_dir, clean_filename)
            with open(final_file_path, 'wb+') as final_file:
                for i in range(total_chunks):
                    part_path = os.path.join(temp_dir, f'chunk_{i}')
                    if os.path.exists(part_path):
                        with open(part_path, 'rb') as part:
                            final_file.write(part.read())
                        os.remove(part_path)

            # Check assembled file size and signature
            total_size = os.path.getsize(final_file_path)
            if total_size > MAX_VIDEO_SIZE:
                os.remove(final_file_path)
                return JsonResponse({'status': 'error', 'message': f"Total file size exceeds limit of {MAX_VIDEO_SIZE // (1024*1024)} MB."}, status=400)

            with open(final_file_path, 'rb') as f:
                header = f.read(512)
            is_sig_valid, sig_err = validate_file_signature(header, ext)
            if not is_sig_valid:
                os.remove(final_file_path)
                return JsonResponse({'status': 'error', 'message': f"Invalid video file content: {sig_err}"}, status=400)

            camera = None
            if camera_id:
                camera = Camera.objects.filter(id=camera_id).first()

            recording = CameraRecording(
                teacher=request.user,
                camera=camera,
                title=title,
                description=description,
                recording_status='completed',
                is_published=False
            )
            with open(final_file_path, 'rb') as final_file:
                recording.video_file.save(clean_filename, File(final_file))

            if thumbnail_file:
                recording.thumbnail = thumbnail_file
                recording.save()
            else:
                try:
                    recording.generate_thumbnail(time_sec=1.0)
                except Exception as e:
                    logger.warning(f"Failed to generate thumbnail: {e}")

            try:
                from ..ffmpeg_helpers import get_video_duration
                from datetime import timedelta
                duration_sec = get_video_duration(recording.video_file.path)
                if duration_sec:
                    recording.duration = timedelta(seconds=duration_sec)
                    recording.save()
            except Exception as e:
                logger.warning(f"Failed to extract video duration: {e}")

            os.remove(final_file_path)
            try:
                os.rmdir(temp_dir)
            except OSError:
                pass

            redirect_url = reverse('edit_recording', args=[recording.id])
            return JsonResponse({'status': 'success', 'redirect_url': redirect_url})

        return JsonResponse({'status': 'success', 'message': f'Chunk {chunk_index+1}/{total_chunks} received'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)



@login_required
def recordings_folder(request):
    """View to show recordings organized in a folder-like structure with date subfolders"""
    from django.utils.text import slugify

    if request.user.is_superuser:
        # Only show recordings that actually have a file
        recordings = CameraRecording.objects.exclude(video_file='').order_by('-created_at')
    else:
        recordings = CameraRecording.objects.filter(teacher=request.user).exclude(video_file='').order_by('-created_at')

    # Group by camera, then by date
    from collections import defaultdict
    folders = defaultdict(lambda: defaultdict(list))

    for rec in recordings:
        camera_name = rec.camera.name if rec.camera else "Uploaded Videos"
        date_str = rec.created_at.strftime('%Y-%m-%d')
        folders[camera_name][date_str].append(rec)

    # Convert to a regular dict with slugified IDs for the template
    processed_folders = []
    for cam_name, dates in folders.items():
        processed_folders.append({
            'name': cam_name,
            'id': slugify(cam_name),
            'dates': dict(dates),
            'count': sum(len(v) for v in dates.values())
        })

    context = {
        'folders': processed_folders,
        'total_count': recordings.count(),
    }
    return render(request, 'cameras/recordings_folder.html', context)


@login_required
def manage_recordings(request):
    """View for teachers to manage their recordings and uploads"""
    if not (request.user.is_superuser or (hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'teacher')):
        return redirect('dashboard')

    recordings = CameraRecording.objects.filter(teacher=request.user).order_by('-created_at')
    return render(request, 'cameras/manage_recordings.html', {'recordings': recordings})


@login_required
def toggle_recording_publish(request, recording_id):
    """Toggle the published status of a recording"""
    recording = get_object_or_404(CameraRecording, id=recording_id)

    if not (request.user.is_superuser or recording.teacher == request.user):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    recording.is_published = not recording.is_published
    recording.save()

    return JsonResponse({
        'status': 'success',
        'is_published': recording.is_published,
        'message': f'Recording {"published" if recording.is_published else "hidden"}'
    })


@login_required
def edit_recording(request, recording_id):
    """Bridge view to edit a camera recording in the existing Video Editor app"""
    from cameras.models import CameraRecording, RecordingChunk
    from video_editing.models import VideoProject, EditOperation
    from video_editing import ffmpeg_utils
    from django.core.files import File
    from django.contrib import messages
    import tempfile
    import uuid
    import subprocess

    recording = get_object_or_404(CameraRecording, id=recording_id)
    if not (request.user.is_superuser or recording.teacher == request.user):
        return redirect('dashboard')

    project_title = f"Edit - {recording.title}"
    
    # Check if a project already exists with this title/owner to avoid duplicate conversions
    existing_project = VideoProject.objects.filter(owner=request.user, title=project_title).first()
    if existing_project:
        url = reverse("project_detail", kwargs={"pk": existing_project.pk})
        return redirect(f"{url}?recording_id={recording.id}")

    # Create a new VideoProject
    project = VideoProject.objects.create(
        owner=request.user,
        title=project_title,
        status="processing"
    )

    try:
        if recording.is_chunked:
            # Stitch chunks together
            chunks = RecordingChunk.objects.filter(recording=recording).order_by('sequence')
            if not chunks.exists():
                raise Exception("No video chunks found for this recording.")

            with tempfile.NamedTemporaryFile(suffix='.ts', delete=False) as temp_video:
                for chunk in chunks:
                    if chunk.data:
                        temp_video.write(chunk.data)
                temp_video_path = temp_video.name

            # Remux / copy it to an MP4 so it plays natively in the browser editor
            mp4_path = temp_video_path.replace('.ts', '.mp4')
            ffmpeg_bin = ffmpeg_utils.settings.FFMPEG_BINARY
            cmd = [
                ffmpeg_bin, '-y',
                '-i', temp_video_path,
                '-c', 'copy',
                mp4_path
            ]
            subprocess.run(cmd, capture_output=True, check=True)

            with open(mp4_path, 'rb') as f:
                project.original_file.save(f"{uuid.uuid4().hex}.mp4", File(f), save=False)

            try:
                os.remove(temp_video_path)
                os.remove(mp4_path)
            except:
                pass
        else:
            if not recording.video_file or not os.path.exists(recording.video_file.path):
                raise Exception("Original recording video file not found.")

            file_path = recording.video_file.path
            # If MKV, remux to MP4 for native browser playback
            if file_path.endswith('.mkv'):
                mp4_path = file_path.replace('.mkv', '_remux.mp4')
                ffmpeg_bin = ffmpeg_utils.settings.FFMPEG_BINARY
                cmd = [
                    ffmpeg_bin, '-y',
                    '-i', file_path,
                    '-c', 'copy',
                    mp4_path
                ]
                subprocess.run(cmd, capture_output=True, check=True)
                with open(mp4_path, 'rb') as f:
                    project.original_file.save(f"{uuid.uuid4().hex}.mp4", File(f), save=False)
                try: os.remove(mp4_path)
                except: pass
            else:
                with open(file_path, 'rb') as f:
                    filename = os.path.basename(file_path)
                    project.original_file.save(filename, File(f), save=False)

        # Get metadata
        meta = ffmpeg_utils.probe(project.original_file.path)
        # Parse duration
        duration = float(meta.get('format', {}).get('duration', 0.0))
        # Parse size
        width = None
        height = None
        has_audio = True
        for stream in meta.get('streams', []):
            if stream.get('codec_type') == 'video':
                width = int(stream.get('width', 0))
                height = int(stream.get('height', 0))
            elif stream.get('codec_type') == 'audio':
                has_audio = True

        project.duration_seconds = duration
        project.width = width
        project.height = height
        project.has_audio = has_audio
        project.status = "ready"
        project.save()

        # Log upload operation
        EditOperation.objects.create(
            project=project,
            operation_type="upload",
            description=f"Loaded recording: {recording.title}",
        )

        messages.success(request, "Recording loaded into Video Editor successfully.")
        url = reverse("project_detail", kwargs={"pk": project.pk})
        return redirect(f"{url}?recording_id={recording.id}")

    except Exception as e:
        logger.error(f"Error preparing video for editing: {e}", exc_info=True)
        project.status = "error"
        project.error_message = str(e)
        project.save()
        messages.error(request, f"Error preparing video for editing: {str(e)}")
        return redirect("manage_recordings")


@login_required
def watch_recording(request, recording_id):
    """Watch a recorded lecture"""
    recording = get_object_or_404(CameraRecording, id=recording_id)
    recording.views_count += 1
    recording.save(update_fields=['views_count'])

    # Check permissions: owner or published
    if not (recording.is_published or recording.teacher == request.user or request.user.is_superuser):
        return HttpResponse("Unauthorized", status=403)

    # Recommended videos (same teacher or same camera)
    recommended = CameraRecording.objects.filter(
        is_published=True
    ).exclude(id=recording_id).filter(
        Q(teacher=recording.teacher) | Q(camera=recording.camera)
    ).order_by('-created_at')[:5]

    context = {
        'recording': recording,
        'recommended': recommended
    }

    if recording.is_chunked:
        context['playlist_url'] = reverse('recording_playlist', args=[recording.id])

    return render(request, 'cameras/watch_recording.html', context)


@login_required
def stream_recording_chunk(request, recording_id, sequence):
    """Serve a specific video chunk from the database"""
    chunk = get_object_or_404(RecordingChunk, recording_id=recording_id, sequence=sequence)

    # Check permission for the recording
    recording = chunk.recording
    if not (recording.is_published or recording.teacher == request.user or request.user.is_superuser):
        return HttpResponse("Unauthorized", status=403)

    return HttpResponse(chunk.data, content_type='video/mp2t')


@login_required
def recording_playlist(request, recording_id):
    """Generate HLS playlist for a chunked recording"""
    recording = get_object_or_404(CameraRecording, id=recording_id)

    if not (recording.is_published or recording.teacher == request.user or request.user.is_superuser):
        return HttpResponse("Unauthorized", status=403)

    chunks = RecordingChunk.objects.filter(recording=recording).order_by('sequence')

    playlist = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-TARGETDURATION:10",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD"
    ]

    for chunk in chunks:
        playlist.append(f"#EXTINF:{chunk.duration},")
        chunk_url = reverse('stream_chunk', args=[recording.id, chunk.sequence])
        playlist.append(chunk_url)

    playlist.append("#EXT-X-ENDLIST")

    return HttpResponse("\n".join(playlist), content_type='application/vnd.apple.mpegurl')


@login_required
@require_http_methods(["POST"])
def delete_recording(request, recording_id):
    """Allow teachers to delete their own recordings"""
    recording = get_object_or_404(CameraRecording, id=recording_id)
    
    if not (request.user.is_superuser or recording.teacher == request.user):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
        
    recording.delete()
    return JsonResponse({'status': 'success', 'message': 'Recording deleted successfully'})


@login_required
def teacher_profile(request, teacher_id):
    """Show all lectures and live status for a specific teacher"""
    teacher = get_object_or_404(User, id=teacher_id)

    live_cameras = Camera.objects.filter(live_teacher=teacher, is_live=True)
    recordings = CameraRecording.objects.filter(teacher=teacher, is_published=True).order_by('-created_at')

    return render(request, 'cameras/teacher_profile.html', {
        'target_teacher': teacher,
        'live_cameras': live_cameras,
        'recordings': recordings
    })


@login_required
@require_http_methods(["POST"])
def update_recording_edit(request, recording_id):
    """Update trim times for a recording"""
    recording = get_object_or_404(CameraRecording, id=recording_id)
    
    if not (request.user.is_superuser or recording.teacher == request.user):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    edit_start_time = request.POST.get('edit_start_time', 0.0)
    edit_end_time = request.POST.get('edit_end_time', None)
    
    try:
        recording.edit_start_time = float(edit_start_time) if edit_start_time is not None else 0.0
        if edit_end_time:
            recording.edit_end_time = float(edit_end_time)
        else:
            recording.edit_end_time = None
        recording.save()
        
        return JsonResponse({'status': 'success', 'message': 'Edit settings saved'})
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Invalid time values'}, status=400)


@login_required
@require_http_methods(["POST"])
def apply_recording_trim(request, recording_id):
    """Apply the trim to the video"""
    recording = get_object_or_404(CameraRecording, id=recording_id)
    
    if not (request.user.is_superuser or recording.teacher == request.user):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    success = recording.apply_trim()
    if success:
        return JsonResponse({'status': 'success', 'message': 'Video trimmed successfully'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Failed to trim video'}, status=500)


@login_required
@require_http_methods(["POST"])
def generate_recording_thumbnail(request, recording_id):
    """Generate a thumbnail for the recording"""
    recording = get_object_or_404(CameraRecording, id=recording_id)
    
    if not (request.user.is_superuser or recording.teacher == request.user):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    time_sec = float(request.POST.get('time_sec', 1.0))
    thumbnail_url = None
    if recording.generate_thumbnail(time_sec=time_sec):
        thumbnail_url = recording.thumbnail.url
    
    return JsonResponse({
        'status': 'success',
        'message': 'Thumbnail generated',
        'thumbnail_url': thumbnail_url
    })


@login_required
@require_http_methods(["POST"])
def like_recording(request, recording_id):
    """Increment likes for a recording."""
    recording = get_object_or_404(CameraRecording, id=recording_id)
    recording.likes_count += 1
    recording.save(update_fields=['likes_count'])
    return JsonResponse({'status': 'success', 'likes_count': recording.likes_count})


@login_required
def recording_analytics(request):
    """YouTube Studio-like Analytics dashboard for teachers."""
    if not (request.user.is_superuser or (hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'teacher')):
        return redirect('dashboard')
        
    # Get all recordings by this teacher
    recordings = CameraRecording.objects.filter(teacher=request.user)
    
    # Calculate statistics
    total_views = sum(rec.views_count for rec in recordings)
    total_likes = sum(rec.likes_count for rec in recordings)
    total_videos = recordings.count()
    
    # Get top viewed recordings
    top_recordings = recordings.order_by('-views_count')[:5]
    
    # Prepare chart data
    chart_data = []
    for rec in recordings.order_by('-views_count')[:10]:
        chart_data.append({
            'title': rec.title,
            'views': rec.views_count,
            'likes': rec.likes_count,
        })
        
    context = {
        'total_views': total_views,
        'total_likes': total_likes,
        'total_videos': total_videos,
        'top_recordings': top_recordings,
        'chart_data': chart_data,
        'recordings': recordings,
    }
    return render(request, 'cameras/recording_analytics.html', context)


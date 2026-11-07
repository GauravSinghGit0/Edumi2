
import logging
import os
import time
import threading
from typing import Optional
import cv2
import numpy as np
from django.shortcuts import render, redirect, get_object_or_404, reverse
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.contrib.auth import get_user_model
from ..models import Camera, CameraRecording, CameraPermission
from django.db.models import Q
from .utils import is_admin, can_view_camera, broadcast_live_status
from ..recording_engine import recording_engine

logger = logging.getLogger(__name__)

User = get_user_model()

# Centralized CameraStreamer and CameraManager from camera_service
from camera_service.camera_api.views.streamer import CameraStreamer, CameraManager, camera_manager


async def _generate_frames(streamer, camera, full_url, quality, camera_id):
    """Yield MJPEG boundary frames; handles stale stream detection."""
    import asyncio
    throttles = {'4k': 0.033, 'high': 0.033, 'med': 0.05, 'low': 0.1}
    delay = throttles.get(quality, 0.05)

    logger.info(f"Starting stream generation for camera {camera_id}, quality {quality}")
    frame_count = 0

    try:
        while True:
            frame = streamer.get_adaptive_frame(quality)
            frame_count += 1
            
            if frame_count % 20 == 0:
                logger.info(f"Sent frame {frame_count}, size: {len(frame)} bytes")

            if frame:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                await asyncio.sleep(delay)
            else:
                logger.warning(f"No frame to send for camera {camera_id}")
                await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Streaming error camera {camera_id}: {e}", exc_info=True)

# --- End of Inline Code ---


@login_required
def mobile_mic(request, camera_id):
    """Dedicated page for using a mobile phone as a wireless microphone"""
    camera = get_object_or_404(Camera, id=camera_id)
    return render(request, 'cameras/control_room/mobile_mic.html', {
        'camera': camera,
        'user': request.user
    })


@login_required
def teacher_camera_dashboard(request):
    """Dashboard for teachers to see assigned cameras (RTSP and Mobile)"""
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher':
        return redirect('student_dashboard' if hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'student' else 'home')

    camera_ids = CameraPermission.objects.filter(teacher=request.user).values_list('camera_id', flat=True)
    all_cameras = list(Camera.objects.filter(id__in=camera_ids, is_active=True))

    return render(request, 'cameras/control_room/teacher_dashboard.html', {
        'cameras': all_cameras,
    })


@login_required
def teacher_control_room(request, camera_id):
    """Teacher control room for live streaming and recording"""
    camera = get_object_or_404(Camera, id=camera_id)

    # Check permission
    if not camera.has_permission(request.user):
        return redirect('teacher_camera_dashboard')

    # We NO LONGER mark camera as live here.
    # It will be marked live only when the teacher explicitly clicks "Start Live Stream"

    # Get linked meeting if any (camera can be linked to a meeting for student tracking)
    linked_meeting = None
    student_count = 0
    active_participants = []
    if camera.livekit_room:
        try:
            from meetings.models import Meeting, MeetingParticipant
            linked_meeting = Meeting.objects.filter(meeting_code=camera.livekit_room).first()
            if linked_meeting:
                student_count = MeetingParticipant.objects.filter(meeting=linked_meeting, is_active=True).count()
                active_participants = list(linked_meeting.participants.filter(is_active=True).values_list('user__username', flat=True)[:10])
        except Exception as e:
            logger.warning(f"Error getting linked meeting participants: {e}")

    # Check if recording is in progress
    is_recording, recording_start_time = recording_engine.is_recording(camera.id, request.user.id)

    # Auto-heal: if the DB says camera is live but there's no active recording engine session,
    # the previous stream was never cleanly stopped (e.g. server restart). Reset the flag.
    if camera.is_live and not is_recording:
        # Check the recording engine to see if we have any active stream sessions
        active_session = recording_engine.get_active_session(camera.id)
        if not active_session:
            camera.is_live = False
            camera.save(update_fields=['is_live'])

    # Use the camera-feed proxy (port 8003 with in-process fallback)
    camera_feed_base = reverse('camera_feed', args=[camera.id])

    context = {
        'camera': camera,
        'qualities': ['360p', '480p', '720p', '1080p', '4K'],
        'default_quality': '1080p',
        'linked_meeting': linked_meeting,
        'student_count': student_count,
        'active_participants': active_participants,
        'is_live': camera.is_live,
        'is_recording': is_recording,
        'recording_start_time': recording_start_time.isoformat() if recording_start_time else None,
        'camera_feed_base': camera_feed_base,
    }
    return render(request, 'cameras/control_room/teacher_control_room.html', context)


@login_required
def update_zoom(request, camera_id):
    """Update digital zoom level for a streaming camera."""
    camera = get_object_or_404(Camera, id=camera_id)
    if not camera.has_permission(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)

    try:
        full_url = camera.get_full_rtsp_url()
        streamer = camera_manager.get_streamer(camera.id, full_url)
        if streamer.set_zoom(request.GET.get('level', 1.0), request.GET.get('x'), request.GET.get('y')):
            return JsonResponse({'status': 'success', 'zoom': streamer.zoom_level,
                                 'x': streamer.zoom_center_x, 'y': streamer.zoom_center_y})
        return JsonResponse({'status': 'error', 'message': 'Invalid zoom level'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def start_streaming(request, camera_id):
    """Teacher starts the live stream explicitly"""
    camera = get_object_or_404(Camera, id=camera_id)
    if not camera.has_permission(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied'})

    camera.is_live = True
    camera.live_teacher = request.user
    camera.save()

    # Broadcast status change
    broadcast_live_status(camera, 'started')

    return JsonResponse({'status': 'success', 'message': 'Live stream started'})


@login_required
def stop_streaming(request, camera_id):
    """Teacher stops the live stream"""
    camera = get_object_or_404(Camera, id=camera_id)
    if camera.live_teacher == request.user:
        camera.is_live = False
        camera.live_teacher = None
        camera.save()

        # Broadcast status change
        broadcast_live_status(camera, 'stopped')

        return JsonResponse({'status': 'success', 'message': 'Live stream stopped'})
    return JsonResponse({'status': 'error', 'message': 'Not the live teacher'})


@login_required
def live_participants(request, camera_id):
    """Get live participants for a camera's linked meeting"""
    camera = get_object_or_404(Camera, id=camera_id)

    # Check permission
    if not camera.has_permission(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if camera.livekit_room:
        try:
            from meetings.models import Meeting, MeetingParticipant
            meeting = Meeting.objects.filter(meeting_code=camera.livekit_room).first()
            if meeting:
                participants = meeting.participants.filter(is_active=True).select_related('user')
                participant_list = [
                    {'username': p.user.username, 'user_id': p.user.id}
                    for p in participants
                ]
                return JsonResponse({
                    'count': len(participant_list),
                    'participants': participant_list
                })
        except Exception as e:
            pass

    return JsonResponse({'count': 0, 'participants': []})


@login_required
def student_lecture_list(request):
    """List all available live sessions and recorded lectures for students"""
    from meetings.models import Meeting, ClassroomMembership

    query = request.GET.get('q', '')
    teacher_id = request.GET.get('teacher', '')

    # Get classrooms where user is an approved member
    my_classroom_ids = ClassroomMembership.objects.filter(
        student=request.user,
        status='approved'
    ).values_list('classroom_id', flat=True)

    # 1. Filter Live Cameras
    # We need to hide cameras that are linked to classrooms the student isn't in
    live_sessions = Camera.objects.filter(is_live=True).select_related('live_teacher')

    # Identify rooms that are linked to classrooms
    classroom_rooms = Meeting.objects.filter(
        classroom__isnull=False,
        status='live'
    ).values('meeting_code', 'classroom_id')

    room_to_classroom = {r['meeting_code']: r['classroom_id'] for r in classroom_rooms}

    filtered_live = []
    for cam in live_sessions:
        if cam.livekit_room in room_to_classroom:
            # This camera is in a classroom session
            if room_to_classroom[cam.livekit_room] in my_classroom_ids:
                filtered_live.append(cam)
        else:
            # Standalone camera or not linked to an active classroom meeting
            filtered_live.append(cam)

    # 2. Filter Recordings
    # The Recorded Lectures section has been removed from this page.
    # Videos are now strictly confined to their respective classrooms.
    recordings = []

    if query:
        # Re-filter the filtered_live list for query
        filtered_live = [
            cam for cam in filtered_live
            if query.lower() in cam.name.lower() or
               (cam.live_teacher and query.lower() in cam.live_teacher.username.lower())
        ]

    if teacher_id:
        filtered_live = [cam for cam in filtered_live if str(cam.live_teacher_id) == str(teacher_id)]

    # Get list of teachers for filtering
    teachers = User.objects.filter(userprofile__user_type='teacher')

    return render(request, 'cameras/recordings/student_lecture_list.html', {
        'live_sessions': filtered_live,
        'recordings': recordings,
        'teachers': teachers,
        'query': query,
        'selected_teacher': teacher_id
    })


@login_required
def watch_live(request, camera_id):
    """Watch a live lecture (Student / Admin View)"""
    camera = get_object_or_404(Camera, id=camera_id)
    if not can_view_camera(request.user, camera):
        return redirect('student_lecture_list')

    context = {
        'camera': camera,
        'teacher': camera.live_teacher if hasattr(camera, 'live_teacher') else None,
    }
    return render(request, 'cameras/control_room/watch_live.html', context)


@login_required
def start_camera_recording(request, camera_id):
    """Start recording a camera feed using FFmpeg engine"""
    camera = get_object_or_404(Camera, id=camera_id)
    if not camera.has_permission(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied'})

    quality = request.POST.get('quality', '720p')
    audio_source = request.POST.get('audio_source', 'pc')  # 'pc', 'remote', or 'camera'
    success, message = recording_engine.start_recording(camera, request.user, quality, audio_source)

    if success:
        return JsonResponse({'status': 'success', 'message': f'Recording started in {quality}'})
    else:
        return JsonResponse({'status': 'error', 'message': message})


@login_required
def stop_camera_recording(request, camera_id):
    """Stop recording and prepare for publishing"""
    camera = get_object_or_404(Camera, id=camera_id)
    success, recording_id = recording_engine.stop_recording(camera.id, request.user.id)

    if success:
        rec = None
        try:
            from cameras.models import CameraRecording
            rec = CameraRecording.objects.filter(id=recording_id).first()
        except Exception as e:
            logger.warning(f"Error fetching recording: {e}")
        
        video_url = None
        is_chunked = False
        if rec:
            is_chunked = rec.is_chunked
            if rec.is_chunked:
                video_url = reverse('recording_playlist', args=[rec.id])
            elif rec.video_file:
                video_url = rec.video_file.url

        return JsonResponse({
            'status': 'success',
            'recording_id': recording_id,
            'video_url': video_url,
            'is_chunked': is_chunked,
            'message': 'Recording stopped and being processed'
        })
    else:
        return JsonResponse({'status': 'error', 'message': 'No active recording found'})


@login_required
def camera_feed_proxy(request, camera_id):
    """Stream adaptive-bitrate MJPEG feed directly from our camera manager."""
    quality = request.GET.get('q', 'med')
    # Map quality param names to internal keys
    quality_map = {'4k': '4k', 'high': 'high', '1080p': 'high', '720p': 'med', '480p': 'med', '360p': 'low'}
    quality = quality_map.get(quality, quality)

    try:
        camera = get_object_or_404(Camera, id=camera_id)
        # Admins can always view; teachers need permission; others need is_live
        from .utils import is_admin, can_view_camera
        if not can_view_camera(request.user, camera):
            return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)

        full_url = camera.get_full_rtsp_url()
        # force_restart if URL changed or streamer is stale
        streamer = camera_manager.get_streamer(camera.id, full_url)
        response = StreamingHttpResponse(
            _generate_frames(streamer, camera, full_url, quality, camera_id),
            content_type='multipart/x-mixed-replace; boundary=frame',
        )
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        response['X-Accel-Buffering'] = 'no'
        return response
    except Exception as e:
        logger.error(f"Camera {camera_id} feed error: {e}")
        return JsonResponse({'error': 'Camera not found'}, status=404)


@login_required
def clear_stream_cache(request, camera_id):
    """Admin endpoint to force-restart a stale camera streamer."""
    from .utils import is_admin
    if not is_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
    try:
        camera = get_object_or_404(Camera, id=camera_id)
        full_url = camera.get_full_rtsp_url()
        camera_manager.get_streamer(camera.id, full_url, force_restart=True)
        return JsonResponse({'status': 'success', 'message': f'Stream cache cleared for camera {camera_id}'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def publish_recording(request):
    """Publish a finished recording with title, description and optional thumbnail"""
    if request.method == 'POST':
        recording_id = request.POST.get('recording_id')
        title = request.POST.get('title')
        description = request.POST.get('description')
        is_draft = request.POST.get('is_draft') == 'true'
        thumbnail = request.FILES.get('thumbnail')

        try:
            rec = CameraRecording.objects.get(id=recording_id, teacher=request.user)
            rec.title = title
            rec.description = description
            if thumbnail:
                rec.thumbnail = thumbnail
            rec.is_published = not is_draft
            rec.save()
            
            status_msg = 'Lecture saved as draft' if is_draft else 'Lecture published successfully'
            return JsonResponse({'status': 'success', 'message': status_msg})
        except CameraRecording.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Recording not found'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request'})


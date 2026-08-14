"""
camera_service/camera_api/views/rtsp_views.py
Django views for RTSP camera streaming, zoom control, and diagnostics.
"""
import os
import time
import logging

import cv2
from django.http import StreamingHttpResponse, JsonResponse

from .streamer import camera_manager

logger = logging.getLogger('camera_api')


def list_cameras(request):
    """List all active cameras."""
    try:
        from cameras.models import Camera
        cameras = Camera.objects.filter(is_active=True).values('id', 'name', 'is_active')
        return JsonResponse({'cameras': list(cameras)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def camera_feed(request, camera_id):
    """Stream adaptive-bitrate MJPEG feed from an RTSP camera."""
    quality = request.GET.get('q', 'med')
    try:
        from cameras.models import Camera
        camera = Camera.objects.get(id=camera_id)
        full_url = camera.get_full_rtsp_url()
        streamer = camera_manager.get_streamer(camera.id, full_url)

        response = StreamingHttpResponse(
            _generate_frames(streamer, camera, full_url, quality, camera_id),
            content_type='multipart/x-mixed-replace; boundary=frame',
        )
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['X-Accel-Buffering'] = 'no'
        return response
    except Exception as e:
        logger.error(f"Camera {camera_id} not found: {e}")
        return JsonResponse({'error': 'Camera not found'}, status=404)


def update_camera_zoom(request, camera_id):
    """Update digital zoom level for a streaming camera."""
    try:
        from cameras.models import Camera
        camera = Camera.objects.get(id=camera_id)
        streamer = camera_manager.get_streamer(camera.id, camera.get_full_rtsp_url())
        if streamer.set_zoom(request.GET.get('level', 1.0), request.GET.get('x'), request.GET.get('y')):
            return JsonResponse({'status': 'success', 'zoom': streamer.zoom_level,
                                 'x': streamer.zoom_center_x, 'y': streamer.zoom_center_y})
        return JsonResponse({'status': 'error', 'message': 'Invalid zoom level'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def test_camera(request, camera_id):
    """Test camera connection with OpenCV and optional FFprobe diagnostics."""
    import subprocess
    try:
        from cameras.models import Camera
        camera = Camera.objects.get(id=camera_id)
        full_url = camera.get_full_rtsp_url()
        results = []

        for transport in ['tcp', 'udp']:
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = f'rtsp_transport;{transport}'
            cap = cv2.VideoCapture(full_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)
            if cap.isOpened():
                ret, frame = cap.read()
                status = ('success' if ret and frame is not None else 'opened_but_no_frame')
                entry = {'method': f'OpenCV {transport.upper()}', 'status': status}
                if ret and frame is not None:
                    entry['frame_size'] = f"{frame.shape[1]}x{frame.shape[0]}"
                results.append(entry)
            else:
                results.append({'method': f'OpenCV {transport.upper()}', 'status': 'failed_to_open'})
            cap.release()

        success_methods = [r for r in results if r['status'] == 'success']
        return JsonResponse({
            'camera_id': camera_id, 'camera_name': camera.name,
            'results': results,
            'overall_status': 'success' if success_methods else 'failed',
            'working_methods': [r['method'] for r in success_methods],
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ── private helpers ───────────────────────────────────────────────────────────

async def _generate_frames(streamer, camera, full_url, quality, camera_id):
    """Yield MJPEG boundary frames; handles stale stream detection."""
    import asyncio
    throttles = {'4k': 0.033, 'high': 0.033, 'med': 0.05, 'low': 0.1}
    delay = throttles.get(quality, 0.05)

    # Wait for streamer to have a frame (placeholder or real), but don't give up!
    wait_count = 0
    while streamer.get_frame() is None and wait_count < 300:
        await asyncio.sleep(0.1)
        wait_count += 1

    # Even if no frame yet, keep trying instead of returning
    frame_count = 0
    try:
        while True:
            frame = streamer.get_adaptive_frame(quality)
            if frame:
                frame_count += 1
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                await asyncio.sleep(delay)
            else:
                await asyncio.sleep(0.1)  # Wait longer if no frame available
    except GeneratorExit:
        logger.info(f"Client disconnected from camera {camera_id} after {frame_count} frames")
    except Exception as e:
        logger.error(f"Streaming error camera {camera_id}: {e}")

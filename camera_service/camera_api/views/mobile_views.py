"""
camera_service/camera_api/views/mobile_views.py
Django views for mobile camera (DroidCam/IP Webcam) streaming and testing.
"""
import logging
import time

from django.http import StreamingHttpResponse, JsonResponse

from .mobile_streamer import mobile_camera_manager

logger = logging.getLogger('camera_api')


def mobile_camera_feed(request, mobile_camera_id):
    """Stream MJPEG feed from a mobile camera with head-tracking overlay."""
    try:
        from mobile_cameras.models import MobileCamera
        mobile_camera = MobileCamera.objects.get(id=mobile_camera_id)
        stream_url = mobile_camera.get_stream_url()
        streamer = mobile_camera_manager.get_streamer(mobile_camera_id, stream_url)

        response = StreamingHttpResponse(
            _generate_mobile_frames(streamer, mobile_camera_id),
            content_type='multipart/x-mixed-replace; boundary=frame',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response
    except Exception as e:
        logger.error(f"Mobile camera {mobile_camera_id} error: {e}")
        return JsonResponse({'error': str(e)}, status=404)


def test_mobile_camera(request, mobile_camera_id):
    """Test mobile camera HTTP connection and return JSON status."""
    import requests as req_lib
    try:
        from mobile_cameras.models import MobileCamera
        mobile_camera = MobileCamera.objects.get(id=mobile_camera_id)
        url = mobile_camera.get_stream_url()
        resp = req_lib.get(url, timeout=5, stream=True)
        if resp.status_code == 200:
            return JsonResponse({'status': 'success', 'url': url, 'camera': mobile_camera.name})
        return JsonResponse({'status': 'error', 'message': f'HTTP {resp.status_code}'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ── private helpers ───────────────────────────────────────────────────────────

def _generate_mobile_frames(streamer, camera_id):
    """Yield MJPEG boundary frames from a MobileCameraStreamer."""
    wait = 0
    while streamer.get_frame() is None and wait < 100:
        time.sleep(0.1)
        wait += 1

    if streamer.get_frame() is None:
        yield b'--frame\r\nContent-Type: text/plain\r\n\r\nERROR: No frame received\r\n'
        return

    try:
        while True:
            frame = streamer.get_frame()
            if frame:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
            time.sleep(0.05)
    except GeneratorExit:
        logger.info(f"Client disconnected from mobile camera {camera_id}")
    except Exception as e:
        logger.error(f"Mobile stream error {camera_id}: {e}")

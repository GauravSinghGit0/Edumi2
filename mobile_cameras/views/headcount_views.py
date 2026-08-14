"""
mobile_cameras/views/headcount_views.py
Live headcount streaming view with OpenCV face + motion detection.
"""
import logging
from collections import deque

import cv2
import numpy as np
import requests as req_lib

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse

from mobile_cameras.models import MobileCamera
from .utils import can_view_mobile_camera

logger = logging.getLogger('mobile_cameras')


@login_required
def mobile_camera_headcount_feed(request, mobile_camera_id):
    """Stream mobile camera feed with per-frame face + motion head-count overlay."""
    mobile_camera = get_object_or_404_safe(mobile_camera_id)
    if mobile_camera is None:
        return JsonResponse({'error': 'Camera not found'}, status=404)
    if not can_view_mobile_camera(request.user, mobile_camera):
        return JsonResponse({'error': 'You do not have permission to view this camera'}, status=403)

    response = StreamingHttpResponse(
        _generate_headcount_frames(mobile_camera),
        content_type='multipart/x-mixed-replace; boundary=frame',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


# ── helpers ──────────────────────────────────────────────────────────────────

def get_object_or_404_safe(mobile_camera_id):
    """Return MobileCamera or None (avoids importing get_object_or_404 at module level)."""
    from django.shortcuts import get_object_or_404
    from mobile_cameras.models import MobileCamera
    try:
        return get_object_or_404(MobileCamera, id=mobile_camera_id)
    except Exception:
        return None


def _generate_headcount_frames(mobile_camera):
    """Generator: connect to MJPEG stream, annotate frames, yield multipart JPEG."""
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    bg_sub = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=25, detectShadows=True)
    detection_history = deque(maxlen=5)
    last_detections = []
    last_count = 0
    frame_count = 0

    try:
        url = mobile_camera.get_stream_url()
        logger.info(f"Connecting to mobile camera headcount feed: {url}")
        response = req_lib.get(url, stream=True, timeout=30)

        if response.status_code != 200:
            logger.error(f"Failed to connect: HTTP {response.status_code}")
            yield b'--frame\r\nContent-Type: text/plain\r\n\r\nERROR: Cannot connect to mobile camera\r\n'
            return

        buf = bytes()
        for chunk in response.iter_content(chunk_size=16384):
            buf += chunk
            while True:
                a, b = buf.find(b'\xff\xd8'), buf.find(b'\xff\xd9')
                if a == -1 or b == -1 or b <= a:
                    break
                jpg, buf = buf[a:b + 2], buf[b + 2:]
                try:
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        continue
                    frame_count += 1
                    display = frame.copy()

                    if frame_count % 3 == 0:
                        last_detections, last_count = _detect(frame, face_cascade, bg_sub, detection_history)

                    _draw_overlay(display, last_detections, last_count, frame.shape)
                    ret, jpeg = cv2.imencode('.jpg', display, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if ret:
                        yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n'
                except Exception:
                    continue

    except Exception as e:
        logger.error(f"Headcount feed error: {e}")
        yield b'--frame\r\nContent-Type: text/plain\r\n\r\nERROR: Stream error\r\n'


def _detect(frame, face_cascade, bg_sub, history):
    """Run face + motion detection on a downscaled frame; return (detections, stable_count)."""
    small = cv2.resize(frame, (320, 240))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    sx, sy = frame.shape[1] / 320, frame.shape[0] / 240

    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=3, minSize=(30, 30))
    fg_mask = bg_sub.apply(small)
    _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    detections = [{'bbox': (int(x * sx), int(y * sy), int(w * sx), int(h * sy)), 'type': 'face'} for (x, y, w, h) in faces]
    for c in contours:
        if cv2.contourArea(c) > 300:
            mx, my, mw, mh = cv2.boundingRect(c)
            detections.append({'bbox': (int(mx * sx), int(my * sy), int(mw * sx), int(mh * sy)), 'type': 'motion'})

    history.append(len([d for d in detections if d['type'] == 'face']))
    count = int(np.median(list(history))) if history else 0
    return detections, count


def _draw_overlay(frame, detections, count, shape):
    """Draw bounding boxes and HUD on frame in-place."""
    for det in detections:
        x, y, w, h = det['bbox']
        color = (0, 255, 0) if det['type'] == 'face' else (0, 255, 255)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (220, 50), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    cv2.putText(frame, f"HEADS: {count}", (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
    cv2.circle(frame, (shape[1] - 25, 25), 8, (0, 0, 255), -1)
    cv2.putText(frame, "LIVE", (shape[1] - 75, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

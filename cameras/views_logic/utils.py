
import logging
from urllib.parse import quote
from django.db import transaction
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger('cameras')


from common.media_views import file_iterator

def get_video_stream(file_path, start, end):
    """Generator to stream video in chunks with support for Range requests"""
    return file_iterator(file_path, offset=start, length=(end - start + 1))

from common.utils import is_admin, is_ajax_request


def can_view_camera(user, camera):
    """Check if user can view a camera"""
    if is_admin(user):
        return True

    # Teachers with explicit CameraPermission can always view their assigned cameras
    # (both in control room and when the camera is live)
    if hasattr(user, 'userprofile') and user.userprofile.user_type == 'teacher':
        return camera.has_permission(user)

    # If the camera is live, students and other authenticated users can view it
    if camera.is_live and camera.is_active:
        return True

    return False


def test_rtsp_paths(ip, port, username, password):
    """Test common RTSP paths to find the working one"""
    import cv2
    common_paths = [
        '/axis-media/media.amp',
        '/Streaming/Channels/101',
        '/Streaming/Channels/1',
        '/cam/realmonitor?channel=1&subtype=0',
        '/cam/realmonitor',
        '/live',
        '/live/ch0',
        '/h264',
        '/h264Preview_01_main',
        '/stream',
        '/stream1',
        '/video',
        '/1',
        '/11',
        '/av0_0',
        '/mpeg4',
        '/media/video1',
        '/onvif1',
        '/ch0',
        '/ch0_0.264',
        '/ch01.264',
        '/',
    ]

    for path in common_paths:
        if username and password:
            safe_user = quote(username)
            safe_pass = quote(password)
            rtsp_url = f"rtsp://{safe_user}:{safe_pass}@{ip}:{port}{path}"
        else:
            rtsp_url = f"rtsp://{ip}:{port}{path}"

        try:
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000)

            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()

                if ret and frame is not None:
                    return path, rtsp_url
            else:
                cap.release()
        except Exception as e:
            continue

    return None, None


def broadcast_live_status(camera, status):
    """Helper to broadcast live status changes to all connected users"""
    channel_layer = get_channel_layer()
    if channel_layer:
        def _send():
            async_to_sync(channel_layer.group_send)(
                "public_notifications",
                {
                    "type": "send_notification",
                    "data": {
                        "type": "live_status_change",
                        "camera_id": camera.id,
                        "camera_name": camera.name,
                        "teacher_name": camera.live_teacher.username if camera.live_teacher else "",
                        "status": status,  # 'started' or 'stopped'
                    }
                }
            )
        transaction.on_commit(_send)




def test_mobile_camera_paths(ip, port, username, password):
    """Probe common MJPEG/HTTP paths to find the one that returns a live stream."""
    import requests
    from requests.auth import HTTPBasicAuth
    common_paths = ['/video', '/mjpegfeed', '/videofeed', '/cam_1.mjpg',
                    '/stream', '/video.mjpg', '/video.cgi', '/']
    for path in common_paths:
        if username and password:
            url = f"http://{username}:{password}@{ip}:{port}{path}"
            auth = HTTPBasicAuth(username, password)
        else:
            url = f"http://{ip}:{port}{path}"
            auth = None
        try:
            resp = requests.get(url, timeout=3, stream=True, auth=auth)
            if resp.status_code == 200:
                ct = resp.headers.get('Content-Type', '')
                if any(x in ct for x in ('image', 'video', 'multipart')):
                    return path, url
        except Exception:
            continue
    return None, None


def parse_camera_url(url):
    """Parse a full camera URL into its components dict."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    camera_type = 'other'
    stream_path = parsed.path or '/'
    if '/video' in stream_path:
        camera_type = 'ip_webcam'
    elif '/mjpegfeed' in stream_path:
        camera_type = 'droidcam'
    port = parsed.port
    if not port:
        port = 554 if parsed.scheme == 'rtsp' else 8080
    return {
        'ip_address': parsed.hostname or '',
        'port': port,
        'username': parsed.username or '',
        'password': parsed.password or '',
        'stream_path': stream_path,
        'camera_type': camera_type,
    }

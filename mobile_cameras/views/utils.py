"""
mobile_cameras/views/utils.py
Helper functions and URL utilities shared across mobile camera views.
"""
import logging
from urllib.parse import urlparse

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger('mobile_cameras')


def is_admin(user):
    """Return True if the user is a superuser/admin."""
    if not (user and user.is_authenticated):
        return False
    return user.is_superuser or getattr(user, 'is_staff', False) or (hasattr(user, 'userprofile') and user.userprofile.user_type == 'admin')


def can_view_mobile_camera(user, mobile_camera):
    """Return True if the user is allowed to see this camera's feed."""
    if is_admin(user):
        return True
    if hasattr(user, 'userprofile'):
        if user.userprofile.user_type == 'teacher':
            return mobile_camera.has_permission(user)
        if user.userprofile.user_type == 'student':
            return mobile_camera.is_active
    return False


def test_mobile_camera_paths(ip, port, username, password):
    """Probe common MJPEG/HTTP paths to find the one that returns a live stream."""
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
        'ip_address': parsed.hostname,
        'port': port,
        'username': parsed.username or '',
        'password': parsed.password or '',
        'stream_path': stream_path,
        'camera_type': camera_type,
    }

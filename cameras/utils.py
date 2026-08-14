
import os
import re
import logging
import threading
import time
from typing import Optional
from urllib.parse import urlparse, quote
from django.utils import timezone
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.db.models import Avg, Max, Min, Count, Q
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Camera, CameraPermission, HeadCountLog, HeadCountSession, CameraRecording

User = get_user_model()

logger = logging.getLogger('cameras')


def get_video_stream(file_path, start, end):
    """Generator to stream video in chunks with support for Range requests"""
    chunk_size = 1024 * 1024  # 1MB chunks for responsiveness

    with open(file_path, 'rb') as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            data = f.read(read_size)
            if not data:
                break
            yield data
            remaining -= read_size


def is_admin(user):
    """Check if user is admin"""
    if user.is_authenticated:
        if user.is_superuser:
            return True
    return False


def can_view_camera(user, camera):
    """Check if user can view a camera"""
    if is_admin(user):
        return True

    # If the camera is live, any authenticated user can view it (for student lectures)
    if camera.is_live:
        return True

    # If not live, teachers can only view cameras they have explicit permission for (control room access)
    if hasattr(user, 'userprofile') and user.userprofile.user_type == 'teacher':
        return camera.has_permission(user)

    # Students can ONLY view live cameras
    if hasattr(user, 'userprofile') and user.userprofile.user_type == 'student':
        return camera.is_live and camera.is_active

    return False


def test_rtsp_paths(ip, port, username, password):
    """Test common RTSP paths to find the working one"""
    import cv2
    common_paths = [
        '/live',
        '/stream',
        '/h264',
        '/video',
        '/cam/realmonitor',
        '/Streaming/Channels/101',
        '/1',
        '/11',
        '/av0_0',
        '/mpeg4',
        '/media/video1',
        '/onvif1',
        '/ch0',
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

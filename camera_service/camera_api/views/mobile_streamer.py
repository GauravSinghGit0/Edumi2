"""
camera_service/camera_api/views/mobile_streamer.py
MobileCameraStreamer and MobileCameraManager for HTTP/MJPEG mobile cameras.
"""
import time
import threading
import logging
from typing import Optional

import cv2
import numpy as np
import requests

logger = logging.getLogger('camera_api')


class MobileCameraStreamer:
    """HTTP/MJPEG streamer for mobile phones running DroidCam / IP Webcam."""

    def __init__(self, mobile_camera_id, stream_url):
        self.mobile_camera_id = mobile_camera_id
        self.stream_url = stream_url
        self.frame: Optional[bytes] = None
        self.running: bool = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        self.last_access = time.time()
        self.last_frame: Optional[np.ndarray] = None

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._update, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def _update(self):
        """Background thread: fetch MJPEG frames, annotate with head tracking, store."""
        while self.running:
            if time.time() - self.last_access > 90:
                break
            try:
                resp = requests.get(self.stream_url, stream=True, timeout=5)
                if resp.status_code == 200:
                    buf = bytes()
                    for chunk in resp.iter_content(chunk_size=1024):
                        if not self.running:
                            break
                        buf += chunk
                        a, b = buf.find(b'\xff\xd8'), buf.find(b'\xff\xd9')
                        if a != -1 and b != -1:
                            jpg, buf = buf[a:b + 2], buf[b + 2:]
                            try:
                                img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                                if img is not None:
                                    img_out = self._annotate(img)
                                    with self.lock:
                                        self.last_frame = img_out.copy()
                                    med = cv2.resize(img_out, (640, 360), interpolation=cv2.INTER_NEAREST)
                                    ret, jpeg = cv2.imencode('.jpg', med, [cv2.IMWRITE_JPEG_QUALITY, 60])
                                    if ret:
                                        with self.lock:
                                            self.frame = jpeg.tobytes()
                            except Exception as e:
                                logger.error(f"Frame processing error: {e}")
                else:
                    logger.error(f"HTTP {resp.status_code} from mobile camera {self.mobile_camera_id}")
                    time.sleep(5)
            except Exception as e:
                logger.error(f"Mobile streamer error: {e}")
                time.sleep(5)

    def _annotate(self, img):
        """Run head tracking annotation; return annotated frame (or original on error)."""
        try:
            from cameras.head_count_service import head_count_manager
            _, _, annotated, _, _ = head_count_manager.detector.detect_heads(img, track_movement=True)
            return annotated
        except Exception as e:
            logger.error(f"Mobile tracking error: {e}")
            return img

    def get_frame(self):
        self.last_access = time.time()
        with self.lock:
            return self.frame


class MobileCameraManager:
    """Registry of active MobileCameraStreamer instances."""
    _lock = threading.Lock()
    _streamers = {}

    @classmethod
    def get_streamer(cls, mobile_camera_id, stream_url):
        with cls._lock:
            if mobile_camera_id not in cls._streamers or not cls._streamers[mobile_camera_id].running:
                s = MobileCameraStreamer(mobile_camera_id, stream_url)
                s.start()
                cls._streamers[mobile_camera_id] = s
            return cls._streamers[mobile_camera_id]

    @classmethod
    def stop_streamer(cls, mobile_camera_id):
        with cls._lock:
            if mobile_camera_id in cls._streamers:
                cls._streamers[mobile_camera_id].stop()
                del cls._streamers[mobile_camera_id]


mobile_camera_manager = MobileCameraManager()

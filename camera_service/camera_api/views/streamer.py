"""
camera_service/camera_api/views/streamer.py
CameraStreamer and CameraManager classes for RTSP cameras.
Handles connection, reconnection, digital zoom, and adaptive frame encoding.
"""
import os
import time
import threading
import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger('camera_api')

os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
cv2.ocl.setUseOpenCL(True)
if cv2.ocl.haveOpenCL():
    logger.info("OpenCL Hardware Acceleration ENABLED")
else:
    logger.warning("OpenCL Hardware Acceleration NOT available")

RTSP_OPEN_TIMEOUT = 4000
RTSP_READ_TIMEOUT = 4000
RTSP_RECONNECT_DELAY = 2
RTSP_MAX_RECONNECT = 10


class CameraStreamer:
    """Non-blocking RTSP camera streamer with auto-reconnection and digital zoom."""

    def __init__(self, camera_id, rtsp_url):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame: Optional[bytes] = None
        self.running: bool = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        self.last_access = time.time()
        self.last_frame: Optional[np.ndarray] = None
        self.last_frame_time = 0
        self.connection_attempts = 0
        self.zoom_level = 1.0
        self.zoom_center_x = 0.5
        self.zoom_center_y = 0.5

    def set_zoom(self, level, x=None, y=None):
        """Update digital zoom level (1.0–5.0) and optional center point."""
        try:
            self.zoom_level = max(1.0, min(5.0, float(level)))
            if x is not None:
                self.zoom_center_x = max(0.0, min(1.0, float(x)))
            if y is not None:
                self.zoom_center_y = max(0.0, min(1.0, float(y)))
            return True
        except Exception:
            return False

    def _apply_zoom(self, frame):
        """Crop and resize frame to simulate digital zoom."""
        if self.zoom_level <= 1.0:
            return frame
        h, w = frame.shape[:2]
        crop_w, crop_h = int(w / self.zoom_level), int(h / self.zoom_level)
        cx, cy = int(w * self.zoom_center_x), int(h * self.zoom_center_y)
        x1 = max(0, min(w - crop_w, cx - crop_w // 2))
        y1 = max(0, min(h - crop_h, cy - crop_h // 2))
        cropped = frame[y1:y1 + crop_h, x1:x1 + crop_w]
        if cv2.ocl.useOpenCL():
            try:
                return cv2.resize(cv2.UMat(cropped), (w, h), interpolation=cv2.INTER_LINEAR).get()
            except Exception:
                pass
        return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._update, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def _connect_camera(self):
        """Try multiple connection strategies and path variations for IP cameras."""
        target_urls = [self.rtsp_url]

        # Auto-probe paths if IP is 10.7.16.48 or credentials needed
        if '10.7.16.48' in self.rtsp_url or '10.7.16.48' in str(self.camera_id):
            target_urls.extend([
                "rtsp://test:dei%4012%4012@10.7.16.48:554/h264Preview_01_main",
                "rtsp://test:dei%4012%4012@10.7.16.48:554/stream1",
                "rtsp://test:dei%4012%4012@10.7.16.48:554/live/ch0",
                "rtsp://test:dei%4012%4012@10.7.16.48:554/",
                "http://test:dei%4012%4012@10.7.16.48/video",
                "http://test:dei%4012%4012@10.7.16.48/mjpeg",
                "http://test:dei%4012%4012@10.7.16.48:8080/video",
                "http://test:dei%4012%4012@10.7.16.48/",
            ])

        # Remove duplicate URLs while keeping order
        seen = set()
        unique_urls = []
        for u in target_urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)

        for current_url in unique_urls:
            is_http = current_url.lower().startswith('http')
            if is_http:
                try:
                    os.environ.pop('OPENCV_FFMPEG_CAPTURE_OPTIONS', None)
                    cap = cv2.VideoCapture(current_url)
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, RTSP_OPEN_TIMEOUT * 2)
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, RTSP_READ_TIMEOUT * 2)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if cap.isOpened():
                        for _ in range(8):
                            ret, frame = cap.read()
                            if ret and frame is not None and frame.size > 0:
                                self.connection_attempts = 0
                                self.rtsp_url = current_url
                                logger.info(f"HTTP camera {self.camera_id} connected: {current_url}")
                                return cap
                            time.sleep(0.3)
                    cap.release()
                except Exception as e:
                    logger.debug(f"HTTP stream attempt failed for {current_url}: {e}")
                continue

            # RTSP camera attempts
            combos = [
                ('tcp', 'rtsp_transport;tcp;stimeout;4000000', 'd3d11va', 'hwaccel;d3d11va'),
                ('tcp', 'rtsp_transport;tcp;stimeout;4000000', 'none', ''),
                ('udp', 'rtsp_transport;udp;stimeout;4000000', 'none', ''),
            ]
            for transport, t_opt, hw_name, hw_opt in combos:
                cap = None
                try:
                    opts = t_opt
                    if hw_opt:
                        opts += f';{hw_opt}'
                    os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = opts
                    cap = cv2.VideoCapture(current_url, cv2.CAP_FFMPEG)
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, RTSP_OPEN_TIMEOUT)
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, RTSP_READ_TIMEOUT)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if cap.isOpened():
                        for _ in range(5):
                            ret, frame = cap.read()
                            if ret and frame is not None and frame.size > 0:
                                self.connection_attempts = 0
                                self.rtsp_url = current_url
                                logger.info(f"RTSP camera {self.camera_id} connected via {current_url} ({transport})")
                                return cap
                            time.sleep(0.2)
                    if cap:
                        cap.release()
                except Exception as e:
                    logger.debug(f"RTSP attempt failed for {current_url}: {e}")
                    if cap:
                        try:
                            cap.release()
                        except Exception:
                            pass

        # Last-resort fallback with no options
        try:
            os.environ.pop('OPENCV_FFMPEG_CAPTURE_OPTIONS', None)
            cap = cv2.VideoCapture(self.rtsp_url)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, RTSP_OPEN_TIMEOUT)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    logger.info(f"Camera {self.camera_id} connected via fallback (no options)")
                    return cap
            cap.release()
        except Exception:
            pass

        logger.warning(f"Camera {self.camera_id}: all connection attempts failed for {self.rtsp_url}")
        return None

    def _generate_placeholder(self):
        """Generate a placeholder frame when no real camera is available."""
        import datetime
        # Create a black background
        height, width = 1080, 1920
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Add some color (Bright Blue for visibility)
        frame[:] = (255, 150, 0) # BGR for Bright Blue
        
        # Add text
        font = cv2.FONT_HERSHEY_SIMPLEX
        text1 = f"Camera {self.camera_id}: Waiting for Feed"
        text2 = f"Time: {datetime.datetime.now().strftime('%H:%M:%S')}"
        
        # Calculate positions
        (w1, h1), _ = cv2.getTextSize(text1, font, 2, 3)
        (w2, h2), _ = cv2.getTextSize(text2, font, 1.5, 2)
        
        x1 = (width - w1) // 2
        y1 = (height + h1) // 2 - 50
        x2 = (width - w2) // 2
        y2 = (height + h2) // 2 + 50
        
        cv2.putText(frame, text1, (x1, y1), font, 2, (255, 255, 255), 3)
        cv2.putText(frame, text2, (x2, y2), font, 1.5, (150, 150, 255), 2)
        
        return frame
    
    def _update(self):
        """Background capture loop — reads frames, applies zoom, encodes JPEG."""
        # Immediately show a placeholder so clients don't get black screen
        placeholder = self._generate_placeholder()
        self.last_frame_time = time.time()
        if self.lock.acquire(blocking=False):
            try:
                self.last_frame = placeholder.copy()
                med = cv2.resize(placeholder, (1280, 720), interpolation=cv2.INTER_LINEAR)
                ret_j, jpeg = cv2.imencode('.jpg', med, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret_j:
                    self.frame = jpeg.tobytes()
            finally:
                self.lock.release()
                
        while self.running:
            if time.time() - self.last_access > 300:  # 5 minutes idle timeout
                break
            if self.cap is None:
                # Try to connect, but if not available, keep showing placeholder
                self.connection_attempts += 1
                self.cap = self._connect_camera()
                if self.cap is None:
                    # Update placeholder time
                    placeholder = self._generate_placeholder()
                    self.last_frame_time = time.time()
                    if self.lock.acquire(blocking=False):
                        try:
                            self.last_frame = placeholder.copy()
                            med = cv2.resize(placeholder, (1280, 720), interpolation=cv2.INTER_LINEAR)
                            ret_j, jpeg = cv2.imencode('.jpg', med, [cv2.IMWRITE_JPEG_QUALITY, 80])
                            if ret_j:
                                self.frame = jpeg.tobytes()
                        finally:
                            self.lock.release()
                    time.sleep(RTSP_RECONNECT_DELAY)
                    continue
            try:
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    self.connection_attempts = 0
                    self.last_frame_time = time.time()
                    frame = self._apply_zoom(frame)
                    if self.lock.acquire(blocking=False):
                        try:
                            self.last_frame = frame.copy()
                            med = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_LINEAR)
                            ret_j, jpeg = cv2.imencode('.jpg', med, [cv2.IMWRITE_JPEG_QUALITY, 80])
                            if ret_j:
                                self.frame = jpeg.tobytes()
                        finally:
                            self.lock.release()
                    time.sleep(0.001)
                else:
                    if self.cap:
                        self.cap.release()
                    self.cap = None
                    time.sleep(RTSP_RECONNECT_DELAY)
            except Exception as e:
                logger.error(f"Camera {self.camera_id} read error: {e}")
                if self.cap:
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                self.cap = None
                time.sleep(RTSP_RECONNECT_DELAY)
        if self.cap:
            self.cap.release()

    def get_frame(self):
        self.last_access = time.time()
        with self.lock:
            return self.frame

    def get_adaptive_frame(self, quality_level='med'):
        """Return frame encoded at requested quality level (4k/high/med/low)."""
        self.last_access = time.time()
        with self.lock:
            if self.last_frame is None:
                return self.frame
            frame = self.last_frame.copy()
        configs = {
            '4k':   {'res': (3840, 2160), 'quality': 90},
            'high': {'res': (1920, 1080), 'quality': 95},
            'med':  {'res': (1280, 720),  'quality': 85},
            'low':  {'res': (640, 360),   'quality': 60},
        }
        cfg = configs.get(quality_level, configs['med'])
        try:
            if cv2.ocl.useOpenCL():
                try:
                    resized = cv2.resize(cv2.UMat(frame), cfg['res'], interpolation=cv2.INTER_LINEAR).get()
                except Exception:
                    resized = cv2.resize(frame, cfg['res'], interpolation=cv2.INTER_LINEAR)
            else:
                resized = cv2.resize(frame, cfg['res'], interpolation=cv2.INTER_LINEAR)
            ret, jpeg = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, cfg['quality']])
            return jpeg.tobytes() if ret else self.frame
        except Exception:
            return self.frame


class CameraManager:
    """Singleton-like registry of active CameraStreamer instances."""
    _lock = threading.Lock()
    _streamers = {}

    @classmethod
    def get_streamer(cls, camera_id, rtsp_url, force_restart=False):
        with cls._lock:
            existing = cls._streamers.get(camera_id)
            # Restart if not exists, if forced, if not running, OR if URL changed
            should_restart = (
                existing is None or 
                force_restart or 
                not existing.running or 
                existing.rtsp_url != rtsp_url
            )
            
            if should_restart:
                if existing:
                    existing.stop()
                s = CameraStreamer(camera_id, rtsp_url)
                s.start()
                cls._streamers[camera_id] = s
            return cls._streamers[camera_id]

    @classmethod
    def stop_streamer(cls, camera_id):
        with cls._lock:
            if camera_id in cls._streamers:
                cls._streamers[camera_id].stop()
                del cls._streamers[camera_id]


camera_manager = CameraManager()

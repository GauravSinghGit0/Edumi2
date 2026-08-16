
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
from .utils import is_admin, broadcast_live_status
from ..recording_engine import recording_engine

logger = logging.getLogger(__name__)

User = get_user_model()

# --- Inline Camera Streamer Code ---
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
        try:
            if cv2.ocl.useOpenCL():
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
        """Try multiple connection strategies based on camera type (RTSP vs HTTP)."""
        RTSP_OPEN_TIMEOUT = 4000
        RTSP_READ_TIMEOUT = 4000

        # Detect camera type from URL scheme
        is_http = self.rtsp_url.lower().startswith('http')

        if is_http:
            # HTTP MJPEG cameras (IP Webcam, DroidCam) — no RTSP options needed
            try:
                os.environ.pop('OPENCV_FFMPEG_CAPTURE_OPTIONS', None)
                cap = cv2.VideoCapture(self.rtsp_url)
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, RTSP_OPEN_TIMEOUT * 2)
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, RTSP_READ_TIMEOUT * 2)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if cap.isOpened():
                    for _ in range(8):
                        ret, frame = cap.read()
                        if ret and frame is not None and frame.size > 0:
                            self.connection_attempts = 0
                            logger.info(f"HTTP camera {self.camera_id} connected: {self.rtsp_url}")
                            return cap
                        time.sleep(0.5)
                cap.release()
            except Exception as e:
                logger.error(f"HTTP camera connection error: {e}")
            return None

        # RTSP cameras — try TCP then UDP
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
                cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, RTSP_OPEN_TIMEOUT)
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, RTSP_READ_TIMEOUT)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if cap.isOpened():
                    for _ in range(5):
                        ret, frame = cap.read()
                        # Accept any valid frame (removed strict brightness check)
                        if ret and frame is not None and frame.size > 0:
                            self.connection_attempts = 0
                            logger.info(f"RTSP camera {self.camera_id} connected via {transport}/{hw_name}")
                            return cap
                        time.sleep(0.3)
                    cap.release()
            except Exception as e:
                logger.error(f"Connection error ({transport}/{hw_name}): {e}")
                if cap:
                    try:
                        cap.release()
                    except Exception:
                        pass

        # Last-resort fallback
        try:
            os.environ.pop('OPENCV_FFMPEG_CAPTURE_OPTIONS', None)
            cap = cv2.VideoCapture(self.rtsp_url)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, RTSP_OPEN_TIMEOUT)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    logger.info(f"Camera {self.camera_id} connected via fallback")
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
        
        # Add some color
        frame[:] = (30, 30, 50)
        
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
                
        RTSP_RECONNECT_DELAY = 2
        while self.running:
            if time.time() - self.last_access > 300:  # 5 minutes idle timeout (was 90s)
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
            if self.frame is None:
                logger.info(f"get_frame: frame is None for camera {self.camera_id}, generating placeholder")
                placeholder = self._generate_placeholder()
                med = cv2.resize(placeholder, (1280, 720), interpolation=cv2.INTER_LINEAR)
                ret_j, jpeg = cv2.imencode('.jpg', med, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret_j:
                    self.frame = jpeg.tobytes()
                    self.last_frame = placeholder.copy()
                    logger.info(f"Generated placeholder for camera {self.camera_id}, size: {len(self.frame)}")
                else:
                    # Absolute fallback: generate a small static jpeg manually
                    self.frame = self._create_simple_jpeg()
                    self.last_frame = placeholder
            return self.frame

    def _create_simple_jpeg(self):
        # Ultra-simple 1x1 red JPEG as absolute fallback
        return (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00\x43\x00'
            b'\x03\x02\x02\x02\x02\x02\x03\x02\x02\x02\x03\x03\x03\x03\x04\x06\x04\x04\x04\x04\x04\x08'
            b'\x06\x06\x05\x06\t\x08\n\n\t\x08\t\t\n\x0c\x0f\x0c\n\x0b\x0e\x0b\t\t\r\x11\r\x0e\x0f\x10'
            b'\x10\x11\x10\n\x0c\x12\x13\x12\x10\x13\x0f\x10\x10\x10\xff\xc0\x00\x0b\x08\x00\x01\x00'
            b'\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x007\x00\xff\xd9'
        )

    def get_adaptive_frame(self, quality_level='med'):
        """Return frame encoded at requested quality level (4k/high/med/low)."""
        self.last_access = time.time()
        frame_to_use = None
        
        with self.lock:
            if self.last_frame is None:
                logger.info(f"get_adaptive_frame: last_frame is None for camera {self.camera_id}, generating placeholder")
                placeholder = self._generate_placeholder()
                self.last_frame = placeholder.copy()
                med = cv2.resize(placeholder, (1280,720), interpolation=cv2.INTER_LINEAR)
                ret_j, jpeg = cv2.imencode('.jpg', med, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret_j:
                    self.frame = jpeg.tobytes()
            
            if self.last_frame is not None:
                frame_to_use = self.last_frame.copy()

        if frame_to_use is None:
            # If no last_frame, use default frame or create a new placeholder
            frame_to_use = self._generate_placeholder()

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
                    resized = cv2.resize(cv2.UMat(frame_to_use), cfg['res'], interpolation=cv2.INTER_LINEAR).get()
                except Exception:
                    resized = cv2.resize(frame_to_use, cfg['res'], interpolation=cv2.INTER_LINEAR)
            else:
                resized = cv2.resize(frame_to_use, cfg['res'], interpolation=cv2.INTER_LINEAR)
                
            ret, jpeg = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, cfg['quality']])
            if ret:
                return jpeg.tobytes()
            else:
                logger.warning(f"Failed to encode jpeg for camera {self.camera_id}, using default frame")
        except Exception as e:
            logger.error(f"Encoding error for camera {self.camera_id}: {e}", exc_info=True)
        
        # Absolute fallback: return self.frame or simple jpeg
        with self.lock:
            if self.frame is not None:
                return self.frame
        return self._create_simple_jpeg()


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
    from mobile_cameras.models import MobileCamera, MobileCameraPermission
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher':
        return redirect('student_dashboard' if hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'student' else 'home')

    # Get RTSP cameras
    camera_ids = CameraPermission.objects.filter(teacher=request.user).values_list('camera_id', flat=True)
    rtsp_cameras = list(Camera.objects.filter(id__in=camera_ids))
    for cam in rtsp_cameras:
        cam.is_mobile = False

    # Get Mobile cameras
    mobile_camera_ids = MobileCameraPermission.objects.filter(teacher=request.user).values_list('mobile_camera_id', flat=True)
    mobile_cameras = list(MobileCamera.objects.filter(id__in=mobile_camera_ids))
    for cam in mobile_cameras:
        cam.is_mobile = True

    # Combine lists
    all_cameras = rtsp_cameras + mobile_cameras

    # Get recent recordings by this teacher
    recent_recordings = CameraRecording.objects.filter(teacher=request.user).order_by('-created_at')[:5]

    return render(request, 'cameras/control_room/teacher_dashboard.html', {
        'cameras': all_cameras,
        'recent_recordings': recent_recordings
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
    # recordings = CameraRecording.objects.filter(is_published=True).select_related('teacher', 'camera')
    # For recordings, if the camera used is traditionally for a classroom, should we hide it?
    # Usually recordings are published by teachers explicitly, but let's stick to the "meetings" logic.
    # If a recording's camera has a livekit_room that belongs to a classroom, maybe check?
    # For now, let's keep recordings as they are unless they have a direct classroom link (which they don't yet).
    recordings = CameraRecording.objects.filter(is_published=True).select_related('teacher', 'camera')

    if query:
        recordings = recordings.filter(
            Q(title__icontains=query) |
            Q(teacher__username__icontains=query) |
            Q(camera__name__icontains=query)
        )
        # Re-filter the filtered_live list for query
        filtered_live = [
            cam for cam in filtered_live
            if query.lower() in cam.name.lower() or
               (cam.live_teacher and query.lower() in cam.live_teacher.username.lower())
        ]

    if teacher_id:
        recordings = recordings.filter(teacher_id=teacher_id)
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
    """Watch a live lecture (Student View)"""
    # Allow admins to view any camera, even if not marked "live"
    if is_admin(request.user):
        camera = get_object_or_404(Camera, id=camera_id)
    else:
        camera = get_object_or_404(Camera, id=camera_id, is_live=True)

    # In a real app, we'd check if the student belongs to the teacher's class

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


"""
Head Counting Service using OpenCV
Detects and counts heads in video frames with green bounding boxes
Includes movement tracking for detected persons
"""
import cv2
import numpy as np
import threading
import time
import logging
import os
from io import BytesIO
from django.core.files.base import ContentFile
from django.utils import timezone
from django.conf import settings
from collections import defaultdict, deque

# Force OpenCV to use TCP transport for RTSP to prevent "bad cseq" and packet loss
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

logger = logging.getLogger('cameras')


class HeadDetector:
    """
    Optimized Head Detection with Frame Skipping & Resolution Control.
    Ensures high FPS while maintaining tracking accuracy.
    """
    
    def __init__(self):
        # Initialize HOG descriptor for person detection
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        
        # Load Haar Cascades with fallback
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.profile_face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_profileface.xml')
        self.upper_body_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_upperbody.xml')
        
        # Try to load a specialized head cascade if it exists, otherwise use upper body as proxy
        # Note: We'll rely on upper body and faces as primary head proxies in classroom settings
        
        # Parameters
        self.confidence_threshold = 0.3
        self.tracking_lock = threading.Lock()
        
        # Stabilization State
        self.frame_counter = 0
        self.last_full_detections = []
        self.head_count_history = deque(maxlen=20) # Increased history for better stability
        self.stable_head_count = 0

    def detect_heads(self, frame):
        """
        Detects heads/people in a frame.
        Optimized for classroom environments where students are often seated.
        """
        if frame is None: return 0, [], None, 0.0, {}
        
        orig_h, orig_w = frame.shape[:2]
        
        # 1. Processing Scale: Use a fixed width for consistent detection performance
        target_w = 640
        scale = target_w / orig_w
        p_frame = cv2.resize(frame, (target_w, int(orig_h * scale)))
        gray = cv2.cvtColor(p_frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray) # Improve contrast for better detection
            
        inv_scale = 1.0 / scale
        annotated_raw = frame.copy()

        with self.tracking_lock:
            self.frame_counter += 1
            # Run heavy detection every 4 frames (increased frequency for responsiveness)
            should_run_heavy = (self.frame_counter % 4 == 0)
            
            if not should_run_heavy and self.last_full_detections:
                return self._finalize(self.stable_head_count, self.last_full_detections, 
                                     annotated_raw, inv_scale)

        # 2. Multi-Model Fusion Detection
        all_detections = []
        
        # --- A. HOG Person Detection (Full body/Half body) ---
        try:
            boxes, weights = self.hog.detectMultiScale(p_frame, winStride=(8,8), padding=(4,4), scale=1.05)
            for (x, y, w, h), weight in zip(boxes, weights):
                if weight > self.confidence_threshold:
                    all_detections.append({'bbox': (x, y, w, h), 'confidence': float(weight), 'type': 'person'})
        except Exception: pass
        
        # --- B. Haar Cascades (Face & Upper Body) ---
        # Face detection is a high-confidence indicator of a head
        try:
            # Frontal Faces
            faces = self.face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
            for box in faces:
                if not any(self._boxes_overlap(box, d['bbox'], 0.5) for d in all_detections):
                    all_detections.append({'bbox': tuple(box), 'confidence': 0.8, 'type': 'head'})
            
            # Profile Faces (Side view)
            profiles = self.profile_face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
            for box in profiles:
                if not any(self._boxes_overlap(box, d['bbox'], 0.5) for d in all_detections):
                    all_detections.append({'bbox': tuple(box), 'confidence': 0.7, 'type': 'head'})
                    
            # Upper Body (Crucial for seated students)
            bodies = self.upper_body_cascade.detectMultiScale(gray, 1.1, 3, minSize=(50, 50))
            for box in bodies:
                # Upper body box is larger, check if it already contains a face
                if not any(self._boxes_overlap(box, d['bbox'], 0.3) for d in all_detections):
                    all_detections.append({'bbox': tuple(box), 'confidence': 0.6, 'type': 'head'})
        except Exception: pass

        # 3. Stabilization & Counting
        with self.tracking_lock:
            # We use a moving average of the raw counts to filter out flickering
            current_count = len(all_detections)
            self.head_count_history.append(current_count)
            
            # Calculate stable count using median (robust to outliers)
            self.stable_head_count = int(np.median(list(self.head_count_history)))
            self.last_full_detections = all_detections
            
            # Calculate average confidence
            avg_conf = 0.0
            if all_detections:
                avg_conf = sum(d['confidence'] for d in all_detections) / len(all_detections)
            
            return self._finalize(self.stable_head_count, all_detections, annotated_raw, inv_scale, avg_conf)

    def _finalize(self, count, detections, frame, inv_scale, avg_conf=0.0):
        """Annotate the frame and return data"""
        h, w = frame.shape[:2]
        
        # 1. Draw Detections
        for d in detections:
            x, y, bw, bh = [int(v * inv_scale) for v in d['bbox']]
            # Draw green bounding box
            color = (0, 255, 0) # Green
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), color, 2)
            
            # Label
            label = f"{d['type']} {int(d['confidence']*100)}%"
            cv2.putText(frame, label, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # 2. Semi-Transparent HUD Bar
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 70), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
        
        # 3. HUD Content
        cv2.putText(frame, f"EDU-MI AI HEADCOUNT: {count}", (20, 45), 
                    cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 255, 0), 2)
        
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, ts, (w - 280, 40), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        
        return count, detections, frame, avg_conf, {}

    def _calculate_iou(self, b1, b2):
        x1, y1, w1, h1 = b1
        x2, y2, w2, h2 = b2
        xi1, yi1, xi2, yi2 = max(x1, x2), max(y1, y2), min(x1+w1, x2+w2), min(y1+h1, y2+h2)
        if xi2 <= xi1 or yi2 <= yi1: return 0.0
        inter = (xi2-xi1) * (yi2-yi1)
        union = (w1*h1 + w2*h2 - inter)
        return inter / union if union > 0 else 0.0

    def _calculate_inclusion(self, s, l):
        """Check if box 's' is mostly inside box 'l'"""
        sx, sy, sw, sh = s
        lx, ly, lw, lh = l
        xi1, yi1, xi2, yi2 = max(sx, lx), max(sy, ly), min(sx+sw, lx+lw), min(sy+sh, ly+lh)
        if xi2 <= xi1 or yi2 <= yi1: return 0.0
        inter_area = (xi2-xi1)*(yi2-yi1)
        s_area = sw*sh
        return inter_area / s_area if s_area > 0 else 0.0

    def _boxes_overlap(self, b1, b2, threshold=0.4):
        """Determines if two bounding boxes are likely detecting the same object"""
        if self._calculate_iou(b1, b2) > threshold: return True
        # Also check if one box is completely inside another (e.g. face inside body)
        if self._calculate_inclusion(b1, b2) > 0.8 or self._calculate_inclusion(b2, b1) > 0.8:
            return True
        return False


class HeadCountManager:
    """
    Manages head counting sessions for multiple cameras.
    Runs in background threads and logs counts periodically.
    """
    
    _instance = None
    _lock = threading.Lock()
    _sessions = {}  # camera_key -> session_data
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.detector = HeadDetector()
                    cls._instance._sessions = {}
        return cls._instance
    
    def get_camera_key(self, camera_type, camera_id):
        """Generate unique key for camera"""
        return f"{camera_type}_{camera_id}"
    
    def start_session(self, camera_type, camera_id, stream_url, camera_name, 
                      user, classroom=None, interval=30):
        """
        Start a head counting session for a camera.
        
        Args:
            camera_type: 'rtsp' or 'mobile'
            camera_id: ID of the camera
            stream_url: URL to stream video from
            camera_name: Name of the camera
            user: User who started the session
            classroom: Optional classroom to associate
            interval: Seconds between captures
        """
        from .models import HeadCountSession
        
        camera_key = self.get_camera_key(camera_type, camera_id)
        
        # Check if session already exists
        if camera_key in self._sessions:
            return False, "Session already active for this camera"
        
        # Create session record
        session = HeadCountSession.objects.create(
            camera_type=camera_type,
            camera_id=camera_id,
            camera_name=camera_name,
            classroom=classroom,
            started_by=user,
            status='active',
            capture_interval=interval
        )
        
        # Start background thread
        session_data = {
            'session': session,
            'stream_url': stream_url,
            'running': True,
            'thread': None,
            'cap': None,
            'last_count': 0,
        }
        
        thread = threading.Thread(
            target=self._run_session,
            args=(camera_key, session_data),
            daemon=True
        )
        session_data['thread'] = thread
        
        self._sessions[camera_key] = session_data
        thread.start()
        
        logger.info(f"Started head count session for {camera_key}")
        return True, session.id
    
    def stop_session(self, camera_type, camera_id):
        """Stop a head counting session"""
        from .models import HeadCountSession
        from django.db import transaction
        
        camera_key = self.get_camera_key(camera_type, camera_id)
        
        if camera_key not in self._sessions:
            return False, "No active session for this camera"
        
        session_data = self._sessions[camera_key]
        session_data['running'] = False
        
        # Release video capture
        if session_data.get('cap'):
            session_data['cap'].release()
        
        # Wait for thread to finish
        if session_data.get('thread'):
            session_data['thread'].join(timeout=5)
        
        # Update session record
        try:
            session = HeadCountSession.objects.get(id=session_data['session'].id)
            session.status = 'stopped'
            session.stopped_at = timezone.now()
            session.save()
        except HeadCountSession.DoesNotExist:
            pass
        
        del self._sessions[camera_key]
        logger.info(f"Stopped head count session for {camera_key}")
        return True, "Session stopped"
    
    def get_active_sessions(self):
        """Get all active sessions"""
        return {key: data['session'] for key, data in self._sessions.items()}
    
    def is_session_active(self, camera_type, camera_id):
        """Check if a session is active for a camera"""
        camera_key = self.get_camera_key(camera_type, camera_id)
        return camera_key in self._sessions
    
    def _run_session(self, camera_key, session_data):
        """Background thread to process camera feed for a session"""
        from .models import HeadCountLog, HeadCountSession
        
        session = session_data['session']
        camera_id = session.camera_id
        camera_type = session.camera_type
        stream_url = session_data['stream_url']
        interval = session.capture_interval
        
        logger.info(f"Starting background headcount thread for {camera_type} camera {camera_id}")
        
        # Robust connection logic
        def connect():
            transport_options = [('tcp', 'rtsp_transport;tcp'), ('udp', 'rtsp_transport;udp')]
            for t_name, t_opt in transport_options:
                try:
                    os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = f'{t_opt};stimeout;4000000'
                    cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
                    if cap.isOpened():
                        # Verify we can read a frame
                        ret, _ = cap.read()
                        if ret: return cap
                        cap.release()
                except Exception as e:
                    logger.warning(f"HOG detection failed: {e}")
            return None

        cap = connect()
        if not cap:
            logger.error(f"Headcount failed to connect to {camera_type} camera {camera_id}")
            try:
                s = HeadCountSession.objects.get(id=session.id)
                s.status = 'failed'
                s.save()
            except Exception as e:
                logger.warning(f"Failed to update session status: {e}")
            return

        last_log_time = 0
        
        try:
            while session_data.get('running', False):
                now = time.time()
                
                # Check if it's time to log based on the user-defined interval
                if now - last_log_time >= interval:
                    try:
                        ret, frame = cap.read()
                        if not ret or frame is None:
                            # Try one quick reconnect
                            cap.release()
                            cap = connect()
                            if not cap: break
                            ret, frame = cap.read()
                            if not ret: break
                        
                        # Process frame
                        count, detections, annotated, avg_conf, tracked = self.detector.detect_heads(frame)
                        
                        # Update session live stats
                        try:
                            s = HeadCountSession.objects.get(id=session.id)
                            s.total_captures += 1
                            if s.total_captures == 1:
                                s.max_head_count = count
                                s.min_head_count = count
                                s.average_head_count = count
                            else:
                                s.max_head_count = max(s.max_head_count, count)
                                s.min_head_count = min(s.min_head_count, count)
                                s.average_head_count = (
                                    (s.average_head_count * (s.total_captures - 1) + count) / 
                                    s.total_captures
                                )
                            s.save()
                            session = s
                        except HeadCountSession.DoesNotExist: pass
                        
                        # Save log to database
                        self._save_log(session, count, avg_conf, annotated)
                        last_log_time = now
                        
                    except Exception as e:
                        logger.error(f"Error in headcount processing loop: {e}")
                        time.sleep(2)
                
                # Sleep briefly to avoid CPU pegging
                time.sleep(1.0)
                
        finally:
            if cap: cap.release()
            logger.info(f"Background headcount thread for {camera_type} camera {camera_id} stopped")
    
    def _save_log(self, session, head_count, avg_confidence, annotated_frame):
        """Save a head count log entry"""
        from .models import HeadCountLog
        
        try:
            log_entry = HeadCountLog(
                camera_type=session.camera_type,
                camera_id=session.camera_id,
                camera_name=session.camera_name,
                classroom=session.classroom,
                head_count=head_count,
                confidence_score=avg_confidence,
                recorded_by=session.started_by,
            )
            
            # Save annotated frame as snapshot with high quality
            if annotated_frame is not None:
                ret, buffer = cv2.imencode('.jpg', annotated_frame, 
                                          [cv2.IMWRITE_JPEG_QUALITY, 90])
                if ret:
                    log_entry.snapshot.save(
                        f"headcount_{session.id}_{int(time.time())}.jpg",
                        ContentFile(buffer.tobytes()),
                        save=False
                    )
            
            log_entry.save()
            logger.info(f"Saved head count log: {head_count} heads")
            
        except Exception as e:
            logger.error(f"Error saving head count log: {e}")
    
    def get_current_count(self, camera_type, camera_id):
        """Get the current head count for a camera"""
        camera_key = self.get_camera_key(camera_type, camera_id)
        if camera_key in self._sessions:
            return self._sessions[camera_key].get('last_count', 0)
        return None


# Singleton instance
head_count_manager = HeadCountManager()

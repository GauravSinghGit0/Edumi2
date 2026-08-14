"""
FaceTrackingConsumer — Teacher-side real-time face tracking WebSocket.

Route: ws/face-tracking/<meeting_code>/

The teacher's browser sends frames from each student's video tile.
The server:
  1. Detects all faces in the frame
  2. Matches each face to the registered student DB embeddings
  3. Estimates engagement/emotion from facial geometry
  4. Returns overlay data: bounding boxes, names, emotion labels
  5. Saves snapshots for the post-meeting engagement report
"""
import json
import base64
import logging
from collections import defaultdict

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger('attendance.face_tracking')

# How often (frames) to save a snapshot to DB — every 4th result
SNAPSHOT_SAVE_INTERVAL = 4

# Emotion labels derived from simple facial geometry heuristics
EMOTION_LABELS = {
    'focused':    '🎯 Focused',
    'happy':      '😊 Happy',
    'surprised':  '😲 Surprised',
    'tired':      '😴 Tired/Sleeping',
    'confused':   '🤔 Confused',
    'distracted': '😶 Distracted',
    'unknown':    '❓ Unknown',
}


class FaceTrackingConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user         = self.scope['user']
        self.meeting_code = self.scope['url_route']['kwargs']['meeting_code']

        if not self.user.is_authenticated:
            await self.close()
            return

        # Only the meeting host (teacher) may connect
        is_host = await self._is_host()
        if not is_host:
            await self.close()
            return

        # Load all registered embeddings for this meeting's classroom
        self._embeddings = await self._load_all_embeddings()
        self._frame_count = defaultdict(int)   # per student_id frame counter

        await self.accept()
        await self.send(json.dumps({
            'type':    'connected',
            'message': f'Face tracking active. {len(self._embeddings)} student(s) registered.',
            'count':   len(self._embeddings),
        }))

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type')

        if msg_type == 'frame':
            # Single frame from one student's video tile
            student_id = data.get('student_id')   # DOM user_id of the student
            frame_b64  = data.get('frame', '')
            if not frame_b64:
                return
            try:
                frame_bytes = base64.b64decode(frame_b64)
            except Exception:
                return

            result = await database_sync_to_async(self._process_frame)(
                frame_bytes, student_id
            )

            # Optionally save snapshot
            if result.get('matched_user_id'):
                self._frame_count[result['matched_user_id']] += 1
                if self._frame_count[result['matched_user_id']] % SNAPSHOT_SAVE_INTERVAL == 0:
                    await self._save_snapshot(
                        result['matched_user_id'],
                        result.get('emotion', 'unknown'),
                        result.get('confidence', 0.0),
                        result.get('face_visible', True),
                    )

            await self.send(json.dumps({
                'type':       'tracking_result',
                'student_id': student_id,
                **result,
            }))

        elif msg_type == 'bulk_frame':
            # All student frames in one message: {student_id: frame_b64, ...}
            frames = data.get('frames', {})
            results = {}
            for sid, frame_b64 in frames.items():
                if not frame_b64:
                    continue
                try:
                    frame_bytes = base64.b64decode(frame_b64)
                except Exception:
                    continue
                res = await database_sync_to_async(self._process_frame)(frame_bytes, sid)
                results[sid] = res
                if res.get('matched_user_id'):
                    self._frame_count[res['matched_user_id']] += 1
                    if self._frame_count[res['matched_user_id']] % SNAPSHOT_SAVE_INTERVAL == 0:
                        await self._save_snapshot(
                            res['matched_user_id'],
                            res.get('emotion', 'unknown'),
                            res.get('confidence', 0.0),
                            res.get('face_visible', True),
                        )
                        # Also write to physical log
                        await self._write_to_meeting_log(
                            res['matched_user_id'],
                            res.get('matched_name', 'Unknown'),
                            res.get('emotion', 'unknown')
                        )

            await self.send(json.dumps({
                'type':    'bulk_tracking_result',
                'results': results,
            }))

    # ── Core processing ───────────────────────────────────────────

    def _process_frame(self, frame_bytes: bytes, hint_student_id=None) -> dict:
        """
        Detect faces, match to DB, estimate emotion.
        Returns overlay data for the client.
        """
        try:
            import numpy as np
            from PIL import Image
            import io
            import cv2

            pil_img = Image.open(io.BytesIO(frame_bytes)).convert('RGB')
            np_img  = np.array(pil_img)
            
            # ── Low-light enhancement ─────────────────────
            try:
                avg_brightness = np.mean(np_img)
                if avg_brightness < 65:
                    lab = cv2.cvtColor(np_img, cv2.COLOR_RGB2LAB)
                    l, a, b = cv2.split(lab)
                    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
                    cl = clahe.apply(l)
                    limg = cv2.merge((cl, a, b))
                    np_img = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
            except Exception as e:
                logger.warning(f"Low-light enhancement inline failed: {e}")

            h, w    = np_img.shape[:2]

            face_locations = []
            try:
                import face_recognition
                face_locations = face_recognition.face_locations(np_img, model='hog')
            except Exception:
                # Fallback to OpenCV
                face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                face_locations = [(y, x + w, y + h, x) for (x, y, w, h) in faces]

            if not face_locations:
                return {
                    'face_visible': False,
                    'faces':        [],
                    'emotion':      'absent',
                    'emotion_label': '📵 Not Visible',
                    'matched_user_id': None,
                    'matched_name':    'Unknown',
                    'confidence':      0.0,
                }

            # Encode all detected faces
            encodings = []
            try:
                import face_recognition
                encodings = face_recognition.face_encodings(
                    np_img, face_locations, num_jitters=1, model='large'
                )
            except (ImportError, Exception):
                # Robust Fallback for each face
                gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)
                for (top, right, bottom, left) in face_locations:
                    try:
                        face_crop = gray[max(0,top):min(h,bottom), max(0,left):min(w,right)]
                        if face_crop.size == 0:
                            encodings.append([0.0]*128)
                            continue
                            
                        # Normalize lighting
                        face_norm = cv2.equalizeHist(face_crop)
                        
                        # Grayscale features
                        g_feat = cv2.resize(face_norm, (8, 8)).flatten() / 255.0
                        
                        # Edge features
                        sobelx = cv2.Sobel(face_norm, cv2.CV_64F, 1, 0, ksize=3)
                        sobely = cv2.Sobel(face_norm, cv2.CV_64F, 0, 1, ksize=3)
                        mag = cv2.magnitude(sobelx, sobely)
                        e_feat = cv2.resize(mag, (8, 8)).flatten()
                        e_feat = e_feat / (np.max(e_feat) + 1e-6)
                        
                        encodings.append(np.concatenate([g_feat, e_feat]).tolist())
                    except Exception as e:
                        logger.warning(f"Face crop processing failed: {e}")
                        encodings.append([0.0]*128)

            faces_out = []
            best_match_uid  = None
            best_match_name = 'Unknown'
            best_confidence = 0.0
            best_emotion    = 'unknown'

            for (top, right, bottom, left), enc in zip(face_locations, encodings):
                # Normalise bounding box to 0-1
                box = {
                    'x': round(left / w, 4),
                    'y': round(top / h, 4),
                    'w': round((right - left) / w, 4),
                    'h': round((bottom - top) / h, 4),
                }

                # Match against all registered embeddings
                matched_uid  = None
                matched_name = 'Unknown'
                confidence   = 0.0

                if self._embeddings:
                    stored_vecs = np.array([e['vec'] for e in self._embeddings])
                    enc_vec = np.array(enc)
                    
                    try:
                        import face_recognition
                        distances = face_recognition.face_distance(stored_vecs, enc_vec)
                    except (ImportError, Exception):
                        # Fallback Euclidean distance with normalization
                        raw_dists = np.linalg.norm(stored_vecs - enc_vec, axis=1)
                        # Normalize to 0-1 range compatible with threshold
                        distances = np.clip(raw_dists / 7.5, 0, 1)

                    best_idx    = int(np.argmin(distances))
                    best_dist   = float(distances[best_idx])
                    conf        = round(max(0.0, 1.0 - best_dist), 3)

                    if best_dist <= 0.45:   # threshold: distance ≤ 0.45 → match
                        matched_uid  = self._embeddings[best_idx]['user_id']
                        matched_name = self._embeddings[best_idx]['name']
                        confidence   = conf

                # Estimate emotion from facial landmarks
                emotion = self._estimate_emotion(np_img, (top, right, bottom, left))

                faces_out.append({
                    'box':        box,
                    'name':       matched_name,
                    'user_id':    matched_uid,
                    'confidence': confidence,
                    'emotion':    emotion,
                    'emotion_label': EMOTION_LABELS.get(emotion, '❓ Unknown'),
                })

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match_uid  = matched_uid
                    best_match_name = matched_name
                    best_emotion    = emotion

            return {
                'face_visible':    True,
                'faces':           faces_out,
                'emotion':         best_emotion,
                'emotion_label':   EMOTION_LABELS.get(best_emotion, '❓ Unknown'),
                'matched_user_id': best_match_uid,
                'matched_name':    best_match_name,
                'confidence':      best_confidence,
            }

        except Exception as exc:
            logger.exception(f"Processing frame failed: {exc}")
            return {
                'face_visible': False,
                'faces':        [],
                'emotion':      'error',
                'emotion_label': '❌ Processing Error',
                'matched_user_id': None,
                'matched_name':    'Error',
                'confidence':      0.0,
            }

    def _estimate_emotion(self, np_img, face_location) -> str:
        """
        Lightweight emotion estimation using facial landmark geometry.
        No external emotion model needed — uses face_recognition landmarks.

        Heuristics:
          - Mouth open wide + raised brows → happy
          - Brows furrowed (close together) → confused
          - Eyes looking sideways (asymmetric) → distracted
          - Default → focused
        """
        try:
            import face_recognition
            import numpy as np

            landmarks_list = face_recognition.face_landmarks(np_img, [face_location])
            if not landmarks_list:
                return 'unknown'

            lm = landmarks_list[0]

            # ── Mouth openness ──────────────────────────────
            top_lip    = lm.get('top_lip', [])
            bottom_lip = lm.get('bottom_lip', [])
            if top_lip and bottom_lip:
                top_y    = np.mean([p[1] for p in top_lip])
                bottom_y = np.mean([p[1] for p in bottom_lip])
                mouth_open = abs(bottom_y - top_y)
            else:
                mouth_open = 0

            # ── Eyebrow height (relative to eye) ───────────
            left_brow  = lm.get('left_eyebrow', [])
            right_brow = lm.get('right_eyebrow', [])
            left_eye   = lm.get('left_eye', [])
            right_eye  = lm.get('right_eye', [])

            brow_raise = 0
            if left_brow and left_eye:
                brow_y = np.mean([p[1] for p in left_brow])
                eye_y  = np.mean([p[1] for p in left_eye])
                brow_raise = eye_y - brow_y   # positive = brows raised

            # ── Brow furrow (horizontal distance between brows) ─
            brow_furrow = 0
            if left_brow and right_brow:
                left_inner  = max(left_brow,  key=lambda p: p[0])
                right_inner = min(right_brow, key=lambda p: p[0])
                brow_furrow = right_inner[0] - left_inner[0]

            # ── Eye symmetry (distraction proxy) ───────────
            eye_asym = 0
            if left_eye and right_eye:
                left_cx  = np.mean([p[0] for p in left_eye])
                right_cx = np.mean([p[0] for p in right_eye])
                left_cy  = np.mean([p[1] for p in left_eye])
                right_cy = np.mean([p[1] for p in right_eye])
                eye_asym = abs(left_cy - right_cy)

            # ── Eye openness (EAR proxy) ────────────────────
            def get_ear(eye_points):
                if not eye_points or len(eye_points) < 6: return 1.0
                # Roughly dist(P2,P6)+dist(P3,P5) / 2*dist(P1,P4)
                p1, p2, p3, p4, p5, p6 = eye_points[0], eye_points[1], eye_points[2], eye_points[3], eye_points[4], eye_points[5]
                ver1 = np.linalg.norm(np.array(p2) - np.array(p6))
                ver2 = np.linalg.norm(np.array(p3) - np.array(p5))
                hor  = np.linalg.norm(np.array(p1) - np.array(p4))
                return (ver1 + ver2) / (2.0 * hor)

            left_ear  = get_ear(lm.get('left_eye'))
            right_ear = get_ear(lm.get('right_eye'))
            avg_ear   = (left_ear + right_ear) / 2.0

            # ── Decision tree ───────────────────────────────
            face_h = face_location[2] - face_location[0]   # bottom - top

            if avg_ear < 0.21:
                return 'tired'
            elif mouth_open > face_h * 0.25:
                return 'surprised'
            elif mouth_open > face_h * 0.12 and brow_raise > face_h * 0.08:
                return 'happy'
            elif brow_furrow < face_h * 0.15 and brow_raise < face_h * 0.04:
                return 'confused'
            elif eye_asym > face_h * 0.06:
                return 'distracted'
            else:
                return 'focused'

        except Exception:
            return 'unknown'

    # ── DB helpers ────────────────────────────────────────────────

    @database_sync_to_async
    def _is_host(self) -> bool:
        from meetings.models import Meeting
        try:
            meeting = Meeting.objects.get(meeting_code=self.meeting_code)
            return meeting.teacher == self.user or self.user.is_superuser
        except Meeting.DoesNotExist:
            return False

    @database_sync_to_async
    def _load_all_embeddings(self) -> list:
        """Load all active face embeddings for students in this meeting's classroom."""
        from meetings.models import Meeting
        from .models import StudentFaceProfile
        from .encryption_service import FaceEncryptionService
        import numpy as np

        try:
            meeting   = Meeting.objects.select_related('classroom').get(
                meeting_code=self.meeting_code
            )
            classroom = meeting.classroom
        except Exception:
            return []

        # Get all approved students in the classroom
        if classroom:
            from meetings.models import ClassroomMembership
            student_ids = ClassroomMembership.objects.filter(
                classroom=classroom, status='approved'
            ).values_list('student_id', flat=True)
        else:
            student_ids = []

        profiles = StudentFaceProfile.objects.filter(
            student_id__in=student_ids, is_active=True
        ).select_related('student', 'student__userprofile')

        enc_svc = FaceEncryptionService()
        result  = []
        for p in profiles:
            try:
                vec = enc_svc.decrypt_embedding(bytes(p.face_embedding_encrypted))
                name = (
                    p.student.get_full_name()
                    or getattr(p.student, 'userprofile', None) and p.student.userprofile.display_name
                    or p.student.username
                )
                result.append({
                    'user_id': p.student_id,
                    'name':    name,
                    'vec':     vec,
                })
            except Exception as exc:
                logger.warning(f'Could not load embedding for {p.student.username}: {exc}')

        return result

    @database_sync_to_async
    def _save_snapshot(self, user_id: int, emotion: str, confidence: float, face_visible: bool):
        from meetings.models import Meeting
        from django.contrib.auth import get_user_model
        from .models import StudentEngagementSnapshot
        User = get_user_model()
        try:
            meeting = Meeting.objects.get(meeting_code=self.meeting_code)
            student = User.objects.get(id=user_id)
            StudentEngagementSnapshot.objects.create(
                meeting=meeting,
                student=student,
                emotion=emotion,
                confidence=confidence,
                face_visible=face_visible,
            )
        except Exception as exc:
            logger.debug(f'Snapshot save failed: {exc}')

    @database_sync_to_async
    def _write_to_meeting_log(self, user_id: int, name: str, emotion: str):
        """Append a record to the meeting's physical engagement CSV log."""
        import os
        import csv
        from django.conf import settings
        
        log_dir = os.path.join(settings.MEDIA_ROOT, 'meeting_logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        log_file = os.path.join(log_dir, f'engagement_{self.meeting_code}.csv')
        file_exists = os.path.isfile(log_file)
        
        try:
            with open(log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['Timestamp', 'User ID', 'Name', 'Expression', 'Status'])
                
                status = 'Active' if emotion not in ['tired', 'distracted', 'absent'] else 'Inactive/Distracted'
                writer.writerow([
                    timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                    user_id,
                    name,
                    emotion.capitalize(),
                    status
                ])
        except Exception as e:
            logger.error(f"Failed to write to engagement log: {e}")

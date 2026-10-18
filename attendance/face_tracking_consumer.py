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
        self.user         = self.scope.get('user')
        self.meeting_code = self.scope['url_route']['kwargs']['meeting_code']

        if not self.user or not self.user.is_authenticated or not getattr(self.user, 'is_active', True):
            await self.close(code=4003)
            return

        # Only the meeting host (teacher) or admin may connect
        is_host = await self._is_host()
        if not is_host:
            await self.close()
            return

        # Accept early to establish WebSocket handshake
        await self.accept()

        try:
            # Load all registered embeddings and match threshold for this meeting's classroom
            self._embeddings = await self._load_all_embeddings()
            self._match_threshold = await self._get_match_threshold()
            self._frame_count = defaultdict(int)   # per student_id frame counter

            await self.send(json.dumps({
                'type':    'connected',
                'message': f'Face tracking active. {len(self._embeddings)} student(s) registered.',
                'count':   len(self._embeddings),
            }))
        except Exception as e:
            logger.error(f"Error initializing FaceTrackingConsumer: {e}", exc_info=True)

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
        Detect faces, match against enrolled students, estimate attention.
        Returns visual overlay tracking data for the client.
        Uses 100% Apache 2.0 compliant YuNet + SFace.
        """
        try:
            import io
            import cv2
            import numpy as np
            from PIL import Image
            from .face_service import get_face_service

            svc = get_face_service()
            pil_img = Image.open(io.BytesIO(frame_bytes)).convert('RGB')
            np_img = np.array(pil_img)

            # Low-light enhancement via shared FaceService
            np_img = svc._enhance_low_light(np_img)
            bgr_img = cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)
            h, w = bgr_img.shape[:2]

            face_locations = []
            encodings = []
            face_landmarks_list = []

            # 1. Detect faces using YuNet (Apache 2.0)
            if svc._models_loaded and svc._detector is not None and svc._recognizer is not None:
                try:
                    with svc._model_lock:
                        svc._detector.setInputSize((w, h))
                        _, detected_faces = svc._detector.detect(bgr_img)

                    if detected_faces is not None and len(detected_faces) > 0:
                        for face_data in detected_faces:
                            fx, fy, fw, fh = int(face_data[0]), int(face_data[1]), int(face_data[2]), int(face_data[3])
                            top = max(0, fy)
                            left = max(0, fx)
                            bottom = min(h, fy + fh)
                            right = min(w, fx + fw)
                            face_locations.append((top, right, bottom, left))

                            # 5 Landmarks: right eye, left eye, nose, right mouth, left mouth
                            landmarks = [
                                (float(face_data[4]), float(face_data[5])),
                                (float(face_data[6]), float(face_data[7])),
                                (float(face_data[8]), float(face_data[9])),
                                (float(face_data[10]), float(face_data[11])),
                                (float(face_data[12]), float(face_data[13])),
                            ]
                            face_landmarks_list.append(landmarks)

                            with svc._model_lock:
                                aligned = svc._recognizer.alignCrop(bgr_img, face_data)
                                feat = svc._recognizer.feature(aligned)
                            if feat is not None and len(feat) > 0:
                                encodings.append(feat[0].tolist())
                            else:
                                encodings.append([0.0] * 128)
                except Exception as e:
                    logger.warning(f"YuNet/SFace detection failed in tracking consumer: {e}")

            # Fallback to Haar cascade if YuNet is offline
            if not face_locations:
                face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                for (x, y, fw, fh) in faces:
                    face_locations.append((y, x + fw, y + fh, x))
                    encodings.append([0.0] * 128)
                    face_landmarks_list.append(None)

            if not face_locations:
                return {
                    'face_visible': False,
                    'faces': [],
                    'emotion': 'absent',
                    'emotion_label': '📵 Not Visible',
                    'matched_user_id': None,
                    'matched_name': 'Unknown',
                    'confidence': 0.0,
                }

            # Pre-compute normalized matrix of stored student embeddings once
            stored_normed = None
            if self._embeddings:
                stored_mat = np.array([e['vec'] for e in self._embeddings], dtype=np.float32)
                norms = np.linalg.norm(stored_mat, axis=1, keepdims=True) + 1e-8
                stored_normed = stored_mat / norms

            faces_out = []
            best_match_uid = None
            best_match_name = 'Unknown'
            best_confidence = 0.0
            best_emotion = 'unknown'
            threshold = getattr(self, '_match_threshold', 0.55)

            for idx, (loc, enc) in enumerate(zip(face_locations, encodings)):
                top, right, bottom, left = loc
                box = {
                    'x': round(left / w, 4),
                    'y': round(top / h, 4),
                    'w': round((right - left) / w, 4),
                    'h': round((bottom - top) / h, 4),
                }

                matched_uid = None
                matched_name = 'Unknown'
                confidence = 0.0

                # Vectorized matching across all stored embeddings
                if stored_normed is not None and len(stored_normed) > 0:
                    enc_vec = np.array(enc, dtype=np.float32)
                    enc_norm = enc_vec / (np.linalg.norm(enc_vec) + 1e-8)
                    sims = np.dot(stored_normed, enc_norm)
                    best_idx = int(np.argmax(sims))
                    best_sim = float(sims[best_idx])
                    dist = max(0.0, min(1.0, 1.0 - best_sim))
                    conf = round(max(0.0, min(1.0, best_sim)), 3)

                    # Cosine similarity >= 0.363 or normalized distance <= threshold
                    if dist <= threshold or best_sim >= 0.363:
                        matched_uid = self._embeddings[best_idx]['user_id']
                        matched_name = self._embeddings[best_idx]['name']
                        confidence = conf

                landmarks = face_landmarks_list[idx] if idx < len(face_landmarks_list) else None
                emotion = self._estimate_emotion(np_img, loc, landmarks=landmarks)

                faces_out.append({
                    'box': box,
                    'name': matched_name,
                    'user_id': matched_uid,
                    'confidence': confidence,
                    'emotion': emotion,
                    'emotion_label': EMOTION_LABELS.get(emotion, '❓ Unknown'),
                })

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match_uid = matched_uid
                    best_match_name = matched_name
                    best_emotion = emotion

            return {
                'face_visible': True,
                'faces': faces_out,
                'emotion': best_emotion,
                'emotion_label': EMOTION_LABELS.get(best_emotion, '❓ Unknown'),
                'matched_user_id': best_match_uid,
                'matched_name': best_match_name,
                'confidence': best_confidence,
            }

        except Exception as exc:
            logger.exception(f"Processing frame failed: {exc}")
            return {
                'face_visible': False,
                'faces': [],
                'emotion': 'error',
                'emotion_label': '❌ Processing Error',
                'matched_user_id': None,
                'matched_name': 'Error',
                'confidence': 0.0,
            }

    def _estimate_emotion(self, np_img, face_location, landmarks=None) -> str:
        """
        Lightweight attention & pose estimation using YuNet landmarks geometry.
        Self-contained, Apache 2.0 compliant (zero external models or dlib).
        """
        if not landmarks or len(landmarks) < 5:
            return 'focused'

        try:
            r_eye, l_eye, nose, r_mouth, l_mouth = landmarks[:5]
            # Eye horizontal tilt (head roll / distraction proxy)
            eye_dy = abs(r_eye[1] - l_eye[1])
            eye_dx = abs(r_eye[0] - l_eye[0]) + 1e-6
            tilt_ratio = eye_dy / eye_dx

            # Mouth width vs eye distance
            mouth_w = abs(r_mouth[0] - l_mouth[0])

            if tilt_ratio > 0.35:
                return 'distracted'
            elif mouth_w > eye_dx * 0.85:
                return 'happy'
            else:
                return 'focused'
        except Exception:
            return 'focused'

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
                if isinstance(vec, dict):
                    vec = vec.get('data', [])
                if not vec:
                    continue
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
    def _get_match_threshold(self) -> float:
        from django.conf import settings
        from meetings.models import Meeting
        from .models import AttendanceSettings
        default_th = getattr(settings, 'FACE_MATCH_THRESHOLD', 0.55)
        try:
            meeting = Meeting.objects.select_related('classroom').get(meeting_code=self.meeting_code)
            if meeting.classroom:
                att_s = AttendanceSettings.objects.filter(classroom=meeting.classroom).first()
                if att_s:
                    return att_s.confidence_threshold
        except Exception:
            pass
        return default_th

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

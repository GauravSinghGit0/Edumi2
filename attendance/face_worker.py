"""
Dedicated asynchronous face processing worker.
Runs independently from Daphne - handles CPU-intensive ONNX inference.
"""
import asyncio
import json
import base64
import logging
from typing import Dict, Any
from django.conf import settings

logger = logging.getLogger('attendance.face_worker')

class AsyncFaceWorker:
    """
    Asynchronous worker that processes face tracking frames from Redis stream.
    Uses asyncio for concurrent frame processing without blocking Daphne.
    """

    def __init__(self, worker_id: str = 'worker-1'):
        self.worker_id = worker_id
        self.redis = None
        self.face_service = None
        self.running = False
        self.embeddings_cache = {}

    async def initialize(self):
        """Initialize Redis connection and face service"""
        import redis.asyncio as aioredis
        self.redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding='utf-8',
            decode_responses=False
        )
        from .face_service import FaceService
        self.face_service = FaceService()
        logger.info(f"AsyncFaceWorker {self.worker_id} initialized")

    async def process_frame(self, frame_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process single frame with face detection and recognition"""
        try:
            frame_id = frame_data['frame_id']
            frame_bytes = base64.b64decode(frame_data['frame_b64'])
            student_id = frame_data.get('student_id')
            meeting_code = frame_data.get('meeting_code', '')

            if meeting_code not in self.embeddings_cache:
                embeddings = await self._load_embeddings_for_meeting(meeting_code)
                self.embeddings_cache[meeting_code] = embeddings
            else:
                embeddings = self.embeddings_cache[meeting_code]

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._process_frame_sync,
                frame_bytes,
                embeddings,
                student_id
            )

            result['frame_id'] = frame_id
            result['timestamp'] = frame_data.get('timestamp')
            return result

        except Exception as e:
            logger.error(f"Error processing frame {frame_data.get('frame_id')}: {e}")
            return {
                'frame_id': frame_data.get('frame_id'),
                'face_visible': False,
                'error': str(e)
            }

    def _process_frame_sync(self, frame_bytes: bytes, embeddings: list, hint_student_id=None):
        """Synchronous frame processing running in thread pool executor"""
        import io
        import cv2
        import numpy as np
        from PIL import Image

        pil_img = Image.open(io.BytesIO(frame_bytes)).convert('RGB')
        np_img = np.array(pil_img)
        np_img = self.face_service._enhance_low_light(np_img)
        bgr_img = cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)
        h, w = bgr_img.shape[:2]

        face_locations = []
        encodings = []
        face_landmarks_list = []

        if self.face_service._models_loaded:
            try:
                with self.face_service._model_lock:
                    self.face_service._detector.setInputSize((w, h))
                    _, detected_faces = self.face_service._detector.detect(bgr_img)

                if detected_faces is not None and len(detected_faces) > 0:
                    for face_data in detected_faces:
                        fx, fy, fw, fh = int(face_data[0]), int(face_data[1]), int(face_data[2]), int(face_data[3])
                        top = max(0, fy)
                        left = max(0, fx)
                        bottom = min(h, fy + fh)
                        right = min(w, fx + fw)
                        face_locations.append((top, right, bottom, left))

                        landmarks = [
                            (float(face_data[4]), float(face_data[5])),
                            (float(face_data[6]), float(face_data[7])),
                            (float(face_data[8]), float(face_data[9])),
                            (float(face_data[10]), float(face_data[11])),
                            (float(face_data[12]), float(face_data[13])),
                        ]
                        face_landmarks_list.append(landmarks)

                        with self.face_service._model_lock:
                            aligned = self.face_service._recognizer.alignCrop(bgr_img, face_data)
                            feat = self.face_service._recognizer.feature(aligned)

                        if feat is not None and len(feat) > 0:
                            encodings.append(feat[0].tolist())
                        else:
                            encodings.append([0.0] * 128)
            except Exception as e:
                logger.warning(f"YuNet/SFace detection failed: {e}")

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

        stored_normed = None
        if embeddings:
            stored_mat = np.array([e['vec'] for e in embeddings], dtype=np.float32)
            norms = np.linalg.norm(stored_mat, axis=1, keepdims=True) + 1e-8
            stored_normed = stored_mat / norms

        faces_out = []
        best_match_uid = None
        best_match_name = 'Unknown'
        best_confidence = 0.0
        best_emotion = 'unknown'
        threshold = 0.55

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

            if stored_normed is not None and len(stored_normed) > 0:
                enc_vec = np.array(enc, dtype=np.float32)
                enc_norm = enc_vec / (np.linalg.norm(enc_vec) + 1e-8)
                sims = np.dot(stored_normed, enc_norm)
                best_idx = int(np.argmax(sims))
                best_sim = float(sims[best_idx])
                dist = max(0.0, min(1.0, 1.0 - best_sim))
                conf = round(max(0.0, min(1.0, best_sim)), 3)

                if dist <= threshold or best_sim >= 0.363:
                    matched_uid = embeddings[best_idx]['user_id']
                    matched_name = embeddings[best_idx]['name']
                    confidence = conf

            landmarks = face_landmarks_list[idx] if idx < len(face_landmarks_list) else None
            emotion = self._estimate_emotion(np_img, loc, landmarks=landmarks)

            faces_out.append({
                'box': box,
                'name': matched_name,
                'user_id': matched_uid,
                'confidence': confidence,
                'emotion': emotion,
                'emotion_label': self._get_emotion_label(emotion),
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
            'emotion_label': self._get_emotion_label(best_emotion),
            'matched_user_id': best_match_uid,
            'matched_name': best_match_name,
            'confidence': best_confidence,
        }

    def _estimate_emotion(self, np_img, face_location, landmarks=None):
        if not landmarks or len(landmarks) < 5:
            return 'focused'
        try:
            r_eye, l_eye, nose, r_mouth, l_mouth = landmarks[:5]
            eye_dy = abs(r_eye[1] - l_eye[1])
            eye_dx = abs(r_eye[0] - l_eye[0]) + 1e-6
            tilt_ratio = eye_dy / eye_dx
            mouth_w = abs(r_mouth[0] - l_mouth[0])

            if tilt_ratio > 0.35:
                return 'distracted'
            elif mouth_w > eye_dx * 0.85:
                return 'happy'
            else:
                return 'focused'
        except Exception:
            return 'focused'

    def _get_emotion_label(self, emotion):
        labels = {
            'focused': '🎯 Focused',
            'happy': '😊 Happy',
            'surprised': '😲 Surprised',
            'tired': '😴 Tired',
            'confused': '🤔 Confused',
            'distracted': '😶 Distracted',
            'unknown': '❓ Unknown',
            'absent': '📵 Not Visible',
        }
        return labels.get(emotion, '❓ Unknown')

    async def _load_embeddings_for_meeting(self, meeting_code: str) -> list:
        from asgiref.sync import sync_to_async

        @sync_to_async
        def _load():
            from meetings.models import Meeting
            try:
                meeting = Meeting.objects.select_related('classroom').get(meeting_code=meeting_code)
                classroom = meeting.classroom
            except Exception:
                return []

            if classroom:
                from academics.models import ClassroomMembership
                student_ids = ClassroomMembership.objects.filter(
                    classroom=classroom, status='approved'
                ).values_list('student_id', flat=True)
            else:
                student_ids = []

            from .models import StudentFaceProfile
            from .encryption_service import FaceEncryptionService

            profiles = StudentFaceProfile.objects.filter(
                student_id__in=student_ids, is_active=True
            ).select_related('student', 'student__userprofile')

            enc_svc = FaceEncryptionService()
            result = []

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
                        'name': name,
                        'vec': vec,
                    })
                except Exception as e:
                    logger.warning(f'Could not load embedding for {p.student.username}: {e}')

            return result

        return await _load()

    async def run(self):
        """Main worker loop - consumes frames from Redis stream"""
        self.running = True
        logger.info(f"AsyncFaceWorker {self.worker_id} starting...")

        group_name = 'face_workers'
        stream_key = 'edumi:face:frames'

        try:
            await self.redis.xgroup_create(stream_key, group_name, id='0', mkstream=True)
        except Exception:
            pass

        while self.running:
            try:
                messages = await self.redis.xreadgroup(
                    groupname=group_name,
                    consumername=self.worker_id,
                    streams={stream_key: '>'},
                    count=10,
                    block=1000
                )

                if not messages:
                    continue

                tasks = []
                for stream, entries in messages:
                    for entry_id, data in entries:
                        frame_data = json.loads(data[b'data'])
                        frame_data['entry_id'] = entry_id
                        tasks.append(self.process_and_store_result(frame_data))

                await asyncio.gather(*tasks, return_exceptions=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(1)

        logger.info(f"AsyncFaceWorker {self.worker_id} stopped")

    async def process_and_store_result(self, frame_data: Dict):
        try:
            from .face_metrics import face_processing_latency, face_frames_processed
            with face_processing_latency.time():
                result = await self.process_frame(frame_data)

            face_frames_processed.labels(
                meeting_code=frame_data.get('meeting_code', ''),
                status='success' if result.get('face_visible') else 'no_face'
            ).inc()

            frame_id = frame_data['frame_id']
            result_key = f"edumi:face:result:{frame_id}"
            await self.redis.setex(result_key, 10, json.dumps(result))

            stream_key = 'edumi:face:frames'
            await self.redis.xack(stream_key, 'face_workers', frame_data['entry_id'])

        except Exception as e:
            logger.error(f"Error processing and storing result: {e}")

    async def stop(self):
        self.running = False
        if self.redis:
            await self.redis.close()

"""
Face recognition service — high-accuracy, anti-spoofing.

  - Uses 'large' face landmark model (68 points) for better encoding accuracy
  - Anti-spoofing motion liveness: only applied during live WebSocket frames,
    NOT during registration (which is intentionally a static photo/upload)
  - Strict distance threshold with per-classroom override
"""
import io
import hashlib
import json
import logging
from typing import Optional

from .encryption_service import FaceEncryptionService

logger = logging.getLogger('attendance.face_service')

MATCH_THRESHOLD   = 0.55   # default; overridden per-classroom
MIN_QUALITY_SCORE = 0.08
# Minimum pixel std-dev — only used for live frames, not registration uploads
MIN_LIVENESS_VARIANCE = 6.0
# Minimum motion diff between two consecutive live frames
MIN_MOTION_DIFF = 1.5


class FaceService:

    def __init__(self):
        self._encryptor = FaceEncryptionService()

    # ─────────────────────────────────────────────────────
    #  PUBLIC: extract embedding from raw image bytes
    #  live=False  → registration (skip liveness variance check)
    #  live=True   → live frame (apply liveness variance check)
    # ─────────────────────────────────────────────────────
    def extract_embedding(self, image_bytes: bytes, live: bool = False) -> dict:
        """
        Extract a face embedding.
        Uses face_recognition (128-d) if available, otherwise fallbacks to 
        Mediapipe landmarks-based signature (128-d normalized vector).
        """
        try:
            import numpy as np
            from PIL import Image
            import cv2

            pil_img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            np_img  = np.array(pil_img)

            # ── Low-light enhancement ─────────────────────
            np_img = self._enhance_low_light(np_img)

            # ── Liveness variance check (live frames only) ──
            if live:
                gray_var = float(np.std(np.mean(np_img, axis=2)))
                if gray_var < MIN_LIVENESS_VARIANCE:
                    return _result('low_quality', None, 0.0,
                                   'Image appears to be a static photo or screen. '
                                   'Please use a live camera feed.')

            # ── Face detection & Encoding ──
            embedding = None
            quality = 0.0
            face_locations = []

            # 1. Try face_recognition (State-of-the-art 128-d vector)
            try:
                import face_recognition
                face_locations = face_recognition.face_locations(np_img, model='hog')
                if face_locations:
                    encodings = face_recognition.face_encodings(
                        np_img, face_locations, num_jitters=1, model='large'
                    )
                    if encodings:
                        embedding = encodings[0].tolist()
                        
                        top, right, bottom, left = face_locations[0]
                        face_area = (bottom - top) * (right - left)
                        img_area  = np_img.shape[0] * np_img.shape[1]
                        quality   = min(1.0, round((face_area / img_area) * 8, 3))
            except (ImportError, Exception):
                pass

            # 2. Fallback to Robust Pseudo-embedding (Histogram Equalized + Edge Features)
            if not embedding:
                try:
                    # Fallback detection with OpenCV Haar Cascade
                    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                    gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)
                    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                    
                    if len(faces) > 0:
                        (x, y, w, h) = faces[0]
                        face_crop = gray[y:y+h, x:x+w]
                        
                        # Normalize lighting
                        face_norm = cv2.equalizeHist(face_crop)
                        
                        # Extract 128 features (8x8 grayscale + 8x8 edge magnitude)
                        g_feat = cv2.resize(face_norm, (8, 8)).flatten() / 255.0
                        
                        # Edge features
                        sobelx = cv2.Sobel(face_norm, cv2.CV_64F, 1, 0, ksize=3)
                        sobely = cv2.Sobel(face_norm, cv2.CV_64F, 0, 1, ksize=3)
                        mag = cv2.magnitude(sobelx, sobely)
                        e_feat = cv2.resize(mag, (8, 8)).flatten()
                        e_feat = e_feat / (np.max(e_feat) + 1e-6)
                        
                        embedding = np.concatenate([g_feat, e_feat]).tolist()
                        quality = 0.5
                        logger.info("Using robust pseudo-embedding (Grayscale + Edges).")
                except Exception as e:
                    logger.warning(f"Robust fallback failed: {e}")

            if not embedding:
                return _result('no_face', None, 0.0, 'No face detected.')

            return _result('success', embedding, quality, 'OK')

        except Exception as exc:
            logger.exception(f"Embedding extraction failed: {exc}")
            return _result('error', None, 0.0, str(exc))

    # ─────────────────────────────────────────────────────
    #  PUBLIC: compare live frame against stored embedding
    # ─────────────────────────────────────────────────────
    def compare_frame_to_stored(
        self,
        frame_bytes: bytes,
        encrypted_embedding: bytes,
        threshold: float = MATCH_THRESHOLD,
        prev_frame_bytes: Optional[bytes] = None,
    ) -> dict:
        """
        Compare a live camera frame to the student's stored embedding.

        Args:
            frame_bytes:          Current JPEG frame
            encrypted_embedding:  Stored encrypted embedding
            threshold:            Match threshold (0–1); higher = stricter
            prev_frame_bytes:     Previous frame for motion liveness check

        Returns: {match, confidence, distance, event, message, liveness_ok}
        """
        # ── Motion liveness check (only when we have a previous frame) ──
        if prev_frame_bytes is not None:
            liveness_ok = self._check_motion_liveness(frame_bytes, prev_frame_bytes)
            if not liveness_ok:
                return {
                    'match': False, 'confidence': 0.0, 'distance': 1.0,
                    'event': 'low_quality', 'liveness_ok': False,
                    'message': 'No motion detected — possible photo spoofing attempt.',
                }

        # live=True: apply variance check on live frames
        live_result = self.extract_embedding(frame_bytes, live=True)

        if live_result['status'] != 'success':
            return {
                'match': False, 'confidence': 0.0, 'distance': 1.0,
                'event': live_result['status'], 'liveness_ok': True,
                'message': live_result['message'],
            }

        try:
            stored_list = self._encryptor.decrypt_embedding(encrypted_embedding)
            stored_vec  = np.array(stored_list)
            live_vec    = np.array(live_result['embedding'])

            try:
                import face_recognition
                # face_recognition vectors are usually 128-d unit vectors
                distance = float(face_recognition.face_distance([stored_vec], live_vec)[0])
            except (ImportError, Exception):
                # Fallback: simple Euclidean distance
                raw_dist = float(np.linalg.norm(stored_vec - live_vec))
                
                # Normalize fallback distance to be compatible with MATCH_THRESHOLD (0.55)
                # 128-d vector (0-1) max distance is ~11.3. 
                # Typical "match" for grayscale/edges is < 3.5
                # We'll map 3.5 to ~0.45 (the threshold for match if MATCH_THRESHOLD=0.55)
                distance = min(1.0, raw_dist / 7.5) 
                logger.info(f"Fallback distance: {raw_dist:.3f} -> normalized: {distance:.3f}")

            confidence = round(max(0.0, 1.0 - distance), 4)
            # threshold=0.55 → distance must be <= 0.45 to match
            is_match   = distance <= (1.0 - threshold)

            return {
                'match':       is_match,
                'confidence':  confidence,
                'distance':    round(distance, 4),
                'event':       'match_success' if is_match else 'match_failed',
                'liveness_ok': True,
                'message':     'Face verified.' if is_match else f'Face did not match (dist={distance:.3f}).',
            }
        except Exception as exc:
            logger.exception(f"Comparison failed: {exc}")
            return {
                'match': False, 'confidence': 0.0, 'distance': 1.0,
                'event': 'error', 'liveness_ok': True, 'message': str(exc),
            }

    # ─────────────────────────────────────────────────────
    #  PUBLIC: encrypt + checksum ready for DB storage
    # ─────────────────────────────────────────────────────
    def prepare_for_storage(self, embedding_list: list) -> tuple:
        json_str  = json.dumps(embedding_list)
        checksum  = hashlib.sha256(json_str.encode()).hexdigest()
        encrypted = self._encryptor.encrypt_embedding(embedding_list)
        return encrypted, checksum

    # ─────────────────────────────────────────────────────
    #  PRIVATE: motion-based liveness
    # ─────────────────────────────────────────────────────
    def _check_motion_liveness(self, frame_bytes: bytes, prev_frame_bytes: bytes) -> bool:
        """
        Returns True if there is enough pixel motion between two frames.
        A printed photo held in front of the camera will have near-zero motion.
        Threshold is intentionally loose to avoid false rejections from slight
        camera shake or compression artifacts.
        """
        try:
            import numpy as np
            from PIL import Image

            def to_gray_small(b):
                img = Image.open(io.BytesIO(b)).convert('L').resize((64, 48))
                return np.array(img, dtype=np.float32)

            a = to_gray_small(frame_bytes)
            b = to_gray_small(prev_frame_bytes)
            diff = float(np.mean(np.abs(a - b)))
            return diff >= MIN_MOTION_DIFF
        except Exception:
            return True  # if check fails, don't block

    def _enhance_low_light(self, np_img):
        """
        Applies CLAHE (Contrast Limited Adaptive Histogram Equalization)
        if the image is determined to be too dark.
        """
        try:
            import cv2
            import numpy as np

            # Calculate brightness
            avg_brightness = np.mean(np_img)
            if avg_brightness > 65:  # Sufficiently bright
                return np_img

            # Convert to LAB color space
            lab = cv2.cvtColor(np_img, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)

            # Apply CLAHE to L-channel
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)

            # Merge and convert back to RGB
            limg = cv2.merge((cl, a, b))
            enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
            return enhanced
        except Exception as e:
            logger.warning(f"Low-light enhancement failed: {e}")
            return np_img


# ─────────────────────────────────────────────────────────────
#  Module-level singleton — avoids re-instantiating Fernet on every frame
# ─────────────────────────────────────────────────────────────
_service_instance: Optional[FaceService] = None


def get_face_service() -> FaceService:
    global _service_instance
    if _service_instance is None:
        _service_instance = FaceService()
    return _service_instance


# ─────────────────────────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────────────────────────
def _result(status, embedding, quality, message):
    return {'status': status, 'embedding': embedding, 'quality': quality, 'message': message}

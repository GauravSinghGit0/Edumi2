"""
attendance/face_service.py

High-performance, 100% commercially compliant facial recognition service.
Uses OpenCV Model Zoo's YuNet (Face Detection) and SFace (Face Recognition),
both licensed under Apache 2.0 with ZERO non-commercial dataset restrictions.

Architecture:
  - Detection: YuNet ONNX (face_detection_yunet_2023mar.onnx) - Apache 2.0
  - Embeddings: SFace ONNX (face_recognition_sface_2021dec.onnx) - Apache 2.0 (128-d vector)
  - Encryption: Fernet AES-128-CBC + HMAC-SHA256 for data at rest
  - Anti-spoofing: Motion differential liveness and ROI variance checks
"""

import io
import os
import json
import hashlib
import logging
import threading
from typing import Optional
import numpy as np
from PIL import Image
import cv2

from django.conf import settings
from .encryption_service import FaceEncryptionService

logger = logging.getLogger('attendance.face_service')

DEFAULT_MAX_DISTANCE = getattr(settings, 'FACE_MATCH_THRESHOLD', 0.55)
MIN_QUALITY_SCORE = 0.08
MIN_LIVENESS_VARIANCE = 4.0
MIN_MOTION_DIFF = 1.0

# OpenCV Model Zoo SFace official cosine similarity threshold: 0.363
SFACE_COSINE_MATCH_THRESHOLD = 0.363


class FaceService:
    """
    Thread-safe facial recognition service utilizing Apache 2.0 licensed
    YuNet + SFace neural networks via OpenCV DNN.
    """

    def __init__(self):
        self._encryptor = FaceEncryptionService()
        self._model_lock = threading.Lock()
        self._models_loaded = False
        self._detector: Optional[cv2.FaceDetectorYN] = None
        self._recognizer: Optional[cv2.FaceRecognizerSF] = None
        self._init_models()

    def _init_models(self):
        """Initialize YuNet and SFace ONNX models."""
        try:
            base_dir = getattr(settings, 'BASE_DIR', None)
            if not base_dir:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            models_dir = os.path.join(str(base_dir), 'models')
            yunet_path = os.path.join(models_dir, 'face_detection_yunet_2023mar.onnx')
            sface_path = os.path.join(models_dir, 'face_recognition_sface_2021dec.onnx')

            if os.path.exists(yunet_path) and os.path.exists(sface_path):
                self._detector = cv2.FaceDetectorYN.create(
                    model=yunet_path,
                    config='',
                    input_size=(320, 320),
                    score_threshold=0.6,
                    nms_threshold=0.3,
                    top_k=5000
                )
                self._recognizer = cv2.FaceRecognizerSF.create(
                    model=sface_path,
                    config=''
                )
                self._models_loaded = True
                logger.info("YuNet + SFace Apache 2.0 face models loaded successfully.")
            else:
                logger.error(f"ONNX model files not found in {models_dir}. Falling back to Haar cascades.")
        except Exception as e:
            logger.error(f"Failed to initialize YuNet / SFace models: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────
    #  PUBLIC: extract embedding from raw image bytes
    #  live=False  -> registration (skip liveness variance check)
    #  live=True   -> live frame (apply liveness variance check on face ROI)
    # ─────────────────────────────────────────────────────
    def extract_embedding(self, image_bytes: bytes, live: bool = False) -> dict:
        """
        Extract a 128-d face embedding using Apache 2.0 YuNet + SFace.
        """
        try:
            pil_img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            np_img = np.array(pil_img)

            # 1. Low-light enhancement
            np_img = self._enhance_low_light(np_img)

            # Convert RGB to BGR for OpenCV
            bgr_img = cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)
            h, w = bgr_img.shape[:2]

            embedding = None
            quality = 0.0
            algo = 'sface_128d'
            face_roi_coords = None

            # 2. Try YuNet + SFace (Commercially Clean 128-d vector)
            if self._models_loaded and self._detector is not None and self._recognizer is not None:
                with self._model_lock:
                    self._detector.setInputSize((w, h))
                    _, faces = self._detector.detect(bgr_img)

                if faces is not None and len(faces) > 1:
                    return _result('multiple_faces', None, 0.0,
                                   'Multiple faces detected. Only one person must be visible in frame.', algo=None)

                if faces is not None and len(faces) == 1:
                    face = faces[0]
                    fx, fy, fw, fh = max(0, int(face[0])), max(0, int(face[1])), int(face[2]), int(face[3])
                    face_roi_coords = (fy, fx + fw, fy + fh, fx)

                    if fw < 50 or fh < 50:
                        return _result('poor_quality', None, 0.0,
                                       'Face is too far or too small. Please move closer to camera.', algo=None)

                    face_roi = bgr_img[fy:min(h, fy + fh), fx:min(w, fx + fw)]

                    # Registration compliance checks: Lighting, Mask, Glasses, Background
                    if not live and face_roi.size > 0:
                        light_ok, light_msg = self._check_face_lighting(face_roi)
                        if not light_ok:
                            return _result('poor_lighting', None, 0.0, light_msg, algo=None)

                        is_masked, mask_msg = self._detect_face_mask(face_roi)
                        if is_masked:
                            return _result('mask_detected', None, 0.0, mask_msg, algo=None)

                        has_glasses, glass_msg = self._detect_glasses(face_roi, face)
                        if has_glasses:
                            return _result('glasses_detected', None, 0.0, glass_msg, algo=None)

                        bg_ok, bg_msg = self._check_plain_background(bgr_img, face_roi_coords)
                        if not bg_ok:
                            return _result('busy_background', None, 0.0, bg_msg, algo=None)

                    with self._model_lock:
                        aligned_face = self._recognizer.alignCrop(bgr_img, face)
                        feature = self._recognizer.feature(aligned_face)

                    if feature is not None and len(feature) > 0:
                        embedding = feature[0].tolist()
                        algo = 'sface_128d'
                        face_area = fw * fh
                        img_area = w * h
                        quality = min(1.0, round((face_area / img_area) * 8, 3))

            # 3. Fallback: Robust OpenCV Pseudo-embedding (Histogram Equalized + Edge Features)
            if not embedding:
                try:
                    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                    gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(gray, 1.1, 4)

                    if len(faces) > 1:
                        return _result('multiple_faces', None, 0.0,
                                       'Multiple faces detected. Only one person must be visible in frame.', algo=None)
                    if len(faces) == 1:
                        (x, y, fw, fh) = faces[0]
                        face_roi_coords = (y, x + fw, y + fh, x)
                        if fw < 50 or fh < 50:
                            return _result('poor_quality', None, 0.0,
                                           'Face is too far or too small. Please move closer.', algo=None)

                        face_crop = gray[y:y+fh, x:x+fw]
                        face_norm = cv2.equalizeHist(face_crop)

                        g_feat = cv2.resize(face_norm, (8, 8)).flatten() / 255.0
                        sobelx = cv2.Sobel(face_norm, cv2.CV_64F, 1, 0, ksize=3)
                        sobely = cv2.Sobel(face_norm, cv2.CV_64F, 0, 1, ksize=3)
                        mag = cv2.magnitude(sobelx, sobely)
                        e_feat = cv2.resize(mag, (8, 8)).flatten()
                        e_feat = e_feat / (np.max(e_feat) + 1e-6)

                        embedding = np.concatenate([g_feat, e_feat]).tolist()
                        algo = 'opencv_pseudo'
                        quality = 0.5
                except Exception as e:
                    logger.warning(f"Haar cascade fallback failed: {e}")

            if not embedding or face_roi_coords is None:
                return _result('no_face', None, 0.0, 'No face detected.', algo=None)

            # 4. Liveness variance check on detected face ROI (for live frames)
            if live:
                top, right, bottom, left = face_roi_coords
                face_roi = np_img[max(0, top):min(h, bottom), max(0, left):min(w, right)]
                if face_roi.size > 0:
                    gray_var = float(np.std(np.mean(face_roi, axis=2)))
                    if gray_var < MIN_LIVENESS_VARIANCE:
                        return _result('low_quality', None, 0.0,
                                       'Face appears to be a static photo or screen. '
                                       'Please use a live camera feed.', algo=algo)

            # Disallow pseudo-embedding registration in production
            if not live and algo == 'opencv_pseudo':
                allow_pseudo = getattr(settings, 'ALLOW_PSEUDO_FACE', False) or getattr(settings, 'DEBUG', False)
                if not allow_pseudo:
                    return _result('error', None, 0.0,
                                   'High-accuracy face models (YuNet/SFace) are unavailable. '
                                   'Face registration is disabled for security.', algo=None)

            return _result('success', embedding, quality, 'OK', algo=algo)

        except Exception as exc:
            logger.exception(f"Embedding extraction failed: {exc}")
            return _result('error', None, 0.0, str(exc), algo=None)

    # ─────────────────────────────────────────────────────
    #  PUBLIC: compare live frame against stored embedding
    # ─────────────────────────────────────────────────────
    def compare_frame_to_stored(
        self,
        frame_bytes: bytes,
        encrypted_embedding: bytes,
        threshold: Optional[float] = None,
        prev_frame_bytes: Optional[bytes] = None,
    ) -> dict:
        """
        Compare a live camera frame to the student's stored embedding.
        Uses SFace cosine matching (Apache 2.0).
        """
        if threshold is None:
            threshold = getattr(settings, 'FACE_MATCH_THRESHOLD', DEFAULT_MAX_DISTANCE)

        # Motion liveness check
        if prev_frame_bytes is not None:
            liveness_ok = self._check_motion_liveness(frame_bytes, prev_frame_bytes)
            if not liveness_ok:
                return {
                    'match': False, 'confidence': 0.0, 'distance': 1.0,
                    'event': 'low_quality', 'liveness_ok': False,
                    'message': 'No motion detected — possible photo spoofing attempt.',
                }

        # Extract live embedding
        live_result = self.extract_embedding(frame_bytes, live=True)
        if live_result['status'] != 'success':
            return {
                'match': False, 'confidence': 0.0, 'distance': 1.0,
                'event': live_result['status'], 'liveness_ok': True,
                'message': live_result['message'],
            }

        try:
            stored_data = self._encryptor.decrypt_embedding(encrypted_embedding)
            if isinstance(stored_data, dict):
                stored_algo = stored_data.get('algo', 'sface_128d')
                stored_vec = np.array(stored_data.get('data', []), dtype=np.float32)
            else:
                stored_algo = 'sface_128d'
                stored_vec = np.array(stored_data, dtype=np.float32)

            live_algo = live_result.get('algo', 'sface_128d')
            live_vec = np.array(live_result['embedding'], dtype=np.float32)

            # Model Compatibility Guard
            if stored_algo != live_algo:
                logger.warning(f"Face model mismatch: stored={stored_algo}, live={live_algo}")
                return {
                    'match': False, 'confidence': 0.0, 'distance': 1.0,
                    'event': 'algo_mismatch', 'liveness_ok': True,
                    'message': f'Face recognition algorithm changed ({stored_algo} vs {live_algo}). Please re-register your face profile to update.',
                }

            # SFace Cosine Matching
            if stored_algo == 'sface_128d' and self._recognizer is not None:
                feat1 = stored_vec.reshape(1, -1)
                feat2 = live_vec.reshape(1, -1)
                with self._model_lock:
                    sim = float(self._recognizer.match(feat1, feat2, cv2.FaceRecognizerSF_FR_COSINE))

                # Normalize distance: sim=1.0 -> dist=0.0; sim=0.0 -> dist=1.0
                distance = max(0.0, min(1.0, 1.0 - sim))
                confidence = round(max(0.0, min(1.0, sim)), 4)
                
                # Match condition: cosine distance <= threshold (or cosine sim >= 0.363)
                is_match = (distance <= threshold) or (sim >= SFACE_COSINE_MATCH_THRESHOLD and distance <= 0.65)
            else:
                # Euclidean distance fallback
                norm1 = stored_vec / (np.linalg.norm(stored_vec) + 1e-8)
                norm2 = live_vec / (np.linalg.norm(live_vec) + 1e-8)
                distance = float(np.linalg.norm(norm1 - norm2)) / 2.0
                confidence = round(max(0.0, min(1.0, 1.0 - distance)), 4)
                is_match = distance <= threshold

            return {
                'match': is_match,
                'confidence': confidence,
                'distance': round(distance, 4),
                'event': 'match_success' if is_match else 'match_failed',
                'liveness_ok': True,
                'message': 'Face verified.' if is_match else f'Face did not match (dist={distance:.3f}, max={threshold:.2f}).',
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
    def prepare_for_storage(self, embedding_list: list, algo: str = 'sface_128d') -> tuple:
        payload = {'v': 2, 'algo': algo, 'data': embedding_list}
        json_str = json.dumps(payload)
        checksum = hashlib.sha256(json_str.encode()).hexdigest()
        encrypted = self._encryptor.encrypt_embedding(payload)
        return encrypted, checksum

    # ─────────────────────────────────────────────────────
    #  PRIVATE: motion-based liveness
    # ─────────────────────────────────────────────────────
    def _check_motion_liveness(self, frame_bytes: bytes, prev_frame_bytes: bytes) -> bool:
        try:
            def to_gray_small(b):
                img = Image.open(io.BytesIO(b)).convert('L').resize((64, 48))
                return np.array(img, dtype=np.float32)

            a = to_gray_small(frame_bytes)
            b = to_gray_small(prev_frame_bytes)
            diff = float(np.mean(np.abs(a - b)))
            return diff >= MIN_MOTION_DIFF
        except Exception:
            return True

    def _enhance_low_light(self, np_img):
        try:
            avg_brightness = np.mean(np_img)
            if avg_brightness > 65:
                return np_img

            lab = cv2.cvtColor(np_img, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            limg = cv2.merge((cl, a, b))
            return cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
        except Exception as e:
            logger.warning(f"Low-light enhancement failed: {e}")
            return np_img

    def _check_face_lighting(self, face_roi: np.ndarray) -> tuple:
        """Verify face region is neither pitch dark nor washed out with glare."""
        try:
            gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
            mean_luma = float(np.mean(gray))
            if mean_luma < 48.0:
                return False, 'Low lighting — increase room light.'
            if mean_luma > 222.0:
                return False, 'High glare — reduce direct light.'
            glare_ratio = float(np.mean(gray > 245))
            if glare_ratio > 0.12:
                return False, 'Direct glare detected — diffuse lighting.'
            return True, 'OK'
        except Exception:
            return True, 'OK'

    def _detect_face_mask(self, face_roi: np.ndarray) -> tuple:
        """
        Detect whether a face mask or cloth is covering the mouth/nose.
        Compares upper face skin (forehead/cheeks) with lower face region.
        """
        try:
            rh, rw = face_roi.shape[:2]
            if rh < 40 or rw < 40:
                return False, ''

            upper = face_roi[int(0.12 * rh):int(0.42 * rh), int(0.20 * rw):int(0.80 * rw)]
            lower = face_roi[int(0.52 * rh):int(0.88 * rh), int(0.20 * rw):int(0.80 * rw)]
            if upper.size == 0 or lower.size == 0:
                return False, ''

            u_gray = cv2.cvtColor(upper, cv2.COLOR_BGR2GRAY)
            l_gray = cv2.cvtColor(lower, cv2.COLOR_BGR2GRAY)
            u_mean = float(np.mean(u_gray))
            l_mean = float(np.mean(l_gray))
            luma_ratio = l_mean / (u_mean + 1e-5)

            # Black/dark cloth mask: Lower face significantly darker than upper skin
            if (luma_ratio < 0.80 and l_mean < 72.0) or (l_mean < 48.0 and u_mean > 58.0):
                return True, 'Face covered — please remove mask or covering.'

            # Skin chrominance evaluation in YCrCb
            u_ycrcb = cv2.cvtColor(upper, cv2.COLOR_BGR2YCrCb)
            l_ycrcb = cv2.cvtColor(lower, cv2.COLOR_BGR2YCrCb)
            u_skin = ((u_ycrcb[:, :, 1] >= 130) & (u_ycrcb[:, :, 1] <= 178) & 
                      (u_ycrcb[:, :, 2] >= 75) & (u_ycrcb[:, :, 2] <= 130))
            l_skin = ((l_ycrcb[:, :, 1] >= 130) & (l_ycrcb[:, :, 1] <= 178) & 
                      (l_ycrcb[:, :, 2] >= 75) & (l_ycrcb[:, :, 2] <= 130))

            u_skin_ratio = float(np.mean(u_skin))
            l_skin_ratio = float(np.mean(l_skin))

            # Surgical / White cloth mask
            if u_skin_ratio > 0.28 and l_skin_ratio < 0.25:
                return True, 'Face covered — please uncover mouth and nose.'

            # Surgical blue mask: Blue channel dominates over red in lower face
            b_mean = float(np.mean(lower[:, :, 0]))
            r_mean = float(np.mean(lower[:, :, 2]))
            if b_mean > (r_mean + 15) and b_mean > 65:
                return True, 'Face covered — please remove mask.'

            return False, ''
        except Exception:
            return False, ''

    def _detect_glasses(self, face_roi: np.ndarray, face_data: np.ndarray) -> tuple:
        """
        Detect whether sunglasses or eyeglasses are worn during biometric registration.
        Government portals require an unobstructed face without sunglasses or reflective frames.
        """
        try:
            rh, rw = face_roi.shape[:2]
            if rh < 40 or rw < 40:
                return False, ''

            fx, fy = int(face_data[0]), int(face_data[1])
            re_x, re_y = int(face_data[4]) - fx, int(face_data[5]) - fy
            le_x, le_y = int(face_data[6]) - fx, int(face_data[7]) - fy

            r = max(4, int(rw * 0.12))
            re_patch = face_roi[max(0, re_y - r):min(rh, re_y + r), max(0, re_x - r):min(rw, re_x + r)]
            le_patch = face_roi[max(0, le_y - r):min(rh, le_y + r), max(0, le_x - r):min(rw, le_x + r)]

            upper_skin = face_roi[int(0.08 * rh):int(0.24 * rh), int(0.25 * rw):int(0.75 * rw)]
            forehead_mean = float(np.mean(cv2.cvtColor(upper_skin, cv2.COLOR_BGR2GRAY))) if upper_skin.size > 0 else 120.0

            # 1. Dark Sunglasses Check
            if re_patch.size > 0 and le_patch.size > 0:
                re_mean = float(np.mean(cv2.cvtColor(re_patch, cv2.COLOR_BGR2GRAY)))
                le_mean = float(np.mean(cv2.cvtColor(le_patch, cv2.COLOR_BGR2GRAY)))
                if (re_mean < 45 and le_mean < 45) or (re_mean < forehead_mean * 0.45 and le_mean < forehead_mean * 0.45):
                    return True, 'Eyewear detected — please remove glasses.'
            else:
                eye_band = face_roi[int(0.26 * rh):int(0.42 * rh), int(0.18 * rw):int(0.82 * rw)]
                if eye_band.size > 0:
                    eye_mean = float(np.mean(cv2.cvtColor(eye_band, cv2.COLOR_BGR2GRAY)))
                    if eye_mean < 48 or (forehead_mean > 65 and eye_mean < forehead_mean * 0.45):
                        return True, 'Eyewear detected — please remove glasses.'

            # 2. Eyeglasses Frames & Lens Glare Check
            bridge = face_roi[int(0.26 * rh):int(0.38 * rh), int(0.40 * rw):int(0.60 * rw)]
            if bridge.size > 0:
                bridge_gray = cv2.cvtColor(bridge, cv2.COLOR_BGR2GRAY)
                bridge_edges = cv2.Canny(bridge_gray, 50, 150)
                if float(np.mean(bridge_edges > 0)) > 0.22:
                    return True, 'Eyewear detected — please remove glasses.'

            if re_patch.size > 0 and le_patch.size > 0:
                re_gray = cv2.cvtColor(re_patch, cv2.COLOR_BGR2GRAY)
                le_gray = cv2.cvtColor(le_patch, cv2.COLOR_BGR2GRAY)
                if float(np.mean(re_gray > 235)) > 0.08 or float(np.mean(le_gray > 235)) > 0.08:
                    return True, 'Lens glare detected — please remove glasses.'

            return False, ''
        except Exception:
            return False, ''

    def _check_plain_background(self, bgr_img: np.ndarray, face_roi_coords: tuple) -> tuple:
        """
        Check that background around the subject is plain/uniform (not busy or textured).
        Government standards require a plain, neutral light background.
        """
        try:
            h, w = bgr_img.shape[:2]
            gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)

            top, right, bottom, left = face_roi_coords
            # Top-left and top-right background regions outside head
            bg_tl = gray[0:max(1, int(top * 0.8)), 0:max(1, int(left * 0.85))]
            bg_tr = gray[0:max(1, int(top * 0.8)), min(w - 1, int(right + (w - right) * 0.15)):w]

            # Fallback to corner blocks if face is too close to border
            if bg_tl.size < 100:
                bg_tl = gray[0:int(0.25 * h), 0:int(0.20 * w)]
            if bg_tr.size < 100:
                bg_tr = gray[0:int(0.25 * h), int(0.80 * w):w]

            def is_patch_busy(patch):
                if patch.size < 50:
                    return False
                std = float(np.std(patch))
                edges = cv2.Canny(patch, 40, 120)
                edge_ratio = float(np.mean(edges > 0)) * 100
                return std > 38.0 and edge_ratio > 10.0

            if is_patch_busy(bg_tl) or is_patch_busy(bg_tr):
                return False, 'Busy background — please use a plain wall.'

            return True, 'OK'
        except Exception:
            return True, 'OK'


# ─────────────────────────────────────────────────────────────
#  Module-level singleton
# ─────────────────────────────────────────────────────────────
_service_instance: Optional[FaceService] = None


def get_face_service() -> FaceService:
    global _service_instance
    if _service_instance is None:
        _service_instance = FaceService()
    return _service_instance


def _result(status, embedding, quality, message, algo=None):
    return {'status': status, 'embedding': embedding, 'quality': quality, 'message': message, 'algo': algo}

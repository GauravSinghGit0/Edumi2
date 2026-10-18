"""
WebSocket consumer for real-time face-recognition attendance.

Route: ws/attendance/<meeting_code>/

  - Rolling vote buffer: requires N consecutive matches before counting a verified interval
  - Passes previous frame to FaceService for motion-based liveness (anti-spoofing)
  - Per-classroom confidence threshold respected
  - Late detection uses meeting.created_at (actual live start) not scheduled_time
  - Uses module-level FaceService singleton to avoid re-instantiating Fernet per frame
"""
import json
import base64
import logging
from collections import deque

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger('attendance.consumers')

# Rolling vote buffer settings
VOTE_BUFFER_SIZE = 5
MIN_VOTES_REQUIRED = 3


class FaceAttendanceConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user         = self.scope.get('user')
        self.meeting_code = self.scope['url_route']['kwargs']['meeting_code']

        if not self.user or not self.user.is_authenticated or not getattr(self.user, 'is_active', True):
            await self.close(code=4003)
            return

        has_access = await self.verify_attendance_access()
        if not has_access:
            logger.warning(f"Unauthorized face attendance WS attempt by {getattr(self.user, 'username', 'anonymous')} for meeting {self.meeting_code}")
            await self.close(code=4003)
            return

        # Accept early so handshake completes cleanly without ERR_CONNECTION_RESET
        await self.accept()

        # Skip face attendance for admins/superusers
        if self.user.is_superuser:
            await self.send(json.dumps({
                'type':        'connected',
                'interval':    999999,  # No need for captures
                'message':     'Admin user - face attendance disabled.',
                'has_profile': True,  # Don't prompt for profile
                'admin_exempt': True,
            }))
            return

        try:
            self.att_settings      = await self.get_settings()
            self.encrypted_emb     = await self.get_encrypted_embedding()
            self.verified_seconds  = 0
            self.attendance_marked = False
            self.join_time         = timezone.now()

            # Rolling vote buffer — track last 5 frame results
            self._vote_buffer = deque(maxlen=VOTE_BUFFER_SIZE)
            # Keep last raw frame bytes for motion liveness check
            self._prev_frame  = None

            await self.send(json.dumps({
                'type':        'connected',
                'interval':    self.att_settings.get('interval', 15),
                'message':     'Face recognition active.',
                'has_profile': self.encrypted_emb is not None,
            }))

            if self.encrypted_emb is None:
                await self.send(json.dumps({
                    'type':    'no_profile',
                    'message': 'No face profile found. Please register your face in Settings.',
                }))
        except Exception as e:
            logger.error(f"Error initializing FaceAttendanceConsumer: {e}", exc_info=True)

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        # Skip for admins or if already marked or no profile
        if self.user.is_superuser:
            return
        if self.attendance_marked or self.encrypted_emb is None:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        if data.get('type') != 'frame':
            return

        frame_b64 = data.get('frame', '')
        if not frame_b64:
            return

        try:
            frame_bytes = base64.b64decode(frame_b64)
        except Exception:
            return

        # Run CPU-bound recognition in thread pool
        result = await database_sync_to_async(self._run_recognition)(frame_bytes)

        # Store frame for next liveness check
        self._prev_frame = frame_bytes

        # Log the attempt
        await self._log_attempt(result['event'], result['confidence'])

        # Rolling vote buffer — track last 5 frames
        is_match = bool(result.get('match', False))
        self._vote_buffer.append(is_match)
        positive_votes = sum(1 for v in self._vote_buffer if v)

        if is_match:
            interval = self.att_settings.get('interval', 15)
            self.verified_seconds += interval
            req_seconds = self.att_settings.get('presence_duration', 30)

            if self.verified_seconds >= req_seconds and positive_votes >= MIN_VOTES_REQUIRED:
                await self._mark_present(result['confidence'])
                self.attendance_marked = True
                await self.send(json.dumps({
                    'type':       'attendance_marked',
                    'status':     'present',
                    'confidence': result['confidence'],
                    'message':    'Attendance recorded successfully.',
                }))
            else:
                await self.send(json.dumps({
                    'type':             'verification_progress',
                    'confidence':       result['confidence'],
                    'verified_seconds': self.verified_seconds,
                    'required_seconds': req_seconds,
                    'consecutive':      positive_votes,
                    'consecutive_req':  MIN_VOTES_REQUIRED,
                    'message':          f'Verified {self.verified_seconds}s / {req_seconds}s',
                }))
        else:
            await self.send(json.dumps({
                'type':        'verification_failed',
                'event':       result.get('event', 'match_failed'),
                'confidence':  result.get('confidence', 0.0),
                'consecutive': positive_votes,
                'message':     result.get('message', 'Face not recognized.'),
            }))

    # ── Sync helpers ─────────────────────────────────────────────

    def _run_recognition(self, frame_bytes: bytes) -> dict:
        from django.conf import settings
        from .face_service import get_face_service
        svc       = get_face_service()
        default_th = getattr(settings, 'FACE_MATCH_THRESHOLD', 0.55)
        threshold = self.att_settings.get('confidence_threshold', default_th)
        return svc.compare_frame_to_stored(
            frame_bytes,
            self.encrypted_emb,
            threshold=threshold,
            prev_frame_bytes=self._prev_frame,
        )

    # ── Async DB helpers ──────────────────────────────────────────

    @database_sync_to_async
    def verify_attendance_access(self):
        from meetings.models import Meeting, ClassroomMembership
        try:
            meeting = Meeting.objects.select_related('classroom').get(
                meeting_code=self.meeting_code
            )
        except Meeting.DoesNotExist:
            return False

        if not self.user or not self.user.is_authenticated or not getattr(self.user, 'is_active', True):
            return False

        if self.user.is_superuser or getattr(self.user, 'is_staff', False):
            return True
        if hasattr(self.user, 'userprofile') and self.user.userprofile.user_type == 'admin':
            return True

        # If meeting is tied to a classroom, require approved student membership
        if meeting.classroom_id:
            return ClassroomMembership.objects.filter(
                classroom_id=meeting.classroom_id,
                student_id=self.user.id,
                status='approved'
            ).exists()

        return True

    @database_sync_to_async
    def get_encrypted_embedding(self):
        from .models import StudentFaceProfile
        try:
            profile = StudentFaceProfile.objects.get(student=self.user, is_active=True)
            return bytes(profile.face_embedding_encrypted)
        except StudentFaceProfile.DoesNotExist:
            return None

    @database_sync_to_async
    def get_settings(self) -> dict:
        from django.conf import settings
        from meetings.models import Meeting
        from .models import AttendanceSettings
        default_th = getattr(settings, 'FACE_MATCH_THRESHOLD', 0.55)
        defaults = {
            'interval': 15, 'presence_duration': 30, 'late_threshold': 10,
            'enabled': True, 'confidence_threshold': default_th,
        }
        try:
            meeting = Meeting.objects.select_related('classroom').get(
                meeting_code=self.meeting_code
            )
            if not meeting.classroom:
                return defaults
            s, _ = AttendanceSettings.objects.get_or_create(classroom=meeting.classroom)
            return {
                'interval':             s.recognition_interval_seconds,
                'presence_duration':    s.presence_duration_seconds,
                'late_threshold':       s.late_threshold_minutes,
                'enabled':              s.face_recognition_enabled,
                'confidence_threshold': s.confidence_threshold,
                'meeting_started_at':   meeting.created_at,
            }
        except Exception:
            return defaults

    @database_sync_to_async
    def _mark_present(self, confidence: float):
        from meetings.models import Meeting
        from .models import AttendanceRecord
        now            = timezone.now()
        late_threshold = self.att_settings.get('late_threshold', 10)

        try:
            meeting = Meeting.objects.select_related('classroom').get(
                meeting_code=self.meeting_code
            )
            # Use created_at as the actual meeting start time (when teacher started it)
            # scheduled_time is set at creation and may be in the past
            meeting_start = self.att_settings.get('meeting_started_at') or meeting.created_at
            minutes_since_start = max(
                0, (self.join_time - meeting_start).total_seconds() / 60
            )
            status = 'late' if minutes_since_start > late_threshold else 'present'
        except Exception:
            meeting = None
            status  = 'present'

        if meeting:
            AttendanceRecord.objects.update_or_create(
                student=self.user,
                meeting=meeting,
                defaults={
                    'classroom':             meeting.classroom,
                    'date':                  now.date(),
                    'status':                status,
                    'face_match_confidence': confidence,
                    'face_verified_at':      now,
                    'marked_present_at':     now,
                    'verification_method':   'face_recognition',
                }
            )
            from .models import StudentFaceProfile
            StudentFaceProfile.objects.filter(student=self.user).update(last_verified_at=now)

    @database_sync_to_async
    def _log_attempt(self, event_type: str, confidence: float):
        from meetings.models import Meeting
        from .models import FaceRecognitionLog
        try:
            meeting = Meeting.objects.get(meeting_code=self.meeting_code)
            FaceRecognitionLog.objects.create(
                student=self.user,
                meeting=meeting,
                event_type=event_type,
                confidence_score=confidence,
            )
        except Exception:
            pass

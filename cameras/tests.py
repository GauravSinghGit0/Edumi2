from django.test import override_settings
from common.test_base import TeacherUserFactory, BaseTestCase
from .models import Camera, CameraRecording, CameraPermission
from .recording_engine import RecordingEngine

class CameraModelTests(BaseTestCase):
    """Test Camera model and permissions"""

    def setUp(self):
        self.teacher = TeacherUserFactory()
        self.camera = Camera.objects.create(
            name='Test Camera 1',
            ip_address='127.0.0.1',
            port=554,
            stream_path='rtsp://localhost:8554/test',
            camera_type='rtsp',
            is_active=True
        )
        CameraPermission.objects.create(camera=self.camera, teacher=self.teacher)

    def test_camera_creation(self):
        """Test camera is created with correct attributes"""
        self.assertEqual(self.camera.name, 'Test Camera 1')
        self.assertTrue(self.camera.is_active)

    def test_camera_stream_url_generation(self):
        """Test get_stream_url method"""
        url = self.camera.get_stream_url()
        self.assertIn('rtsp://', url)

    def test_camera_permission_check(self):
        """Test teacher permission check"""
        self.assertTrue(self.camera.has_permission(self.teacher))
        other_teacher = TeacherUserFactory()
        self.assertFalse(self.camera.has_permission(other_teacher))

    def test_camera_soft_delete(self):
        """Test camera deactivation"""
        camera_id = self.camera.id
        self.camera.is_active = False
        self.camera.save()
        self.assertFalse(self.camera.is_active)
        self.assertTrue(Camera.objects.filter(id=camera_id).exists())


class RecordingEngineTests(BaseTestCase):
    """Test RecordingEngine functionality"""

    def setUp(self):
        self.teacher = TeacherUserFactory()
        self.camera = Camera.objects.create(
            name='Recording Test Camera',
            ip_address='127.0.0.1',
            port=554,
            stream_path='rtsp://localhost:8554/test',
            camera_type='rtsp',
            is_active=True,
            is_live=True
        )

    @override_settings(MEDIA_ROOT='/tmp/test_media')
    def test_recording_metadata_creation(self):
        """Test recording creates DB record"""
        rec = CameraRecording.objects.create(
            camera=self.camera,
            teacher=self.teacher,
            title='Test Recording',
            recording_status='recording'
        )
        self.assertEqual(rec.camera, self.camera)
        self.assertEqual(rec.teacher, self.teacher)
        self.assertEqual(rec.recording_status, 'recording')

    def test_recording_state_check(self):
        """Test is_recording state check"""
        is_rec, start_time = RecordingEngine.is_recording(
            self.camera.id,
            self.teacher.id
        )
        self.assertFalse(is_rec)
        self.assertIsNone(start_time)

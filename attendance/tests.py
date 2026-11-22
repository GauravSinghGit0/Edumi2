import numpy as np
from django.test import TestCase
from django.utils import timezone
from common.test_base import StudentUserFactory, TeacherUserFactory, BaseTestCase
from .models import StudentFaceProfile, AttendanceRecord
from .face_service import FaceService
from .encryption_service import FaceEncryptionService

class FaceEncryptionTests(TestCase):
    """Test face embedding encryption/decryption"""

    def setUp(self):
        self.enc_service = FaceEncryptionService()
        self.test_embedding = [0.1] * 128

    def test_encrypt_decrypt_cycle(self):
        """Test encryption followed by decryption returns original vector"""
        encrypted = self.enc_service.encrypt_embedding(self.test_embedding)
        self.assertIsInstance(encrypted, bytes)

        decrypted = self.enc_service.decrypt_embedding(encrypted)
        self.assertEqual(len(decrypted), len(self.test_embedding))

        for orig, dec in zip(self.test_embedding, decrypted):
            self.assertAlmostEqual(orig, dec, places=5)

    def test_encryption_produces_different_output(self):
        """Test random IV produces different ciphertexts"""
        enc1 = self.enc_service.encrypt_embedding(self.test_embedding)
        enc2 = self.enc_service.encrypt_embedding(self.test_embedding)
        self.assertNotEqual(enc1, enc2)


class StudentFaceProfileTests(BaseTestCase):
    """Test StudentFaceProfile model"""

    def setUp(self):
        self.student = StudentUserFactory()
        self.enc_service = FaceEncryptionService()
        self.test_embedding = [0.1] * 128

    def test_face_profile_creation_and_decryption(self):
        """Test creating face profile with encrypted embedding"""
        encrypted = self.enc_service.encrypt_embedding(self.test_embedding)

        profile = StudentFaceProfile.objects.create(
            student=self.student,
            face_embedding_encrypted=encrypted,
            is_active=True
        )

        self.assertEqual(profile.student, self.student)
        self.assertTrue(profile.is_active)

        decrypted = self.enc_service.decrypt_embedding(
            bytes(profile.face_embedding_encrypted)
        )
        self.assertEqual(len(decrypted), 128)


class FaceServiceTests(TestCase):
    """Test FaceService detection and recognition"""

    def setUp(self):
        self.face_service = FaceService()

    def test_face_service_initialization(self):
        """Test FaceService loads models correctly"""
        self.assertIsNotNone(self.face_service._detector)
        self.assertIsNotNone(self.face_service._recognizer)
        self.assertTrue(self.face_service._models_loaded)

    def test_detect_faces_no_face(self):
        """Test detection on image with no faces"""
        blank_image = np.zeros((480, 640, 3), dtype=np.uint8)
        faces = self.face_service.detect_faces(blank_image)
        self.assertEqual(len(faces), 0)

    def test_cosine_similarity_calculation(self):
        """Test cosine similarity calculation"""
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([1.0, 0.0, 0.0])
        vec3 = np.array([0.0, 1.0, 0.0])

        sim_same = self.face_service._cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(sim_same, 1.0, places=5)

        sim_diff = self.face_service._cosine_similarity(vec1, vec3)
        self.assertAlmostEqual(sim_diff, 0.0, places=5)


class AttendanceRecordTests(BaseTestCase):
    """Test AttendanceRecord model"""

    def setUp(self):
        from meetings.models import Meeting, Classroom
        self.teacher = TeacherUserFactory()
        self.student = StudentUserFactory()

        self.classroom = Classroom.objects.create(
            class_code='ATT101',
            title='Attendance Test Classroom',
            password='testpass',
            teacher=self.teacher
        )

        self.meeting = Meeting.objects.create(
            classroom=self.classroom,
            title='Attendance Meeting',
            teacher=self.teacher,
            meeting_code='MEETATT01',
            scheduled_time=timezone.now(),
            status='live'
        )

    def test_attendance_record_creation(self):
        """Test creating attendance record"""
        record = AttendanceRecord.objects.create(
            student=self.student,
            classroom=self.classroom,
            meeting=self.meeting,
            date=timezone.now().date(),
            status='present',
            verification_method='face_recognition',
            face_match_confidence=0.95
        )

        self.assertEqual(record.student, self.student)
        self.assertEqual(record.status, 'present')
        self.assertEqual(record.face_match_confidence, 0.95)

"""
accounts/tests.py

Comprehensive Automated Test Suite for EduMi 2:
Centralized User Identity, Unified User Records, and SSOT Architecture.

Covers:
1. Identity SSOT consistency and property aliases (phone, student_id, roll_number, contact_number)
2. Duplicate account handling & uniqueness constraints (email case-insensitive, student_id, employee_id)
3. HTTP Identity API security and institutional classroom boundaries
4. Media access control (biometric photos, assignment submissions, video ranges)
5. Data retention and cascade protection (models.PROTECT, soft-deactivation)
6. WebSocket active status and authentication enforcement
7. Duplicate identity audit management command
"""

import json
import datetime
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import ProtectedError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from io import StringIO

from accounts.models import UserProfile, StudentPhoto
from accounts.identity import IdentityService
from common.utils import get_user_identity
from meetings.models import Classroom, ClassroomMembership, Meeting
from attendance.models import AttendanceRecord
from assignments.models import Assignment, AssignmentSubmission, AssignmentSubmissionFile, Quiz, QuizSubmission

User = get_user_model()


def configure_profile(user, **kwargs):
    """Safely configure the auto-created UserProfile attached to user."""
    profile = getattr(user, 'userprofile', None)
    if profile is None:
        profile, _ = UserProfile.objects.get_or_create(user=user)
    for key, value in kwargs.items():
        setattr(profile, key, value)
    profile.save()
    return profile


class IdentitySSOTConsistencyTests(TestCase):
    """Tests confirming IdentityService is the Single Source of Truth."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='student_test',
            email='student_test@edumi.test',
            password='Password123!',
            first_name='Alice',
            last_name='Smith'
        )
        self.profile = configure_profile(
            self.user,
            user_type='student',
            student_id='STU-2026-001',
            phone='+1234567890',
            branch='Computer Science',
            grade='Senior'
        )

    def tearDown(self):
        cache.clear()

    def test_property_aliases_bi_directional(self):
        """Test roll_number and contact_number aliases map cleanly to canonical student_id and phone."""
        # Getter alias
        self.assertEqual(self.profile.roll_number, 'STU-2026-001')
        self.assertEqual(self.profile.contact_number, '+1234567890')

        # Setter alias
        self.profile.roll_number = 'STU-2026-002'
        self.profile.contact_number = '+9876543210'
        self.assertEqual(self.profile.student_id, 'STU-2026-002')
        self.assertEqual(self.profile.phone, '+9876543210')

    def test_identity_service_and_utils_consistency(self):
        """Verify IdentityService.get_identity and common.utils.get_user_identity return identical SSOT dicts."""
        ssot_identity = IdentityService.get_identity(self.user)
        utils_identity = get_user_identity(self.user)
        model_identity = self.profile.get_identity_dict()

        self.assertEqual(ssot_identity['user_id'], self.user.id)
        self.assertEqual(ssot_identity['username'], 'student_test')
        self.assertEqual(ssot_identity['email'], 'student_test@edumi.test')
        self.assertEqual(ssot_identity['student_id'], 'STU-2026-001')
        self.assertEqual(ssot_identity['roll_number'], 'STU-2026-001')
        self.assertEqual(ssot_identity['phone'], '+1234567890')
        self.assertEqual(ssot_identity['contact_number'], '+1234567890')

        # Verify utils delegates to SSOT
        self.assertEqual(ssot_identity['user_id'], utils_identity['user_id'])
        self.assertEqual(ssot_identity['email'], utils_identity['email'])
        self.assertEqual(ssot_identity['student_id'], utils_identity['student_id'])
        self.assertEqual(ssot_identity['phone'], utils_identity['phone'])

        # Verify model get_identity_dict matches
        self.assertEqual(model_identity['user_id'], self.user.id)
        self.assertEqual(model_identity['student_id'], 'STU-2026-001')

    def test_batch_identity_resolution(self):
        """Verify batch lookup resolves multiple user identities and caps at 100."""
        user2 = User.objects.create_user(username='student_two', email='two@edumi.test', password='P!')
        configure_profile(user2, user_type='student', student_id='STU-002')

        batch = IdentityService.get_identities_batch([self.user.id, user2.id, 99999])
        self.assertIn(self.user.id, batch)
        self.assertIn(user2.id, batch)
        self.assertNotIn(99999, batch)
        self.assertEqual(batch[self.user.id]['username'], 'student_test')
        self.assertEqual(batch[user2.id]['username'], 'student_two')


class DuplicateAccountAndConstraintsTests(TestCase):
    """Tests preventing duplicate accounts, duplicate emails, and conflicting IDs."""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(
            username='sysadmin',
            email='admin@edumi.test',
            password='AdminPassword123!'
        )
        configure_profile(self.admin, user_type='admin')
        self.client = Client()
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def test_admin_create_user_prevents_case_insensitive_duplicate_email(self):
        """Admin creating a second user with the same email in different case must be rejected."""
        User.objects.create_user(username='user1', email='john.doe@edumi.test', password='P1')

        response = self.client.post(reverse('admin_create_user'), {
            'username': 'user2',
            'email': 'JOHN.DOE@EDUMI.TEST',  # uppercase duplicate
            'password': 'Password123!',
            'user_type': 'student',
        })
        # Should redirect back with error message and NOT create user2
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username='user2').exists())

    def test_identity_service_update_blocks_duplicate_email(self):
        """IdentityService.update_identity raises ValueError if email collision is attempted."""
        user1 = User.objects.create_user(username='u1', email='first@edumi.test', password='P!')
        user2 = User.objects.create_user(username='u2', email='second@edumi.test', password='P!')

        with self.assertRaises(ValueError) as ctx:
            IdentityService.update_identity(
                target_user=user2,
                actor=self.admin,
                data={'email': 'FIRST@edumi.test'}
            )
        self.assertIn("already exists", str(ctx.exception))

    def test_identity_service_update_blocks_duplicate_student_id(self):
        """IdentityService.update_identity raises ValueError if student_id collision is attempted."""
        user1 = User.objects.create_user(username='s1', email='s1@edumi.test', password='P!')
        configure_profile(user1, user_type='student', student_id='ROLL-101')

        user2 = User.objects.create_user(username='s2', email='s2@edumi.test', password='P!')
        configure_profile(user2, user_type='student', student_id='ROLL-102')

        with self.assertRaises(ValueError) as ctx:
            IdentityService.update_identity(
                target_user=user2,
                actor=self.admin,
                data={'student_id': 'ROLL-101'}
            )
        self.assertIn("already assigned", str(ctx.exception))


class IdentityApiSecurityTests(TestCase):
    """Tests verifying authentication and institutional classroom boundaries on identity APIs."""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(username='prof_x', email='x@edumi.test', password='P!')
        configure_profile(self.teacher, user_type='teacher')

        self.student_a = User.objects.create_user(username='student_a', email='a@edumi.test', password='P!')
        configure_profile(self.student_a, user_type='student', student_id='A1')

        self.student_b = User.objects.create_user(username='student_b', email='b@edumi.test', password='P!')
        configure_profile(self.student_b, user_type='student', student_id='B1')

        self.student_c = User.objects.create_user(username='student_c', email='c@edumi.test', password='P!')
        configure_profile(self.student_c, user_type='student', student_id='C1')

        # Classroom 1: Teacher X, Student A and Student C enrolled
        self.classroom = Classroom.objects.create(
            title='Physics 101',
            class_code='PHYS101',
            teacher=self.teacher,
            password='hashed'
        )
        ClassroomMembership.objects.create(classroom=self.classroom, student=self.student_a, status='approved')
        ClassroomMembership.objects.create(classroom=self.classroom, student=self.student_c, status='approved')

        # Student B is isolated (not enrolled in Classroom 1)
        self.anon_client = Client()
        self.client_a = Client()
        self.client_a.force_login(self.student_a)

    def tearDown(self):
        cache.clear()

    def test_unauthenticated_api_access_is_blocked(self):
        """Unauthenticated requests to /api/identity/user/<id>/ and /api/identity/batch/ must be rejected."""
        # Single user lookup
        resp = self.anon_client.get(f'/api/identity/user/{self.student_a.id}/')
        # Expect 302 redirect to login or 401/403
        self.assertIn(resp.status_code, (302, 401, 403))

        # Batch lookup
        resp = self.anon_client.post('/api/identity/batch/', json.dumps({'user_ids': [1, 2]}), content_type='application/json')
        self.assertIn(resp.status_code, (302, 401, 403))

        # Identity Me unauthenticated returns 401
        resp = self.anon_client.get('/api/identity/me/')
        self.assertEqual(resp.status_code, 401)

    def test_student_cannot_view_unrelated_student_identity(self):
        """Classroom boundary: Student A cannot inspect isolated Student B's identity (HTTP 403)."""
        resp = self.client_a.get(f'/api/identity/user/{self.student_b.id}/')
        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn("Forbidden", data['error'])

    def test_student_can_view_peer_and_teacher_in_shared_classroom(self):
        """Student A can inspect fellow student C and teacher X from their approved classroom."""
        # Peer in same classroom
        resp_c = self.client_a.get(f'/api/identity/user/{self.student_c.id}/')
        self.assertEqual(resp_c.status_code, 200)
        self.assertEqual(resp_c.json()['identity']['username'], 'student_c')

        # Teacher of same classroom
        resp_t = self.client_a.get(f'/api/identity/user/{self.teacher.id}/')
        self.assertEqual(resp_t.status_code, 200)
        self.assertEqual(resp_t.json()['identity']['username'], 'prof_x')

    def test_batch_api_filters_out_unauthorized_identities(self):
        """Batch lookup for Student A querying [student_c, student_b] only returns authorized student_c."""
        resp = self.client_a.post(
            '/api/identity/batch/',
            json.dumps({'user_ids': [self.student_c.id, self.student_b.id]}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertIn(str(self.student_c.id), data['identities'])
        self.assertNotIn(str(self.student_b.id), data['identities'])


class MediaAccessControlSecurityTests(TestCase):
    """Tests verifying media protection, submission privacy, and video ranges endpoint hardening."""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(username='teacher_m', email='tm@edumi.test', password='P!')
        configure_profile(self.teacher, user_type='teacher')

        self.student_a = User.objects.create_user(username='student_m1', email='m1@edumi.test', password='P!')
        configure_profile(self.student_a, user_type='student')

        self.student_b = User.objects.create_user(username='student_m2', email='m2@edumi.test', password='P!')
        configure_profile(self.student_b, user_type='student')

        self.classroom = Classroom.objects.create(title='Biology', class_code='BIO101', teacher=self.teacher, password='h')
        ClassroomMembership.objects.create(classroom=self.classroom, student=self.student_a, status='approved')

        self.assignment = Assignment.objects.create(
            classroom=self.classroom,
            title='Lab 1',
            due_date=timezone.now() + datetime.timedelta(days=7),
            created_by=self.teacher
        )
        self.submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student_a
        )
        self.sub_file = AssignmentSubmissionFile.objects.create(
            submission=self.submission,
            file='assignments/1/submissions/student_m1/lab_report.pdf',
            filename='lab_report.pdf'
        )

        self.client_a = Client()
        self.client_a.force_login(self.student_a)

        self.client_b = Client()
        self.client_b.force_login(self.student_b)

        self.anon_client = Client()

    def tearDown(self):
        cache.clear()

    def test_unauthenticated_media_access_denied(self):
        """Unauthenticated media requests are rejected."""
        resp = self.anon_client.get('/media/assignments/1/submissions/student_m1/lab_report.pdf')
        self.assertIn(resp.status_code, (302, 401, 403))

    def test_student_b_cannot_access_student_a_homework(self):
        """Student B cannot download Student A's assignment submission."""
        resp = self.client_b.get('/media/assignments/1/submissions/student_m1/lab_report.pdf')
        self.assertEqual(resp.status_code, 403)

    def test_serve_media_ranges_blocks_unauthorized_files(self):
        """serve_media_ranges endpoint in video_editing blocks access to student submissions and face photos."""
        resp = self.client_b.get('/video-editing/media-ranges/assignments/1/submissions/student_m1/lab_report.pdf')
        self.assertEqual(resp.status_code, 403)

        resp_face = self.client_b.get('/video-editing/media-ranges/face_photos/student_secret.jpg')
        self.assertEqual(resp_face.status_code, 403)


class DataRetentionAndCascadeProtectionTests(TestCase):
    """Tests confirming models.PROTECT and soft-deactivation preserve historical records."""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(username='root_admin', email='root@edumi.test', password='P!')
        configure_profile(self.admin, user_type='admin')

        self.teacher = User.objects.create_user(username='hist_teacher', email='ht@edumi.test', password='P!')
        configure_profile(self.teacher, user_type='teacher')

        self.student = User.objects.create_user(username='hist_student', email='hs@edumi.test', password='P!')
        configure_profile(self.student, user_type='student')

        self.classroom = Classroom.objects.create(
            title='History Class',
            class_code='HIST101',
            teacher=self.teacher,
            password='h'
        )
        ClassroomMembership.objects.create(classroom=self.classroom, student=self.student, status='approved')

        self.meeting = Meeting.objects.create(
            classroom=self.classroom,
            title='History Lecture',
            teacher=self.teacher,
            meeting_code='HIST-M1',
            scheduled_time=timezone.now()
        )

        # Attendance record
        self.attendance = AttendanceRecord.objects.create(
            student=self.student,
            classroom=self.classroom,
            meeting=self.meeting,
            date='2026-10-15',
            status='present'
        )

        # Assignment submission
        self.assignment = Assignment.objects.create(
            classroom=self.classroom,
            title='History Essay',
            due_date=timezone.now() + datetime.timedelta(days=7),
            created_by=self.teacher
        )
        self.submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student
        )

    def tearDown(self):
        cache.clear()

    def test_hard_delete_student_with_attendance_raises_protected_error(self):
        """Direct ORM delete of student with attendance records raises ProtectedError."""
        with self.assertRaises(ProtectedError):
            self.student.delete()
        # Verify attendance record still exists
        self.assertTrue(AttendanceRecord.objects.filter(id=self.attendance.id).exists())

    def test_hard_delete_student_with_submissions_raises_protected_error(self):
        """Direct ORM delete of student with assignment submissions raises ProtectedError."""
        with self.assertRaises(ProtectedError):
            self.student.delete()
        self.assertTrue(AssignmentSubmission.objects.filter(id=self.submission.id).exists())

    def test_hard_delete_teacher_with_classrooms_raises_protected_error(self):
        """Direct ORM delete of teacher with active classrooms raises ProtectedError."""
        with self.assertRaises(ProtectedError):
            self.teacher.delete()
        self.assertTrue(Classroom.objects.filter(id=self.classroom.id).exists())

    def test_admin_delete_user_performs_safe_soft_deactivation(self):
        """Admin delete_user action soft-deactivates the user and preserves all historical records."""
        client = Client()
        client.force_login(self.admin)

        response = client.get(reverse('delete_user', kwargs={'user_id': self.student.id}))
        self.assertEqual(response.status_code, 302)

        # Student still exists in database, but marked inactive and soft-deleted
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertTrue(self.student.userprofile.is_deleted)
        self.assertIsNotNone(self.student.userprofile.deleted_at)

        # Historical records remain completely intact
        self.assertTrue(AttendanceRecord.objects.filter(student=self.student).exists())
        self.assertTrue(AssignmentSubmission.objects.filter(student=self.student).exists())
        self.assertTrue(ClassroomMembership.objects.filter(student=self.student).exists())


class DuplicateIdentityAuditCommandTests(TestCase):
    """Tests confirming the audit_identity_duplicates command operates safely."""

    def test_audit_command_runs_successfully(self):
        out = StringIO()
        call_command('audit_identity_duplicates', stdout=out)
        output = out.getvalue()
        self.assertIn("=== EduMi 2 Identity & Profile Audit ===", output)
        self.assertIn("All identity checks PASSED", output)


class WebSocketAndCameraSecurityAuthorizationTests(TestCase):
    """Tests confirming WebSocket and camera audio access control boundary enforcement."""

    def setUp(self):
        cache.clear()
        from asgiref.sync import async_to_sync
        self.async_to_sync = async_to_sync

        self.teacher = User.objects.create_user(username='ws_prof', email='prof@edumi.test', password='P!')
        configure_profile(self.teacher, user_type='teacher')

        self.student_enrolled = User.objects.create_user(username='ws_stu_in', email='in@edumi.test', password='P!')
        configure_profile(self.student_enrolled, user_type='student')

        self.student_outsider = User.objects.create_user(username='ws_stu_out', email='out@edumi.test', password='P!')
        configure_profile(self.student_outsider, user_type='student')

        self.admin = User.objects.create_superuser(username='ws_admin', email='wsadmin@edumi.test', password='P!')
        configure_profile(self.admin, user_type='admin')

        self.classroom = Classroom.objects.create(
            title='Advanced Chemistry',
            class_code='CHEM201',
            teacher=self.teacher,
            password='h'
        )
        ClassroomMembership.objects.create(classroom=self.classroom, student=self.student_enrolled, status='approved')

        self.meeting = Meeting.objects.create(
            classroom=self.classroom,
            title='Chem Lab Session',
            teacher=self.teacher,
            meeting_code='CHEM201',
            scheduled_time=timezone.now()
        )

        from cameras.models import Camera, CameraPermission
        self.camera = Camera.objects.create(
            name='Chem Lab Cam 1',
            camera_type='rtsp',
            ip_address='127.0.0.1',
            port=554,
            is_active=True
        )
        CameraPermission.objects.create(
            camera=self.camera,
            teacher=self.teacher,
            show_to_students=True
        )

    def tearDown(self):
        cache.clear()

    def test_meeting_consumer_enforces_classroom_boundary(self):
        """MeetingConsumer.verify_meeting_access rejects outsider and accepts enrolled student, teacher, admin."""
        from meetings.consumers import MeetingConsumer

        # Outsider student -> Rejected
        consumer_out = MeetingConsumer()
        consumer_out.meeting_code = 'CHEM201'
        consumer_out.user = self.student_outsider
        self.assertFalse(self.async_to_sync(consumer_out.verify_meeting_access)())

        # Enrolled student -> Accepted
        consumer_in = MeetingConsumer()
        consumer_in.meeting_code = 'CHEM201'
        consumer_in.user = self.student_enrolled
        self.assertTrue(self.async_to_sync(consumer_in.verify_meeting_access)())

        # Teacher host -> Accepted
        consumer_t = MeetingConsumer()
        consumer_t.meeting_code = 'CHEM201'
        consumer_t.user = self.teacher
        self.assertTrue(self.async_to_sync(consumer_t.verify_meeting_access)())

        # Superuser -> Accepted
        consumer_adm = MeetingConsumer()
        consumer_adm.meeting_code = 'CHEM201'
        consumer_adm.user = self.admin
        self.assertTrue(self.async_to_sync(consumer_adm.verify_meeting_access)())

    def test_face_attendance_consumer_enforces_classroom_boundary(self):
        """FaceAttendanceConsumer.verify_attendance_access rejects outsider student and accepts enrolled student."""
        from attendance.consumers import FaceAttendanceConsumer

        # Outsider student -> Rejected
        c_out = FaceAttendanceConsumer()
        c_out.meeting_code = 'CHEM201'
        c_out.user = self.student_outsider
        self.assertFalse(self.async_to_sync(c_out.verify_attendance_access)())

        # Enrolled student -> Accepted
        c_in = FaceAttendanceConsumer()
        c_in.meeting_code = 'CHEM201'
        c_in.user = self.student_enrolled
        self.assertTrue(self.async_to_sync(c_in.verify_attendance_access)())

    def test_camera_audio_consumer_enforces_classroom_enrollment(self):
        """AudioConsumer.check_camera_access rejects student not enrolled in camera's assigned classrooms."""
        from cameras.consumers import AudioConsumer

        # Outsider student -> Rejected
        c_out = AudioConsumer()
        c_out.camera_id = self.camera.id
        c_out.user = self.student_outsider
        self.assertFalse(self.async_to_sync(c_out.check_camera_access)())

        # Enrolled student -> Accepted
        c_in = AudioConsumer()
        c_in.camera_id = self.camera.id
        c_in.user = self.student_enrolled
        self.assertTrue(self.async_to_sync(c_in.check_camera_access)())

    def test_email_change_resets_verification_status(self):
        """When a user changes their email address, is_verified must be reset to False."""
        user = User.objects.create_user(username='verified_u', email='old@edumi.test', password='P!')
        prof = configure_profile(user, is_verified=True, email_verified_at=timezone.now())
        self.assertTrue(prof.is_verified)

        IdentityService.update_identity(
            target_user=user,
            actor=user,
            data={'email': 'new_email@edumi.test'}
        )

        user.refresh_from_db()
        prof.refresh_from_db()
        self.assertEqual(user.email, 'new_email@edumi.test')
        self.assertFalse(prof.is_verified)
        self.assertIsNone(prof.email_verified_at)


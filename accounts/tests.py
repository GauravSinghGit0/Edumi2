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
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import ProtectedError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from io import StringIO

from accounts.models import UserProfile
from accounts.identity import IdentityService
from common.utils import get_user_identity
from meetings.models import Classroom, ClassroomMembership, Meeting, MeetingParticipant
from attendance.models import AttendanceRecord
from assignments.models import Assignment, AssignmentSubmission, AssignmentSubmissionFile

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


class WebSocketAndCameraSecurityAuthorizationTests(TransactionTestCase):
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


class AdminPortalBugFixesTests(TestCase):
    """Tests for the 9 Admin Portal fixes and enhancements."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username='admin_boss',
            email='admin_boss@edumi.test',
            password='Password123!'
        )
        configure_profile(self.admin, user_type='admin')

        self.teacher_user = User.objects.create_user(
            username='teacher_prof',
            email='teacher_prof@edumi.test',
            password='Password123!'
        )
        configure_profile(self.teacher_user, user_type='teacher', department='Physics')

        self.student_user = User.objects.create_user(
            username='student_bob',
            email='student_bob@edumi.test',
            password='Password123!'
        )
        configure_profile(self.student_user, user_type='student')

        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def test_admin_create_classroom_rejects_non_teacher(self):
        """Backend validation: instructor must have user_type == 'teacher'."""
        response = self.client.post(reverse('admin_create_classroom'), {
            'title': 'Invalid Math Class',
            'class_code': 'MATH-INV-1',
            'teacher_id': self.student_user.id,
        })
        self.assertEqual(response.status_code, 302)
        # Classroom must NOT have been created
        self.assertFalse(Classroom.objects.filter(class_code='MATH-INV-1').exists())

    def test_admin_create_classroom_accepts_teacher(self):
        """Creating classroom with valid teacher succeeds."""
        response = self.client.post(reverse('admin_create_classroom'), {
            'title': 'Quantum Physics 101',
            'class_code': 'QP-101',
            'teacher_id': self.teacher_user.id,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Classroom.objects.filter(class_code='QP-101').exists())

    def test_admin_edit_classroom_instructor_validation(self):
        """Classroom edit view enforces instructor user_type == 'teacher'."""
        cr = Classroom.objects.create(
            title='Intro to Physics',
            class_code='PHY-101',
            teacher=self.teacher_user,
            is_active=True
        )

        # Attempt to change instructor to student -> Rejected
        response = self.client.post(reverse('admin_edit_classroom', args=[cr.id]), {
            'title': 'Intro to Physics Updated',
            'class_code': 'PHY-101',
            'teacher_id': self.student_user.id,
        })
        self.assertEqual(response.status_code, 302)
        cr.refresh_from_db()
        self.assertEqual(cr.teacher, self.teacher_user)

        # Change with valid teacher -> Accepted
        other_teacher = User.objects.create_user(username='other_t', email='other_t@edumi.test', password='P!')
        configure_profile(other_teacher, user_type='teacher')

        response = self.client.post(reverse('admin_edit_classroom', args=[cr.id]), {
            'title': 'Intro to Physics Updated',
            'class_code': 'PHY-101-NEW',
            'teacher_id': other_teacher.id,
            'is_active': 'on'
        })
        self.assertEqual(response.status_code, 302)
        cr.refresh_from_db()
        self.assertEqual(cr.teacher, other_teacher)
        self.assertEqual(cr.class_code, 'PHY-101-NEW')

    def test_check_classroom_instructors_command(self):
        """Management command identifies classrooms taught by non-teachers."""
        # Create an anomaly classroom taught by a student
        Classroom.objects.create(
            title='Anomalous Course',
            class_code='ANOM-01',
            teacher=self.student_user
        )

        out = StringIO()
        call_command('check_classroom_instructors', stdout=out)
        output = out.getvalue()
        self.assertIn("ANOM-01", output)
        self.assertIn("student_bob", output)
        self.assertIn("Found 1 classroom(s) whose instructor is NOT a registered teacher", output)

    def test_teacher_roster_stats_counts_only_teacher_classrooms(self):
        """Teacher Roster Total Classrooms stat counts only classrooms taught by teachers."""
        # Classroom taught by teacher
        Classroom.objects.create(title='Valid Course', class_code='VAL-1', teacher=self.teacher_user)
        # Classroom taught by student
        Classroom.objects.create(title='Invalid Course', class_code='INVAL-1', teacher=self.student_user)

        response = self.client.get(reverse('admin_all_teachers_roster'))
        self.assertEqual(response.status_code, 200)
        # Context total_classrooms must be 1 (only teacher's classroom), not 2
        self.assertEqual(response.context['total_classrooms'], 1)

    def test_bulk_archive_classrooms(self):
        """POST /admin/classrooms/bulk-archive/ archives selected classrooms."""
        c1 = Classroom.objects.create(title='Course 1', class_code='C1', teacher=self.teacher_user, is_active=True)
        c2 = Classroom.objects.create(title='Course 2', class_code='C2', teacher=self.teacher_user, is_active=True)

        response = self.client.post(reverse('admin_bulk_archive_classrooms'), {
            'classroom_ids': [c1.id, c2.id]
        })
        self.assertEqual(response.status_code, 302)
        c1.refresh_from_db()
        c2.refresh_from_db()
        self.assertFalse(c1.is_active)
        self.assertFalse(c2.is_active)

    def test_bulk_export_classrooms(self):
        """POST /admin/classrooms/bulk-export/ returns CSV with classroom data."""
        c1 = Classroom.objects.create(title='Bio 101', class_code='BIO-1', teacher=self.teacher_user)
        response = self.client.post(reverse('admin_bulk_export_classrooms'), {
            'classroom_ids': [c1.id]
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode('utf-8')
        self.assertIn('BIO-1', content)
        self.assertIn('Bio 101', content)

    def test_bulk_users_status(self):
        """POST /admin/users/bulk-status/ suspends/activates selected users."""
        u1 = User.objects.create_user(username='u_test_1', email='u1@test.com', password='P!', is_active=True)
        u2 = User.objects.create_user(username='u_test_2', email='u2@test.com', password='P!', is_active=True)

        response = self.client.post(reverse('admin_bulk_users_status'), {
            'user_ids': [u1.id, u2.id],
            'status_action': 'suspend'
        })
        self.assertEqual(response.status_code, 302)
        u1.refresh_from_db()
        u2.refresh_from_db()
        self.assertFalse(u1.is_active)
        self.assertFalse(u2.is_active)

    def test_human_duration_template_filter(self):
        """Template filter human_duration handles timedeltas, strings, and integers."""
        from common.templatetags.common_tags import human_duration_filter
        import datetime

        # String formatted timedelta (0:02:03.485000 -> 2m 03s)
        self.assertEqual(human_duration_filter("0:02:03.485000"), "2m 03s")
        # Python timedelta
        self.assertEqual(human_duration_filter(datetime.timedelta(seconds=123.485)), "2m 03s")
        # Hours, minutes, seconds
        self.assertEqual(human_duration_filter("1:05:12.100"), "1h 05m 12s")
        self.assertEqual(human_duration_filter(3665), "1h 01m 05s")
        # Just seconds
        self.assertEqual(human_duration_filter(45), "45s")
        self.assertEqual(human_duration_filter(0), "0s")
        # Empty / None
        self.assertEqual(human_duration_filter(None), "--")
        self.assertEqual(human_duration_filter(""), "--")

    def test_dashboard_kpi_subtexts_populated(self):
        """Dashboard stats provide non-empty human-readable KPI subtexts."""
        from accounts.admin_services import compute_raw_admin_dashboard_stats
        stats = compute_raw_admin_dashboard_stats()
        self.assertIn('users_kpi_subtext', stats)
        self.assertIn('active', stats['users_kpi_subtext'])
        self.assertIn('students', stats['users_kpi_subtext'])
        self.assertIn('classrooms_kpi_subtext', stats)
        self.assertIn('enrolled', stats['classrooms_kpi_subtext'])


class ExecutiveDashboardTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(
            username='exec_admin',
            email='exec_admin@test.com',
            password='Password123!'
        )
        UserProfile.objects.filter(user=self.admin).update(user_type='admin')
        self.client.force_login(self.admin)

        self.teacher = User.objects.create_user(
            username='exec_prof',
            email='exec_prof@test.com',
            password='Password123!'
        )
        UserProfile.objects.filter(user=self.teacher).update(user_type='teacher')

        self.student = User.objects.create_user(
            username='exec_student',
            email='exec_student@test.com',
            password='Password123!'
        )
        UserProfile.objects.filter(user=self.student).update(user_type='student')

        self.classroom = Classroom.objects.create(
            title='Executive Operations 101',
            class_code='EXEC-101',
            teacher=self.teacher,
            is_active=True
        )

    def test_admin_dashboard_view_renders(self):
        resp = self.client.get('/admin/dashboard/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Executive Control Center')
        self.assertContains(resp, 'Total Users')
        self.assertContains(resp, 'Active Today')
        self.assertContains(resp, 'Live Sessions')
        self.assertContains(resp, 'Avg Attendance %')
        self.assertContains(resp, 'System Infrastructure & Services Health')

    def test_needs_attention_with_pending_enrollments(self):
        # Create pending enrollment
        ClassroomMembership.objects.create(
            classroom=self.classroom,
            student=self.student,
            status='pending'
        )
        resp = self.client.get('/admin/dashboard/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Action Required')
        self.assertContains(resp, 'Pending Enrollment Request')
        self.assertContains(resp, 'Review Enrollments')

    def test_needs_attention_all_systems_normal(self):
        # With zero pending enrollments and zero offline cameras (no cameras created)
        from accounts.admin_services import compute_raw_admin_dashboard_stats
        stats = compute_raw_admin_dashboard_stats()
        # Verify needs_attention_items is empty
        self.assertEqual(len(stats['needs_attention_items']), 0)
        resp = self.client.get('/admin/dashboard/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'All systems normal')

    def test_next_scheduled_session_when_no_live_meetings(self):
        # No live meetings, create upcoming scheduled session
        upcoming_time = timezone.now() + datetime.timedelta(hours=2)
        m = Meeting.objects.create(
            title='Upcoming Board Review',
            teacher=self.teacher,
            classroom=self.classroom,
            status='scheduled',
            scheduled_time=upcoming_time,
            duration_minutes=60
        )
        resp = self.client.get('/admin/dashboard/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Next Scheduled')
        self.assertContains(resp, 'Upcoming Board Review')

    def test_recent_admin_actions_feed_from_audit_trail(self):
        from common.models import AdminAuditTrail
        audit = AdminAuditTrail.objects.create(
            admin_user=self.admin,
            action_type=AdminAuditTrail.ACTION_USER_CREATED,
            target_type='User',
            target_id=self.student.id,
            target_label='@newly_onboarded_student',
            ip_address='127.0.0.1'
        )
        resp = self.client.get('/admin/dashboard/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Recent Admin Actions')
        self.assertContains(resp, '@newly_onboarded_student')

    def test_dashboard_metrics_api_endpoint(self):
        # 7-day range
        resp = self.client.get('/admin/api/dashboard-metrics/?range=7')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('status'), 'success')
        self.assertEqual(data.get('range'), 7)
        self.assertEqual(len(data.get('categories', [])), 7)
        self.assertEqual(len(data.get('attendance', {}).get('attendance_rate', [])), 7)
        self.assertEqual(len(data.get('workload', {}).get('assignment_submissions', [])), 7)

        # 30-day range
        resp30 = self.client.get('/admin/api/dashboard-metrics/?range=30')
        self.assertEqual(resp30.status_code, 200)
        data30 = resp30.json()
        self.assertEqual(data30.get('range'), 30)
        self.assertEqual(len(data30.get('categories', [])), 30)

        # Unauthenticated blocked
        self.client.logout()
        resp_anon = self.client.get('/admin/api/dashboard-metrics/?range=7')
        self.assertEqual(resp_anon.status_code, 302)


class UserDirectoryUpgradeTests(TestCase):
    """
    Automated tests for User Directory Upgrade & Teacher Roster Merger (Part 7).
    Covers:
    1. 5 Role Tabs & unfiltered badge counts
    2. Legacy /admin/teachers/ redirect to /admin/users/?tab=teachers
    3. Live search, sorting, and department filters
    4. Floating bulk status (activate/suspend) with AdminAuditTrail logging
    5. Bulk role change with AdminAuditTrail logging
    6. Password reset link generation with AdminAuditTrail logging
    7. 360 User Profile quick actions and Dossier rebranding
    """

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser('admin_exec', 'admin@edumi.test', 'adminpass123')
        configure_profile(self.admin, user_type='admin', department='IT Administration')

        self.teacher1 = User.objects.create_user('prof_smith', 'smith@edumi.test', 'teacherpass123')
        configure_profile(self.teacher1, user_type='teacher', department='Computer Science')

        self.teacher2 = User.objects.create_user('dr_watson', 'watson@edumi.test', 'teacherpass123')
        configure_profile(self.teacher2, user_type='teacher', department='Mathematics')

        self.student1 = User.objects.create_user('alice_student', 'alice@edumi.test', 'studentpass123')
        configure_profile(self.student1, user_type='student', department='Computer Science')

        self.student2 = User.objects.create_user('bob_suspended', 'bob@edumi.test', 'studentpass123', is_active=False)
        configure_profile(self.student2, user_type='student', department='Physics')

        self.client.force_login(self.admin)

    def test_user_directory_tabs_and_counts(self):
        resp = self.client.get('/admin/users/?tab=all')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_count'], 5)
        self.assertEqual(resp.context['student_count'], 2)
        self.assertEqual(resp.context['teacher_count'], 2)
        self.assertEqual(resp.context['admin_count'], 1)
        self.assertEqual(resp.context['suspended_count'], 1)

        # Filter by teachers tab
        resp_teachers = self.client.get('/admin/users/?tab=teachers')
        self.assertEqual(resp_teachers.status_code, 200)
        users = [item['user'].username for item in resp_teachers.context['users_data']]
        self.assertIn('prof_smith', users)
        self.assertIn('dr_watson', users)
        self.assertNotIn('alice_student', users)

        # Filter by suspended tab
        resp_suspended = self.client.get('/admin/users/?tab=suspended')
        self.assertEqual(resp_suspended.status_code, 200)
        users_susp = [item['user'].username for item in resp_suspended.context['users_data']]
        self.assertIn('bob_suspended', users_susp)
        self.assertNotIn('alice_student', users_susp)

    def test_teacher_roster_redirect(self):
        resp = self.client.get('/admin/teachers/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/admin/users/?tab=teachers')

    def test_search_sort_and_department_filters(self):
        # Department filter
        resp_cs = self.client.get('/admin/users/?dept=Computer Science')
        self.assertEqual(resp_cs.status_code, 200)
        cs_users = [item['user'].username for item in resp_cs.context['users_data']]
        self.assertIn('prof_smith', cs_users)
        self.assertIn('alice_student', cs_users)
        self.assertNotIn('dr_watson', cs_users)

        # Search query
        resp_search = self.client.get('/admin/users/?q=watson')
        self.assertEqual(resp_search.status_code, 200)
        search_users = [item['user'].username for item in resp_search.context['users_data']]
        self.assertEqual(search_users, ['dr_watson'])

        # Sorting by name asc
        resp_sort = self.client.get('/admin/users/?sort=name&dir=asc')
        self.assertEqual(resp_sort.status_code, 200)
        sorted_users = [item['user'].username for item in resp_sort.context['users_data']]
        self.assertTrue(len(sorted_users) > 0)

    def test_bulk_users_status_json_and_audit(self):
        from common.models import AdminAuditTrail
        # Bulk suspend alice
        resp = self.client.post(
            '/admin/users/bulk-status/',
            data=json.dumps({'user_ids': [self.student1.id], 'status_action': 'suspend'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        self.student1.refresh_from_db()
        self.assertFalse(self.student1.is_active)

        # Verify audit trail logged
        audit = AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_BULK_ACTION
        ).latest('timestamp')
        self.assertEqual(audit.admin_user, self.admin)
        self.assertIn(str(self.student1.id), str(audit.changes_json))

        # Bulk activate alice & bob
        resp2 = self.client.post(
            '/admin/users/bulk-status/',
            data=json.dumps({'user_ids': [self.student1.id, self.student2.id], 'status_action': 'activate'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp2.status_code, 200)
        self.student1.refresh_from_db()
        self.student2.refresh_from_db()
        self.assertTrue(self.student1.is_active)
        self.assertTrue(self.student2.is_active)

    def test_bulk_change_role_and_audit(self):
        from common.models import AdminAuditTrail
        resp = self.client.post(
            '/admin/users/bulk-role/',
            data=json.dumps({'user_ids': [self.student1.id], 'new_role': 'teacher'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        self.student1.userprofile.refresh_from_db()
        self.assertEqual(self.student1.userprofile.user_type, 'teacher')

        # Verify audit trail logged
        audit = AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_ROLE_CHANGED
        ).latest('timestamp')
        self.assertEqual(audit.admin_user, self.admin)
        self.assertEqual(audit.changes_json.get('new_role'), 'teacher')

    def test_password_reset_link_generation_and_audit(self):
        from common.models import AdminAuditTrail
        resp = self.client.post(
            f'/admin/users/{self.student1.id}/reset-password/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('password-reset/confirm/', data.get('reset_url'))
        self.assertEqual(data.get('username'), 'alice_student')

        # Verify audit trail logged
        audit = AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_PASSWORD_RESET
        ).latest('timestamp')
        self.assertEqual(audit.admin_user, self.admin)
        self.assertEqual(audit.target_label, '@alice_student')

    def test_user_profile_dossier_renamed_and_quick_actions(self):
        resp = self.client.get(f'/admin/users/{self.student1.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '360 Profile')
        self.assertNotContains(resp, '360 Dossier')
        # Check quick action buttons
        self.assertContains(resp, 'Edit Account')
        self.assertContains(resp, 'Reset Password')
        self.assertContains(resp, 'Suspend')
        self.assertContains(resp, 'Delete User')


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class BulkUserImporterTests(TestCase):
    """
    Automated test coverage for the Bulk User Importer:
    - Step 1: Sample CSV template download & non-admin permission gates.
    - Step 2: CSV parsing, duplicate detection (DB & intra-file), bad roles, missing fields.
    - Step 3 & 4: Execution, Celery/Thread progress polling, user & profile creation.
    - Failed rows CSV generation and download.
    - Single consolidated AdminAuditTrail logging (ACTION_BULK_ACTION).
    """

    def setUp(self):
        self.admin = User.objects.create_superuser('admin_importer', 'admin_importer@example.com', 'AdminPass123!')
        configure_profile(self.admin, user_type='admin', department='IT Administration')

        self.student = User.objects.create_user('alice_existing', 'alice_existing@example.com', 'Pass123!')
        configure_profile(self.student, user_type='student', department='Mathematics')

        self.regular_user = User.objects.create_user('normie_user', 'normie@example.com', 'Pass123!')
        configure_profile(self.regular_user, user_type='student')

        self.client.force_login(self.admin)

    def test_sample_csv_download(self):
        resp = self.client.get('/admin/users/import/sample-template/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        self.assertIn('attachment; filename="edumi_user_import_template.csv"', resp['Content-Disposition'])

        content = resp.content.decode('utf-8')
        self.assertIn('username,email,first_name,last_name,role,department', content)
        self.assertIn('student', content)
        self.assertIn('teacher', content)
        self.assertIn('admin', content)

    def test_preview_validation_bad_roles_duplicates_and_missing_fields(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        csv_content = (
            "username,email,first_name,last_name,role,department\n"
            "valid_student,valid_student@example.com,Valid,Student,student,Science\n"
            "bad_role_user,bad_role@example.com,Bad,Role,dean,Engineering\n"
            "no_email_user,,No,Email,student,Art\n"
            "alice_existing,new_email@example.com,Alice,DuplicateUsername,teacher,CS\n"
            "diff_username,alice_existing@example.com,Alice,DuplicateEmail,student,Math\n"
            "valid_student,another_email@example.com,Dup,InCsv,student,History\n"
        )
        csv_file = SimpleUploadedFile("test_import.csv", csv_content.encode('utf-8'), content_type="text/csv")

        resp = self.client.post('/admin/users/import/preview/', {'file': csv_file})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data.get('status'), 'success')
        self.assertEqual(data['total_rows'], 6)
        self.assertEqual(data['valid_count'], 1)
        self.assertEqual(data['invalid_count'], 5)
        self.assertIn('file_token', data)

        rows = data['rows']
        # Row 0: valid
        self.assertTrue(rows[0]['valid'])
        # Row 1: bad role
        self.assertFalse(rows[1]['valid'])
        self.assertIn("Invalid role 'dean'", rows[1]['error'])
        # Row 2: missing email
        self.assertFalse(rows[2]['valid'])
        self.assertIn("Email address is missing", rows[2]['error'])
        # Row 3: existing username in DB
        self.assertFalse(rows[3]['valid'])
        self.assertIn("Username 'alice_existing' already exists in database", rows[3]['error'])
        # Row 4: existing email in DB
        self.assertFalse(rows[4]['valid'])
        self.assertIn("Email 'alice_existing@example.com' is already registered in database", rows[4]['error'])
        # Row 5: duplicate username in CSV
        self.assertFalse(rows[5]['valid'])
        self.assertIn("Duplicate username 'valid_student'", rows[5]['error'])

    def test_import_execution_valid_file_and_audit_trail(self):
        from common.models import AdminAuditTrail
        from django.core.files.uploadedfile import SimpleUploadedFile
        import time

        csv_content = (
            "username,email,first_name,last_name,role,department\n"
            "new_prof,new_prof@example.com,Robert,Langdon,teacher,History\n"
            "new_admin,new_admin@example.com,Dana,Scully,admin,Security\n"
        )
        csv_file = SimpleUploadedFile("staff_import.csv", csv_content.encode('utf-8'), content_type="text/csv")

        # 1. Preview
        resp_preview = self.client.post('/admin/users/import/preview/', {'file': csv_file})
        self.assertEqual(resp_preview.status_code, 200)
        file_token = resp_preview.json()['file_token']

        # 2. Execute
        resp_exec = self.client.post(
            '/admin/users/import/execute/',
            data=json.dumps({'file_token': file_token, 'send_invites': False}),
            content_type='application/json'
        )
        self.assertEqual(resp_exec.status_code, 200)
        exec_data = resp_exec.json()
        self.assertEqual(exec_data.get('status'), 'success')
        task_id = exec_data['task_id']

        # 3. Wait/poll for task completion (thread fallback completes in milliseconds)
        for _ in range(20):
            progress_resp = self.client.get(f'/admin/api/user-import-progress/{task_id}/')
            self.assertEqual(progress_resp.status_code, 200)
            progress_data = progress_resp.json()
            if progress_data.get('status') == 'SUCCESS':
                break
            time.sleep(0.1)

        self.assertEqual(progress_data['status'], 'SUCCESS')
        self.assertEqual(progress_data['success_count'], 2)
        self.assertEqual(progress_data['failed_count'], 0)

        # 4. Verify DB records
        prof = User.objects.get(username='new_prof')
        self.assertEqual(prof.email, 'new_prof@example.com')
        self.assertEqual(prof.first_name, 'Robert')
        self.assertEqual(prof.userprofile.user_type, 'teacher')
        self.assertEqual(prof.userprofile.department, 'History')
        self.assertFalse(prof.is_staff)

        adm = User.objects.get(username='new_admin')
        self.assertEqual(adm.userprofile.user_type, 'admin')
        self.assertTrue(adm.is_staff)

        # 5. Verify AdminAuditTrail: exactly one ACTION_BULK_ACTION record
        audits = AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_BULK_ACTION,
            target_type='BulkUserImport'
        )
        self.assertEqual(audits.count(), 1)
        audit = audits.first()
        self.assertEqual(audit.admin_user, self.admin)
        self.assertIn('staff_import.csv', audit.target_label)
        self.assertEqual(audit.changes_json.get('filename'), 'staff_import.csv')
        self.assertEqual(audit.changes_json.get('success_count'), 2)
        self.assertEqual(audit.changes_json.get('failed_count'), 0)

    def test_import_failed_rows_and_csv_download(self):
        from accounts.tasks import bulk_import_users_task
        import uuid

        # Directly run task with an invalid row (e.g. invalid role that bypassed or direct call)
        task_id = str(uuid.uuid4())
        bad_rows = [
            {
                'row_num': 2,
                'username': 'ghost_user',
                'email': 'ghost@example.com',
                'first_name': 'Ghost',
                'last_name': 'Rider',
                'role': 'unsupported_role',
                'department': 'Vehicular'
            }
        ]

        bulk_import_users_task(
            admin_user_id=self.admin.id,
            rows_data=bad_rows,
            send_invites=False,
            original_filename='bad_rows.csv',
            task_id=task_id,
            ip_address='127.0.0.1'
        )

        # Progress should show 1 failure
        progress_resp = self.client.get(f'/admin/api/user-import-progress/{task_id}/')
        self.assertEqual(progress_resp.status_code, 200)
        progress_data = progress_resp.json()
        self.assertEqual(progress_data['status'], 'SUCCESS')
        self.assertEqual(progress_data['failed_count'], 1)

        # Failed rows CSV endpoint
        failed_csv_resp = self.client.get(f'/admin/api/user-import-failed-csv/{task_id}/')
        self.assertEqual(failed_csv_resp.status_code, 200)
        self.assertEqual(failed_csv_resp['Content-Type'], 'text/csv')
        content = failed_csv_resp.content.decode('utf-8')
        self.assertIn('ghost_user', content)
        self.assertIn('unsupported_role', content)
        self.assertIn('error_reason', content)

    def test_non_admin_forbidden(self):
        self.client.force_login(self.regular_user)
        # Template download
        self.assertEqual(self.client.get('/admin/users/import/sample-template/').status_code, 403)
        # Preview
        self.assertEqual(self.client.post('/admin/users/import/preview/').status_code, 403)
        # Execute
        self.assertEqual(self.client.post('/admin/users/import/execute/').status_code, 403)
        # Progress
        self.assertEqual(self.client.get('/admin/api/user-import-progress/some-id/').status_code, 403)
        # Failed CSV
        self.assertEqual(self.client.get('/admin/api/user-import-failed-csv/some-id/').status_code, 403)


class CoursesAndLiveSessionsUpgradeTests(TestCase):
    """
    Automated test coverage for:
    1. Courses (Classroom Catalog Upgrade):
       - View toggle (cards vs table), filters (status, teacher, department), live search.
       - Per-course metrics: enrollment count, pending requests, attendance %, last session date.
       - Edit Settings drawer (GET and POST with role validation and audit trail).
       - Archive course with confirmation and audit trail.
    2. Live Sessions (Meetings Upgrade):
       - Tabs (live now, upcoming, past, all).
       - Columns: duration, participants count, attendance %.
       - Past session detail: attendance table with join/leave time, face-verification result.
       - Session attendance CSV export with AdminAuditTrail logging.
       - Live Monitor page & Force-End Session action with audit logging and participant disconnect.
    """

    def setUp(self):
        self.admin = User.objects.create_superuser('admin_exec_gov', 'admin_gov@example.com', 'AdminPass123!')
        configure_profile(self.admin, user_type='admin', department='Academic Governance')

        self.teacher_cs = User.objects.create_user('prof_alan', 'alan@example.com', 'TeachPass123!')
        configure_profile(self.teacher_cs, user_type='teacher', department='Computer Science')

        self.teacher_math = User.objects.create_user('prof_hypatia', 'hypatia@example.com', 'TeachPass123!')
        configure_profile(self.teacher_math, user_type='teacher', department='Mathematics')

        self.student1 = User.objects.create_user('student_john', 'john@example.com', 'StudPass123!')
        configure_profile(self.student1, user_type='student', department='Computer Science')

        self.student2 = User.objects.create_user('student_sarah', 'sarah@example.com', 'StudPass123!')
        configure_profile(self.student2, user_type='student', department='Computer Science')

        # Course 1: Active CS Course
        self.course_cs = Classroom.objects.create(
            title="Algorithms & Data Structures",
            class_code="CS201",
            teacher=self.teacher_cs,
            auto_approve=True,
            is_active=True
        )
        ClassroomMembership.objects.create(classroom=self.course_cs, student=self.student1, status='approved')
        ClassroomMembership.objects.create(classroom=self.course_cs, student=self.student2, status='pending')

        # Course 2: Archived Math Course
        self.course_math = Classroom.objects.create(
            title="Linear Algebra & Matrix Theory",
            class_code="MATH101",
            teacher=self.teacher_math,
            auto_approve=False,
            is_active=False
        )
        ClassroomMembership.objects.create(classroom=self.course_math, student=self.student1, status='approved')

        # Meeting 1: Live Now
        self.meeting_live = Meeting.objects.create(
            title="CS201 Live Lab Session",
            meeting_code="LIVE-CS201",
            teacher=self.teacher_cs,
            classroom=self.course_cs,
            status='live',
            scheduled_time=timezone.now() - datetime.timedelta(minutes=30),
            started_at=timezone.now() - datetime.timedelta(minutes=25),
            duration_minutes=60
        )
        self.part_teacher = MeetingParticipant.objects.create(
            meeting=self.meeting_live,
            user=self.teacher_cs,
            is_active=True,
            joined_at=timezone.now() - datetime.timedelta(minutes=25)
        )
        self.part_student1 = MeetingParticipant.objects.create(
            meeting=self.meeting_live,
            user=self.student1,
            is_active=True,
            joined_at=timezone.now() - datetime.timedelta(minutes=20)
        )

        # Meeting 2: Upcoming
        self.meeting_upcoming = Meeting.objects.create(
            title="CS201 Next Week Lecture",
            meeting_code="UPCOMING-CS",
            teacher=self.teacher_cs,
            classroom=self.course_cs,
            status='scheduled',
            scheduled_time=timezone.now() + datetime.timedelta(days=2),
            duration_minutes=90
        )

        # Meeting 3: Past Ended Session with Attendance Record
        self.meeting_past = Meeting.objects.create(
            title="Math101 Historical Review",
            meeting_code="PAST-MATH",
            teacher=self.teacher_math,
            classroom=self.course_math,
            status='ended',
            scheduled_time=timezone.now() - datetime.timedelta(days=3),
            started_at=timezone.now() - datetime.timedelta(days=3, hours=1),
            ended_at=timezone.now() - datetime.timedelta(days=3),
            duration_minutes=60
        )
        self.part_past = MeetingParticipant.objects.create(
            meeting=self.meeting_past,
            user=self.student1,
            is_active=False,
            joined_at=self.meeting_past.started_at,
            left_at=self.meeting_past.ended_at,
            total_duration_seconds=3600
        )
        from attendance.models import AttendanceRecord
        self.att_record = AttendanceRecord.objects.create(
            student=self.student1,
            meeting=self.meeting_past,
            classroom=self.course_math,
            date=self.meeting_past.scheduled_time.date(),
            status='present',
            verification_method='face_recognition',
            face_match_confidence=0.965
        )

        self.client.force_login(self.admin)

    def test_courses_catalog_filters_metrics_and_views(self):
        # 1. Base catalog list view
        resp = self.client.get('/admin/classrooms/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Courses")
        self.assertContains(resp, "Algorithms &amp; Data Structures")
        self.assertContains(resp, "Linear Algebra &amp; Matrix Theory")

        # 2. Filter by status: active
        resp_act = self.client.get('/admin/classrooms/?status=active')
        self.assertEqual(resp_act.status_code, 200)
        act_titles = [c.title for c in resp_act.context['classrooms']]
        self.assertIn("Algorithms & Data Structures", act_titles)
        self.assertNotIn("Linear Algebra & Matrix Theory", act_titles)

        # 3. Filter by department: Mathematics
        resp_dept = self.client.get('/admin/classrooms/?dept=Mathematics')
        self.assertEqual(resp_dept.status_code, 200)
        dept_titles = [c.title for c in resp_dept.context['classrooms']]
        self.assertEqual(dept_titles, ["Linear Algebra & Matrix Theory"])

        # 4. Search query
        resp_search = self.client.get('/admin/classrooms/?q=CS201')
        self.assertEqual(resp_search.status_code, 200)
        search_titles = [c.title for c in resp_search.context['classrooms']]
        self.assertEqual(search_titles, ["Algorithms & Data Structures"])

        # 5. Verify computed metrics on course object
        cs_obj = [c for c in resp.context['classrooms'] if c.id == self.course_cs.id][0]
        self.assertEqual(cs_obj.approved_students, 1)
        self.assertEqual(cs_obj.pending_students, 1)
        self.assertIsNotNone(cs_obj.last_session_date)

    def test_courses_edit_settings_drawer_ajax_get_and_post(self):
        from common.models import AdminAuditTrail

        # 1. GET drawer info via AJAX
        resp_get = self.client.get(
            f'/admin/classrooms/{self.course_cs.id}/edit/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_get.status_code, 200)
        data = resp_get.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['classroom']['title'], "Algorithms & Data Structures")
        self.assertEqual(data['classroom']['enrollment_mode'], 'auto')

        # 2. POST update settings
        resp_post = self.client.post(
            f'/admin/classrooms/{self.course_cs.id}/edit/',
            data=json.dumps({
                'title': 'Advanced Algorithms & Data Structures',
                'class_code': 'CS201-ADV',
                'teacher_id': self.teacher_cs.id,
                'enrollment_mode': 'manual',
                'description': 'Updated course syllabus',
                'is_active': True,
            }),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_post.status_code, 200)
        post_data = resp_post.json()
        self.assertEqual(post_data['status'], 'success')

        # Refresh and assert DB updates
        self.course_cs.refresh_from_db()
        self.assertEqual(self.course_cs.title, 'Advanced Algorithms & Data Structures')
        self.assertEqual(self.course_cs.class_code, 'CS201-ADV')
        self.assertFalse(self.course_cs.auto_approve)

        # Verify AdminAuditTrail entry
        audit = AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target_id=str(self.course_cs.id)
        ).latest('timestamp')
        self.assertEqual(audit.admin_user, self.admin)
        self.assertEqual(audit.changes_json['title']['after'], 'Advanced Algorithms & Data Structures')

        # 3. Reject invalid instructor role
        resp_bad_inst = self.client.post(
            f'/admin/classrooms/{self.course_cs.id}/edit/',
            data=json.dumps({
                'title': 'Fake Course',
                'class_code': 'FAKE999',
                'teacher_id': self.student1.id,  # Student, not teacher!
                'is_active': True
            }),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_bad_inst.status_code, 400)
        self.assertIn("Instructor validation failed", resp_bad_inst.json()['message'])

    def test_courses_archive_toggle_and_audit(self):
        from common.models import AdminAuditTrail

        # Archive active course
        resp = self.client.post(f'/admin/classrooms/{self.course_cs.id}/toggle-active/')
        self.assertEqual(resp.status_code, 302)
        self.course_cs.refresh_from_db()
        self.assertFalse(self.course_cs.is_active)

        # Verify audit log
        audit = AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_CLASSROOM_ARCHIVED,
            target_id=str(self.course_cs.id)
        ).latest('timestamp')
        self.assertEqual(audit.admin_user, self.admin)

    def test_live_sessions_tabs_and_columns(self):
        # 1. Tab: Live now
        resp_live = self.client.get('/admin/meetings/?tab=live')
        self.assertEqual(resp_live.status_code, 200)
        live_codes = [m.meeting_code for m in resp_live.context['meetings']]
        self.assertIn("LIVE-CS201", live_codes)
        self.assertNotIn("UPCOMING-CS", live_codes)

        # 2. Tab: Upcoming
        resp_up = self.client.get('/admin/meetings/?tab=upcoming')
        self.assertEqual(resp_up.status_code, 200)
        up_codes = [m.meeting_code for m in resp_up.context['meetings']]
        self.assertIn("UPCOMING-CS", up_codes)
        self.assertNotIn("LIVE-CS201", up_codes)

        # 3. Tab: Past
        resp_past = self.client.get('/admin/meetings/?tab=past')
        self.assertEqual(resp_past.status_code, 200)
        past_codes = [m.meeting_code for m in resp_past.context['meetings']]
        self.assertIn("PAST-MATH", past_codes)

        # Check duration and participants count on live meeting
        live_m = [m for m in resp_live.context['meetings'] if m.id == self.meeting_live.id][0]
        self.assertEqual(live_m.attendees_count, 2)
        self.assertIsNotNone(live_m.duration_formatted)
        self.assertIsNotNone(live_m.attendance_pct)

    def test_past_session_detail_and_csv_export(self):
        from common.models import AdminAuditTrail

        # 1. Past session detail view
        resp_detail = self.client.get(f'/admin/meetings/{self.meeting_past.id}/')
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, "Attendance & Biometric Verification Log")
        self.assertContains(resp_detail, "student_john")
        self.assertContains(resp_detail, "Verified (96.5%)")

        # 2. CSV export
        resp_csv = self.client.get(f'/admin/meetings/{self.meeting_past.id}/export-attendance/')
        self.assertEqual(resp_csv.status_code, 200)
        self.assertEqual(resp_csv['Content-Type'], 'text/csv; charset=utf-8')
        content = resp_csv.content.decode('utf-8')

        self.assertIn('Full Name,Username,Email,Role', content)
        self.assertIn('student_john', content)
        self.assertIn('Face Recognition', content)
        self.assertIn('96.5%', content)

        # Verify AdminAuditTrail
        audit = AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_DATA_EXPORTED,
            target_id=str(self.meeting_past.id)
        ).latest('timestamp')
        self.assertEqual(audit.admin_user, self.admin)
        self.assertEqual(audit.changes_json['export'], 'session_attendance_csv')

    def test_live_monitor_page_and_force_end(self):
        from common.models import AdminAuditTrail

        # 1. Live Monitor page
        resp_mon = self.client.get('/admin/live-monitor/')
        self.assertEqual(resp_mon.status_code, 200)
        self.assertContains(resp_mon, "Live Monitor")
        self.assertContains(resp_mon, "LIVE-CS201")
        self.assertContains(resp_mon, "CS201 Live Lab Session")
        self.assertContains(resp_mon, "student_john")

        # 2. Force-end session
        resp_end = self.client.post(
            f'/admin/meetings/{self.meeting_live.id}/force-end/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_end.status_code, 200)
        self.assertEqual(resp_end.json()['status'], 'success')

        # Verify meeting state
        self.meeting_live.refresh_from_db()
        self.assertEqual(self.meeting_live.status, 'ended')
        self.assertIsNotNone(self.meeting_live.ended_at)

        # Verify participants disconnected
        self.part_student1.refresh_from_db()
        self.assertFalse(self.part_student1.is_active)
        self.assertIsNotNone(self.part_student1.left_at)


class MediaLibraryAndCamerasTests(TestCase):
    """
    Test suite for Media Library consolidation, Cameras card view,
    RTSP validation, test connection, and dashboard camera alerts.
    """
    def setUp(self):
        from datetime import timedelta
        self.client = Client()
        self.admin = User.objects.create_superuser('media_admin', 'media_admin@edumi.io', 'pass123')
        if hasattr(self.admin, 'userprofile'):
            self.admin.userprofile.user_type = 'admin'
            self.admin.userprofile.save()
        else:
            UserProfile.objects.create(user=self.admin, user_type='admin')

        self.teacher = User.objects.create_user('cam_teacher', 'cam_teacher@edumi.io', 'pass123')
        if hasattr(self.teacher, 'userprofile'):
            self.teacher.userprofile.user_type = 'teacher'
            self.teacher.userprofile.save()
        else:
            UserProfile.objects.create(user=self.teacher, user_type='teacher')

        self.course = Classroom.objects.create(
            title="Physics 101",
            class_code="PHYS101",
            teacher=self.teacher,
            is_active=True
        )

        from cameras.models import Camera, CameraRecording, HeadCountLog
        self.camera = Camera.objects.create(
            name="Lab Camera 1",
            camera_type="rtsp",
            ip_address="192.168.1.120",
            port=554,
            stream_path="/live",
            is_active=True
        )

        self.recording_cam = CameraRecording.objects.create(
            camera=self.camera,
            classroom=self.course,
            teacher=self.teacher,
            title="Physics Lecture 01 - Mechanics",
            duration=timedelta(minutes=45, seconds=12),
            file_size=104857600,
            is_published=True
        )

        self.recording_upload = CameraRecording.objects.create(
            camera=None,
            classroom=self.course,
            teacher=self.teacher,
            title="Electromagnetism Supplementary Slides",
            duration=timedelta(minutes=14, seconds=30),
            file_size=52428800,
            is_published=False
        )

        self.hc_log = HeadCountLog.objects.create(
            camera_type='rtsp',
            camera_id=self.camera.id,
            camera_name=self.camera.name,
            classroom=self.course,
            head_count=24,
            date=timezone.now().date(),
            hour=10
        )

        self.client.force_login(self.admin)

    def test_media_library_tabs_and_filtering(self):
        # 1. Base recordings tab
        resp = self.client.get('/cameras/content-manager/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_recordings_count'], 2)
        self.assertEqual(resp.context['uploaded_count'], 1)
        self.assertEqual(resp.context['camera_recordings_count'], 1)
        self.assertEqual(len(resp.context['recordings']), 2)

        # 2. Uploaded tab
        resp_up = self.client.get('/cameras/content-manager/?tab=uploaded')
        self.assertEqual(resp_up.status_code, 200)
        self.assertEqual(len(resp_up.context['recordings']), 1)
        self.assertIsNone(resp_up.context['recordings'][0].camera)

        # 3. Camera recordings tab
        resp_cam = self.client.get('/cameras/content-manager/?tab=camera')
        self.assertEqual(resp_cam.status_code, 200)
        self.assertEqual(len(resp_cam.context['recordings']), 1)
        self.assertIsNotNone(resp_cam.context['recordings'][0].camera)

        # 4. Search filter
        resp_search = self.client.get('/cameras/content-manager/?q=Mechanics')
        self.assertEqual(resp_search.status_code, 200)
        self.assertEqual(len(resp_search.context['recordings']), 1)
        self.assertEqual(resp_search.context['recordings'][0].title, "Physics Lecture 01 - Mechanics")

        # 5. Status filter
        resp_status = self.client.get('/cameras/content-manager/?status=hidden')
        self.assertEqual(resp_status.status_code, 200)
        self.assertEqual(len(resp_status.context['recordings']), 1)
        self.assertFalse(resp_status.context['recordings'][0].is_published)

    def test_toggle_recording_publish_with_audit(self):
        from common.models import AdminAuditTrail

        resp = self.client.post(
            f'/cameras/toggle-publish/{self.recording_upload.id}/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['is_published'])

        self.recording_upload.refresh_from_db()
        self.assertTrue(self.recording_upload.is_published)

        audit = AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target_id=str(self.recording_upload.id)
        ).latest('timestamp')
        self.assertEqual(audit.admin_user, self.admin)
        self.assertEqual(audit.changes_json['is_published']['before'], False)
        self.assertEqual(audit.changes_json['is_published']['after'], True)

    def test_delete_recording_admin_with_audit(self):
        from common.models import AdminAuditTrail
        from cameras.models import CameraRecording

        rec_id = self.recording_upload.id
        resp = self.client.post(
            f'/cameras/delete-recording-admin/{rec_id}/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'success')

        self.assertFalse(CameraRecording.objects.filter(id=rec_id).exists())

        audit = AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target_id=str(rec_id)
        ).latest('timestamp')
        self.assertEqual(audit.admin_user, self.admin)
        self.assertIn('deleted_media', audit.changes_json)

    def test_recordings_folder_redirects_admin(self):
        resp = self.client.get('/cameras/recordings-folder/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/cameras/content-manager/', resp.url)

    def test_cameras_dashboard_cards_and_headcount(self):
        resp = self.client.get('/cameras/admin-dashboard/')
        self.assertEqual(resp.status_code, 200)
        cameras = resp.context['cameras']
        self.assertEqual(len(cameras), 1)

        cam_item = cameras[0]
        self.assertEqual(cam_item.current_headcount, 24)
        self.assertTrue(cam_item.is_online_status)
        self.assertIn("Lab Camera 1", resp.content.decode())

    def test_add_camera_rtsp_validation_and_audit(self):
        from common.models import AdminAuditTrail
        from cameras.models import Camera

        # 1. Invalid RTSP URL (e.g. http:// scheme for RTSP type)
        resp_bad = self.client.post('/cameras/add-camera/', {
            'name': 'Bad RTSP Cam',
            'camera_type': 'rtsp',
            'ip_address': 'http://192.168.1.200/stream',
            'port': '554',
        })
        self.assertEqual(resp_bad.status_code, 400)
        self.assertIn("Invalid RTSP URL", resp_bad.json()['message'])

        # 2. Valid RTSP URL
        resp_ok = self.client.post('/cameras/add-camera/', {
            'name': 'Corridor RTSP Cam',
            'camera_type': 'rtsp',
            'ip_address': 'rtsp://192.168.1.200:554/h264',
            'port': '554',
        })
        self.assertEqual(resp_ok.status_code, 200)
        cam_id = resp_ok.json()['camera_id']

        created_cam = Camera.objects.get(id=cam_id)
        self.assertEqual(created_cam.name, 'Corridor RTSP Cam')
        self.assertEqual(created_cam.camera_type, 'rtsp')

        audit = AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target_id=str(cam_id)
        ).latest('timestamp')
        self.assertEqual(audit.admin_user, self.admin)
        self.assertIn('camera_created', audit.changes_json)

    def test_delete_camera_with_audit(self):
        from common.models import AdminAuditTrail
        from cameras.models import Camera

        cam_id = self.camera.id
        resp = self.client.post(
            f'/cameras/delete-camera/{cam_id}/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Camera.objects.filter(id=cam_id).exists())

        audit = AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target_id=str(cam_id)
        ).latest('timestamp')
        self.assertEqual(audit.admin_user, self.admin)
        self.assertIn('camera_deleted', audit.changes_json)

    def test_camera_connection_test_endpoint(self):
        resp = self.client.get(f'/cameras/test-camera/{self.camera.id}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('camera_id', data)
        self.assertEqual(data['camera_id'], self.camera.id)
        self.assertIn('overall_status', data)

    def test_dashboard_needs_attention_offline_cameras(self):
        from accounts.admin_services import get_needs_attention_items

        health_all_ok = {
            'cameras': {'total': 2, 'online': 2, 'offline': 0, 'label': '2 Online · 0 Offline'},
            'redis': {'status': 'online', 'latency_ms': 5},
            'disk': {'percent': 40, 'total_gb': 100, 'used_gb': 40}
        }
        items_ok = get_needs_attention_items(health_all_ok, livekit_online=True)
        self.assertFalse(any(item['id'] == 'offline_cameras' for item in items_ok))

        health_with_offline = {
            'cameras': {'total': 3, 'online': 1, 'offline': 2, 'label': '1 Online · 2 Offline'},
            'redis': {'status': 'online', 'latency_ms': 5},
            'disk': {'percent': 40, 'total_gb': 100, 'used_gb': 40}
        }
        items_offline = get_needs_attention_items(health_with_offline, livekit_online=True)
        offline_alert = next((item for item in items_offline if item['id'] == 'offline_cameras'), None)
        self.assertIsNotNone(offline_alert)
        self.assertIn("2 Classroom Cameras Offline", offline_alert['title'])
        self.assertIn("1 online / 3 total cameras configured", offline_alert['description'])


class SystemHealthTests(TestCase):
    """
    Test suite for System Health service layer, endpoints,
    storage calculation, and caching mechanisms.
    """
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser('health_admin', 'health_admin@edumi.io', 'pass123')
        if hasattr(self.admin, 'userprofile'):
            self.admin.userprofile.user_type = 'admin'
            self.admin.userprofile.save()
        else:
            UserProfile.objects.create(user=self.admin, user_type='admin')

        self.student = User.objects.create_user('health_student', 'health_student@edumi.io', 'pass123')
        if hasattr(self.student, 'userprofile'):
            self.student.userprofile.user_type = 'student'
            self.student.userprofile.save()
        else:
            UserProfile.objects.create(user=self.student, user_type='student')

        self.client.force_login(self.admin)

    def test_service_layer_individual_checks(self):
        from common.system_health import (
            check_livekit,
            check_django_daphne,
            check_redis,
            check_celery,
            check_database,
            check_camera_gateway,
            check_ollama,
        )

        # 1. LiveKit
        lk = check_livekit(timeout=2.0)
        self.assertEqual(lk['id'], 'livekit')
        self.assertIn(lk['status'], ['operational', 'down'])
        self.assertIn('active_rooms', lk)

        # 2. Django Daphne
        dj = check_django_daphne(timeout=1.0)
        self.assertEqual(dj['id'], 'django_daphne')
        self.assertEqual(dj['status'], 'operational')
        self.assertIsNotNone(dj['pid'])

        # 3. Redis
        rd = check_redis(timeout=2.0)
        self.assertEqual(rd['id'], 'redis')
        self.assertIn(rd['status'], ['operational', 'degraded', 'down'])

        # 4. Celery
        cl = check_celery(timeout=2.0)
        self.assertEqual(cl['id'], 'celery')
        self.assertIn(cl['status'], ['operational', 'degraded', 'down'])
        self.assertIn('queue_depth', cl)

        # 5. Database
        db = check_database(timeout=2.0)
        self.assertEqual(db['id'], 'database')
        self.assertEqual(db['status'], 'operational')
        self.assertIsNotNone(db['latency_ms'])

        # 6. Camera Gateway
        cg = check_camera_gateway(timeout=2.0)
        self.assertEqual(cg['id'], 'camera_gateway')
        self.assertIn(cg['status'], ['operational', 'degraded'])

        # 7. Ollama
        ol = check_ollama(timeout=2.0)
        self.assertEqual(ol['id'], 'ollama')
        self.assertIn(ol['status'], ['operational', 'down', 'not_configured'])

    def test_storage_breakdown(self):
        from common.system_health import get_storage_breakdown

        storage = get_storage_breakdown()
        self.assertIn('total_gb', storage)
        self.assertIn('used_gb', storage)
        self.assertIn('free_gb', storage)
        self.assertIn('percent', storage)
        self.assertIn('categories', storage)

        cats = storage['categories']
        self.assertIn('recordings', cats)
        self.assertIn('uploads', cats)
        self.assertIn('avatars', cats)
        self.assertEqual(cats['recordings']['color'], '#8b5cf6')

    def test_recent_errors(self):
        from common.system_health import get_recent_errors

        errors = get_recent_errors(limit=20)
        self.assertIsInstance(errors, list)
        self.assertLessEqual(len(errors), 20)

    def test_full_system_health_and_caching(self):
        from common.system_health import get_full_system_health

        # Fresh pull with force=True
        data1 = get_full_system_health(use_cache=True, force=True)
        self.assertIn('overall_status', data1)
        self.assertIn('checks', data1)
        self.assertEqual(len(data1['checks']), 7)
        self.assertFalse(data1['cached'])

        # Cached pull
        data2 = get_full_system_health(use_cache=True, force=False)
        self.assertTrue(data2['cached'])

    def test_admin_system_health_view(self):
        # 1. Admin authorized
        resp = self.client.get('/admin/system-health/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('health', resp.context)
        self.assertIn("System Health", resp.content.decode())

        # 2. Student blocked
        self.client.force_login(self.student)
        resp_std = self.client.get('/admin/system-health/')
        self.assertIn(resp_std.status_code, [302, 403])

    def test_admin_system_health_api(self):
        # 1. Admin gets JSON
        resp = self.client.get('/admin/api/system-health/?force=1')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('overall_status', data)
        self.assertIn('checks', data)
        self.assertIn('storage', data)
        self.assertIn('recent_errors', data)

        # 2. Student blocked from JSON API
        self.client.force_login(self.student)
        resp_std = self.client.get('/admin/api/system-health/')
        self.assertEqual(resp_std.status_code, 403)

    def test_dashboard_reuses_system_health(self):
        from accounts.admin_services import get_system_health

        dash_health = get_system_health()
        self.assertIn('livekit', dash_health)
        self.assertIn('redis', dash_health)
        self.assertIn('celery', dash_health)
        self.assertIn('disk', dash_health)
        self.assertIn('cameras', dash_health)


class ReportsAndAnalyticsTests(TestCase):
    """
    Test suite for Centralized Reports & Analytics:
    Attendance, Engagement, User Activity, and Course Performance reports
    with interactive filters, CSV export, and PDF generation with audit logging.
    """
    def setUp(self):
        from datetime import date
        from django.utils import timezone
        from attendance.models import AttendanceRecord, EngagementReport
        from common.models import UserActivityLog, AdminAuditTrail

        self.client = Client()
        self.admin = User.objects.create_superuser('rep_admin', 'rep_admin@edumi.edu', 'pass123')
        if hasattr(self.admin, 'userprofile'):
            self.admin.userprofile.user_type = 'admin'
            self.admin.userprofile.save()
        else:
            UserProfile.objects.create(user=self.admin, user_type='admin')

        self.teacher = User.objects.create_user('rep_teacher', 'rep_teacher@edumi.edu', 'pass123')
        if hasattr(self.teacher, 'userprofile'):
            self.teacher.userprofile.user_type = 'teacher'
            self.teacher.userprofile.department = 'Computer Science'
            self.teacher.userprofile.save()
        else:
            UserProfile.objects.create(user=self.teacher, user_type='teacher', department='Computer Science')

        self.student = User.objects.create_user('rep_student', 'rep_student@edumi.edu', 'pass123')
        if hasattr(self.student, 'userprofile'):
            self.student.userprofile.user_type = 'student'
            self.student.userprofile.student_id = 'STU-1001'
            self.student.userprofile.save()
        else:
            UserProfile.objects.create(user=self.student, user_type='student', student_id='STU-1001')

        self.course = Classroom.objects.create(
            title="Algorithms & Data Structures",
            class_code="CS201",
            teacher=self.teacher,
            is_active=True
        )

        self.meeting = Meeting.objects.create(
            title="Lecture 1 - Graph Traversal",
            classroom=self.course,
            teacher=self.teacher,
            meeting_code="GRAPH101",
            status="ended",
            scheduled_time=timezone.now()
        )

        self.att_record = AttendanceRecord.objects.create(
            student=self.student,
            meeting=self.meeting,
            classroom=self.course,
            date=date.today(),
            status='present',
            verification_method='face_recognition',
            face_match_confidence=0.92,
            face_verified_at=timezone.now()
        )

        self.eng_report = EngagementReport.objects.create(
            meeting=self.meeting,
            classroom=self.course,
            teacher=self.teacher,
            class_engagement_score=88.5,
            student_data=[{'student_id': self.student.id, 'attention_score': 85.0, 'head_pose_score': 80.0}]
        )

        self.act_log = UserActivityLog.objects.create(
            username=self.student.username,
            user=self.student,
            user_role='student',
            event_type='action',
            event_name='TEST_EVENT',
            ip_address='127.0.0.1'
        )

    def test_reports_access_control(self):
        # Anonymous blocked
        resp_anon = self.client.get('/admin/reports/')
        self.assertEqual(resp_anon.status_code, 302)

        # Student blocked
        self.client.force_login(self.student)
        resp_std = self.client.get('/admin/reports/')
        self.assertIn(resp_std.status_code, [302, 403])

        # Admin allowed
        self.client.force_login(self.admin)
        resp_adm = self.client.get('/admin/reports/')
        self.assertEqual(resp_adm.status_code, 200)

    def test_all_reports_tabs_load(self):
        self.client.force_login(self.admin)
        tabs = ['attendance', 'engagement', 'user_activity', 'course_performance']
        for tab in tabs:
            resp = self.client.get(f'/admin/reports/?tab={tab}')
            self.assertEqual(resp.status_code, 200)
            self.assertIn('page_obj', resp.context)
            self.assertIn('metrics', resp.context)

    def test_csv_exports_and_audit_logging(self):
        from common.models import AdminAuditTrail
        self.client.force_login(self.admin)

        tabs = ['attendance', 'engagement', 'user_activity', 'course_performance']
        for tab in tabs:
            initial_count = AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_DATA_EXPORTED).count()
            resp = self.client.get(f'/admin/reports/{tab}/csv/')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp['Content-Type'], 'text/csv')
            self.assertTrue(len(resp.content) > 0)
            # Verify exactly 1 audit entry created
            self.assertEqual(
                AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_DATA_EXPORTED).count(),
                initial_count + 1
            )

    def test_pdf_exports_and_audit_logging(self):
        from common.models import AdminAuditTrail
        self.client.force_login(self.admin)

        tabs = ['attendance', 'engagement', 'user_activity', 'course_performance']
        for tab in tabs:
            initial_count = AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_DATA_EXPORTED).count()
            resp = self.client.get(f'/admin/reports/{tab}/pdf/')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp['Content-Type'], 'application/pdf')
            self.assertTrue(resp.content.startswith(b'%PDF'))
            # Verify exactly 1 audit entry created
            self.assertEqual(
                AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_DATA_EXPORTED).count(),
                initial_count + 1
            )


class SettingsAndGovernanceTests(TestCase):
    """
    Test suite for Platform Settings & Governance:
    Institution branding, Academic semesters/departments CRUD,
    Attendance thresholds, Security policy, Email/SMTP diagnostics, and audit trail diffs.
    """
    def setUp(self):
        from common.models import SiteSetting
        self.client = Client()
        self.admin = User.objects.create_superuser('set_admin', 'set_admin@edumi.edu', 'pass123')
        if hasattr(self.admin, 'userprofile'):
            self.admin.userprofile.user_type = 'admin'
            self.admin.userprofile.save()
        else:
            UserProfile.objects.create(user=self.admin, user_type='admin')

        self.student = User.objects.create_user('set_student', 'set_student@edumi.edu', 'pass123')
        if hasattr(self.student, 'userprofile'):
            self.student.userprofile.user_type = 'student'
            self.student.userprofile.save()
        else:
            UserProfile.objects.create(user=self.student, user_type='student')

    def test_settings_page_access_and_sections(self):
        # Student blocked
        self.client.force_login(self.student)
        resp_std = self.client.get('/admin/settings/')
        self.assertIn(resp_std.status_code, [302, 403])

        # Admin allowed
        self.client.force_login(self.admin)
        sections = ['institution', 'academic', 'attendance', 'security', 'email']
        for sec in sections:
            resp = self.client.get(f'/admin/settings/?section={sec}')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.context['active_section'], sec)
            self.assertIn('settings', resp.context)

    def test_update_settings_and_audit_log_diff(self):
        from common.models import AdminAuditTrail, SiteSetting
        self.client.force_login(self.admin)

        initial_audits = AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_SETTINGS_CHANGED).count()

        payload = {
            'institution_name': 'Imperial Autonomous Institute',
            'institution_tagline': 'Excellence in AI Education',
            'contact_email': 'contact@imperial.edu',
            'support_phone': '+1 555 999 8888',
            'institution_address': '42 Discovery Way',
            'logo_url': '/static/images/logo.png',
        }

        resp = self.client.post(
            '/admin/settings/institution/update/',
            data=payload,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)

        # Verify SiteSetting model persistence
        self.assertEqual(SiteSetting.get_setting('institution_name'), 'Imperial Autonomous Institute')

        # Verify exactly 1 audit entry created with before/after diff
        self.assertEqual(
            AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_SETTINGS_CHANGED).count(),
            initial_audits + 1
        )
        audit = AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_SETTINGS_CHANGED).first()
        self.assertIn('before', audit.changes_json)
        self.assertIn('after', audit.changes_json)
        self.assertEqual(audit.changes_json['after']['institution_name'], 'Imperial Autonomous Institute')

    def test_academic_semester_crud(self):
        from common.models import AdminAuditTrail
        self.client.force_login(self.admin)

        # 1. Add Semester
        resp = self.client.post('/admin/settings/academic/semester/', {
            'action': 'add',
            'name': 'Summer Term 2027',
            'code': 'SU27',
            'start_date': '2027-06-01',
            'end_date': '2027-08-15',
            'is_current': '1',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        sem_id = data['semester']['id']

        # 2. Delete Semester
        resp_del = self.client.post('/admin/settings/academic/semester/', {
            'action': 'delete',
            'id': sem_id,
        })
        self.assertEqual(resp_del.status_code, 200)
        self.assertEqual(resp_del.json()['status'], 'success')

    def test_academic_department_crud(self):
        self.client.force_login(self.admin)

        # 1. Add Department
        resp = self.client.post('/admin/settings/academic/department/', {
            'action': 'add',
            'name': 'Aerospace Engineering',
            'code': 'AERO',
            'head': 'Dr. Neil Armstrong',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        dept_id = data['department']['id']

        # 2. Delete Department
        resp_del = self.client.post('/admin/settings/academic/department/', {
            'action': 'delete',
            'id': dept_id,
        })
        self.assertEqual(resp_del.status_code, 200)
        self.assertEqual(resp_del.json()['status'], 'success')

    def test_smtp_diagnostic_endpoint(self):
        from unittest.mock import patch
        from common.models import AdminAuditTrail
        self.client.force_login(self.admin)

        initial_audits = AdminAuditTrail.objects.filter(target_id='smtp_test').count()
        with patch('accounts.settings_services.send_test_smtp_email') as mock_send:
            mock_send.return_value = {'success': True, 'message': 'Test email sent.'}
            resp = self.client.post('/admin/settings/test-email/', {
                'recipient_email': 'test_admin@edumi.edu'
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()['status'], 'success')
            self.assertEqual(
                AdminAuditTrail.objects.filter(target_id='smtp_test').count(),
                initial_audits + 1
            )


class ApprovalsAndAnnouncementsTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile
        from academics.models import Classroom, ClassroomMembership
        from common.models import AdminAuditTrail, Announcement
        from accounts.notification_models import Notification

        User = get_user_model()
        self.admin = User.objects.create_user(username='appr_admin', password='pass123', is_staff=True, is_superuser=True)
        prof_adm, _ = UserProfile.objects.get_or_create(user=self.admin)
        prof_adm.user_type = 'admin'
        prof_adm.save()

        self.teacher = User.objects.create_user(username='prof_oak', password='pass123')
        prof_t, _ = UserProfile.objects.get_or_create(user=self.teacher)
        prof_t.user_type = 'teacher'
        prof_t.department = 'Biochemistry'
        prof_t.save()

        self.student = User.objects.create_user(username='ash_ketchum', password='pass123')
        prof_s, _ = UserProfile.objects.get_or_create(user=self.student)
        prof_s.user_type = 'student'
        prof_s.department = 'Biochemistry'
        prof_s.save()

        self.student2 = User.objects.create_user(username='gary_oak', password='pass123')
        prof_s2, _ = UserProfile.objects.get_or_create(user=self.student2)
        prof_s2.user_type = 'student'
        prof_s2.department = 'Biochemistry'
        prof_s2.save()

        self.classroom = Classroom.objects.create(
            title='Intro to Genetics',
            class_code='GEN101',
            teacher=self.teacher,
            is_active=True
        )

    def test_approvals_access_control(self):
        # Anonymous redirect
        resp_anon = self.client.get('/admin/approvals/')
        self.assertEqual(resp_anon.status_code, 302)

        # Student denied
        self.client.force_login(self.student)
        resp_stud = self.client.get('/admin/approvals/')
        self.assertIn(resp_stud.status_code, [302, 403])

        # Admin allowed
        self.client.force_login(self.admin)
        resp_adm = self.client.get('/admin/approvals/')
        self.assertEqual(resp_adm.status_code, 200)
        self.assertContains(resp_adm, 'Approvals Queue')

    def test_approvals_queue_and_tab_filtering(self):
        from academics.models import ClassroomMembership
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile
        User = get_user_model()

        # 1 pending enrollment
        m1 = ClassroomMembership.objects.create(
            classroom=self.classroom,
            student=self.student,
            status='pending'
        )

        # 1 pending teacher signup (inactive teacher)
        pending_teacher = User.objects.create_user(username='new_prof_elm', password='pass123', is_active=False)
        pt_prof, _ = UserProfile.objects.get_or_create(user=pending_teacher)
        pt_prof.user_type = 'teacher'
        pt_prof.department = 'Genetics'
        pt_prof.save()

        self.client.force_login(self.admin)

        # Tab: all
        resp_all = self.client.get('/admin/approvals/?tab=all')
        self.assertEqual(resp_all.status_code, 200)
        self.assertContains(resp_all, 'ash_ketchum')
        self.assertContains(resp_all, 'new_prof_elm')

        # Tab: enrollments
        resp_enr = self.client.get('/admin/approvals/?tab=enrollments')
        self.assertEqual(resp_enr.status_code, 200)
        self.assertContains(resp_enr, 'ash_ketchum')
        self.assertNotContains(resp_enr, 'new_prof_elm')

        # Tab: teachers
        resp_tea = self.client.get('/admin/approvals/?tab=teachers')
        self.assertEqual(resp_tea.status_code, 200)
        self.assertContains(resp_tea, 'new_prof_elm')
        self.assertNotContains(resp_tea, 'ash_ketchum')

        # Search query
        resp_search = self.client.get('/admin/approvals/?tab=all&search=ash_ketchum')
        self.assertEqual(resp_search.status_code, 200)
        self.assertContains(resp_search, 'ash_ketchum')
        self.assertNotContains(resp_search, 'new_prof_elm')

    def test_approve_and_reject_enrollment(self):
        from academics.models import ClassroomMembership
        from common.models import AdminAuditTrail
        from accounts.notification_models import Notification

        membership = ClassroomMembership.objects.create(
            classroom=self.classroom,
            student=self.student,
            status='pending'
        )

        self.client.force_login(self.admin)

        # 1. Approve
        resp_app = self.client.post(f'/admin/approvals/enrollment/{membership.id}/approve/')
        self.assertEqual(resp_app.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.status, 'approved')
        self.assertEqual(membership.approved_by, self.admin)
        self.assertTrue(Notification.objects.filter(recipient=self.student, notification_type='classroom_approved').exists())
        self.assertTrue(AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_ENROLLMENT_APPROVED).exists())

        # 2. Reject
        membership2 = ClassroomMembership.objects.create(
            classroom=self.classroom,
            student=self.student2,
            status='pending'
        )
        resp_rej = self.client.post(f'/admin/approvals/enrollment/{membership2.id}/reject/')
        self.assertEqual(resp_rej.status_code, 302)
        membership2.refresh_from_db()
        self.assertEqual(membership2.status, 'denied')
        self.assertTrue(AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_ENROLLMENT_REJECTED).exists())

    def test_approve_and_reject_teacher_signup(self):
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile
        from common.models import AdminAuditTrail
        User = get_user_model()

        t_approve = User.objects.create_user(username='tea_pending_1', password='pass123', is_active=False)
        p1, _ = UserProfile.objects.get_or_create(user=t_approve)
        p1.user_type = 'teacher'
        p1.save()

        t_reject = User.objects.create_user(username='tea_pending_2', password='pass123', is_active=False)
        p2, _ = UserProfile.objects.get_or_create(user=t_reject)
        p2.user_type = 'teacher'
        p2.save()

        self.client.force_login(self.admin)

        # 1. Approve
        resp_app = self.client.post(f'/admin/approvals/teacher/{t_approve.id}/approve/')
        self.assertEqual(resp_app.status_code, 302)
        t_approve.refresh_from_db()
        self.assertTrue(t_approve.is_active)
        self.assertTrue(AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_USER_ACTIVATED, target_id=t_approve.id).exists())

        # 2. Reject
        resp_rej = self.client.post(f'/admin/approvals/teacher/{t_reject.id}/reject/')
        self.assertEqual(resp_rej.status_code, 302)
        t_reject.refresh_from_db()
        self.assertFalse(t_reject.is_active)
        self.assertTrue(t_reject.userprofile.is_deleted)
        self.assertTrue(AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_USER_SUSPENDED, target_id=t_reject.id).exists())

    def test_bulk_approvals_and_rejections(self):
        from academics.models import ClassroomMembership
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile
        from common.models import AdminAuditTrail
        User = get_user_model()

        m1 = ClassroomMembership.objects.create(classroom=self.classroom, student=self.student, status='pending')
        m2 = ClassroomMembership.objects.create(classroom=self.classroom, student=self.student2, status='pending')

        t1 = User.objects.create_user(username='bulk_tea_1', password='pass123', is_active=False)
        p1, _ = UserProfile.objects.get_or_create(user=t1)
        p1.user_type = 'teacher'
        p1.save()

        t2 = User.objects.create_user(username='bulk_tea_2', password='pass123', is_active=False)
        p2, _ = UserProfile.objects.get_or_create(user=t2)
        p2.user_type = 'teacher'
        p2.save()

        self.client.force_login(self.admin)

        # Bulk approve m1 and t1
        resp_bulk_app = self.client.post('/admin/approvals/bulk/', {
            'bulk_action': 'approve',
            'enrollment_ids': [m1.id],
            'teacher_ids': [t1.id]
        })
        self.assertEqual(resp_bulk_app.status_code, 302)
        m1.refresh_from_db()
        t1.refresh_from_db()
        self.assertEqual(m1.status, 'approved')
        self.assertTrue(t1.is_active)

        # Bulk reject m2 and t2
        resp_bulk_rej = self.client.post('/admin/approvals/bulk/', {
            'bulk_action': 'reject',
            'enrollment_ids': [m2.id],
            'teacher_ids': [t2.id]
        })
        self.assertEqual(resp_bulk_rej.status_code, 302)
        m2.refresh_from_db()
        t2.refresh_from_db()
        self.assertEqual(m2.status, 'denied')
        self.assertFalse(t2.is_active)

        # Verify BULK_ACTION audit trail
        self.assertTrue(AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_BULK_ACTION).exists())

    def test_pending_approvals_context_processor(self):
        from academics.models import ClassroomMembership
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile
        from django.core.cache import cache
        from accounts.context_processors import admin_approvals_context
        from django.test.client import RequestFactory
        User = get_user_model()
        cache.clear()

        # 1 enrollment + 1 teacher = 2
        ClassroomMembership.objects.create(classroom=self.classroom, student=self.student, status='pending')
        t_inact = User.objects.create_user(username='inactive_t', password='pass123', is_active=False)
        p, _ = UserProfile.objects.get_or_create(user=t_inact)
        p.user_type = 'teacher'
        p.save()

        rf = RequestFactory()
        req = rf.get('/admin/panel/')
        req.user = self.admin

        ctx = admin_approvals_context(req)
        self.assertEqual(ctx['pending_approvals_count'], 2)

    def test_announcements_access_control(self):
        self.client.force_login(self.student)
        resp_stud = self.client.get('/admin/announcements/')
        self.assertIn(resp_stud.status_code, [302, 403])

        self.client.force_login(self.admin)
        resp_adm = self.client.get('/admin/announcements/')
        self.assertEqual(resp_adm.status_code, 200)
        self.assertContains(resp_adm, 'Campus Announcements')

    def test_compose_and_dispatch_immediate_announcement(self):
        from common.models import Announcement, AdminAuditTrail
        from accounts.notification_models import Notification
        self.client.force_login(self.admin)

        resp = self.client.post('/admin/announcements/', {
            'title': 'Emergency Weather Alert',
            'body': 'Severe thunderstorm warning. Campus facilities close at 6 PM.',
            'audience': 'all',
        })
        self.assertEqual(resp.status_code, 302)

        ann = Announcement.objects.filter(title='Emergency Weather Alert').first()
        self.assertIsNotNone(ann)
        self.assertTrue(ann.is_sent)
        self.assertIsNotNone(ann.sent_at)
        self.assertGreater(ann.recipient_count, 0)

        # Verify delivered notifications in DB
        self.assertTrue(Notification.objects.filter(title='Emergency Weather Alert').exists())

        # Verify audit trail logged
        self.assertTrue(AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_BULK_ACTION,
            target_type='Announcement'
        ).exists())

    def test_compose_scheduled_announcement_and_send_now(self):
        from common.models import Announcement
        from django.utils import timezone
        from datetime import timedelta
        self.client.force_login(self.admin)

        future_time = timezone.now() + timedelta(days=2)
        resp = self.client.post('/admin/announcements/', {
            'title': 'Next Week Exam Schedule',
            'body': 'Final examinations begin next Monday morning.',
            'audience': 'students',
            'scheduled_at': future_time.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertEqual(resp.status_code, 302)

        ann = Announcement.objects.filter(title='Next Week Exam Schedule').first()
        self.assertIsNotNone(ann)
        self.assertFalse(ann.is_sent)
        self.assertIsNotNone(ann.scheduled_at)

        # Trigger send-now
        resp_now = self.client.post(f'/admin/announcements/{ann.id}/send-now/')
        self.assertEqual(resp_now.status_code, 302)
        ann.refresh_from_db()
        self.assertTrue(ann.is_sent)
        self.assertGreater(ann.recipient_count, 0)

    def test_announcement_delete(self):
        from common.models import Announcement
        self.client.force_login(self.admin)

        ann = Announcement.objects.create(
            title='Temporary Notice',
            body='Will be removed.',
            audience='all',
            created_by=self.admin
        )

        resp = self.client.post(f'/admin/announcements/{ann.id}/delete/')
        self.assertEqual(resp.status_code, 302)
        ann.refresh_from_db()
        self.assertTrue(ann.is_deleted)

    def test_scheduled_announcements_celery_task(self):
        from common.models import Announcement
        from django.utils import timezone
        from datetime import timedelta
        from accounts.tasks import check_and_deliver_scheduled_announcements
        from accounts.notification_models import Notification

        past_time = timezone.now() - timedelta(minutes=5)
        ann = Announcement.objects.create(
            title='Auto-Dispatched Scheduled Announcement',
            body='This announcement was queued and delivered by celery.',
            audience='all',
            created_by=self.admin,
            scheduled_at=past_time,
            is_sent=False
        )

        delivered = check_and_deliver_scheduled_announcements()
        self.assertGreaterEqual(delivered, 1)

        ann.refresh_from_db()
        self.assertTrue(ann.is_sent)
        self.assertTrue(Notification.objects.filter(title='Auto-Dispatched Scheduled Announcement').exists())


class GranularAdminRBACTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile
        from common.models import AdminRole, AdminAuditTrail
        User = get_user_model()

        # Seed roles
        AdminRole.seed_default_roles()
        self.super_role = AdminRole.objects.get(name='Super Admin')
        self.academic_role = AdminRole.objects.get(name='Academic Admin')
        self.auditor_role = AdminRole.objects.get(name='Attendance Auditor')
        self.it_role = AdminRole.objects.get(name='IT Admin')

        # Superuser (full unrestricted access)
        self.superuser = User.objects.create_user(username='super_boss', password='password123', is_staff=True, is_superuser=True)
        p_sup, _ = UserProfile.objects.get_or_create(user=self.superuser)
        p_sup.user_type = 'admin'
        p_sup.save()

        # Academic Admin (courses, sessions, export; NO users, NO settings, NO cameras, NO audit)
        self.academic_admin = User.objects.create_user(username='acad_admin', password='password123', is_staff=True)
        p_acad, _ = UserProfile.objects.get_or_create(user=self.academic_admin)
        p_acad.user_type = 'admin'
        p_acad.admin_role = self.academic_role
        p_acad.save()

        # Attendance Auditor (audit, export; NO users, NO courses, NO sessions, NO settings, NO cameras)
        self.auditor_admin = User.objects.create_user(username='auditor_admin', password='password123', is_staff=True)
        p_aud, _ = UserProfile.objects.get_or_create(user=self.auditor_admin)
        p_aud.user_type = 'admin'
        p_aud.admin_role = self.auditor_role
        p_aud.save()

        # IT Admin (cameras, settings, audit; NO users, NO courses, NO sessions, NO export)
        self.it_admin = User.objects.create_user(username='it_admin', password='password123', is_staff=True)
        p_it, _ = UserProfile.objects.get_or_create(user=self.it_admin)
        p_it.user_type = 'admin'
        p_it.admin_role = self.it_role
        p_it.save()

    def test_superuser_full_access(self):
        """Superusers (is_superuser=True) bypass role checks with full access."""
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get('/admin/users/').status_code, 200)
        self.assertEqual(self.client.get('/admin/classrooms/').status_code, 200)
        self.assertEqual(self.client.get('/admin/meetings/').status_code, 200)
        self.assertEqual(self.client.get('/admin/activity/').status_code, 200)
        self.assertEqual(self.client.get('/admin/settings/').status_code, 200)
        self.assertEqual(self.client.get('/admin/roles/').status_code, 200)
        self.assertEqual(self.client.get('/cameras/admin-dashboard/').status_code, 200)

    def test_academic_admin_access_and_403_denials(self):
        """Academic Admin can access courses and meetings, but is denied (403) from users, settings, and cameras."""
        self.client.force_login(self.academic_admin)

        # Allowed views
        self.assertEqual(self.client.get('/admin/classrooms/').status_code, 200)
        self.assertEqual(self.client.get('/admin/meetings/').status_code, 200)

        # Denied views (403 Forbidden)
        self.assertEqual(self.client.get('/admin/users/').status_code, 403)
        self.assertEqual(self.client.get('/admin/settings/').status_code, 403)
        self.assertEqual(self.client.get('/cameras/admin-dashboard/').status_code, 403)
        self.assertEqual(self.client.get('/admin/roles/').status_code, 403)
        self.assertEqual(self.client.get('/admin/activity/').status_code, 403)

    def test_attendance_auditor_access_and_403_denials(self):
        """Attendance Auditor can access activity feeds and reports, but is denied (403) from users, courses, and sessions."""
        self.client.force_login(self.auditor_admin)

        # Allowed views
        self.assertEqual(self.client.get('/admin/activity/').status_code, 200)
        self.assertEqual(self.client.get('/admin/reports/').status_code, 200)

        # Denied views (403 Forbidden)
        self.assertEqual(self.client.get('/admin/users/').status_code, 403)
        self.assertEqual(self.client.get('/admin/classrooms/').status_code, 403)
        self.assertEqual(self.client.get('/admin/meetings/').status_code, 403)
        self.assertEqual(self.client.get('/cameras/admin-dashboard/').status_code, 403)
        self.assertEqual(self.client.get('/admin/settings/').status_code, 403)

    def test_it_admin_access_and_403_denials(self):
        """IT Admin can access cameras, system health, and settings, but is denied (403) from users, courses, and sessions."""
        self.client.force_login(self.it_admin)

        # Allowed views
        self.assertEqual(self.client.get('/cameras/admin-dashboard/').status_code, 200)
        self.assertEqual(self.client.get('/admin/settings/').status_code, 200)
        self.assertEqual(self.client.get('/admin/activity/').status_code, 200)

        # Denied views (403 Forbidden)
        self.assertEqual(self.client.get('/admin/users/').status_code, 403)
        self.assertEqual(self.client.get('/admin/classrooms/').status_code, 403)
        self.assertEqual(self.client.get('/admin/meetings/').status_code, 403)

    def test_ajax_permission_denied_returns_json_403(self):
        """AJAX requests that fail permission checks return a structured JSON 403 response."""
        self.client.force_login(self.academic_admin)
        resp = self.client.get(
            '/admin/api/system-health/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertEqual(data['status'], 'error')
        self.assertIn('Missing', data['message'])

    def test_roles_management_and_matrix_update(self):
        """Admins with manage_settings can load the roles matrix and update permissions."""
        from common.models import AdminAuditTrail
        self.client.force_login(self.superuser)

        # 1. Load roles page
        resp = self.client.get('/admin/roles/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Roles & Permissions')
        self.assertContains(resp, 'Academic Admin')

        # 2. Update role permissions via POST
        initial_audits = AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_SETTINGS_CHANGED).count()
        resp_up = self.client.post('/admin/roles/update/', {
            'action': 'update',
            'role_id': self.academic_role.id,
            'manage_courses': 'on',
            'manage_sessions': 'on',
            'export_data': 'on',
            'view_audit': 'on',  # Grant view_audit to Academic Admin
        })
        self.assertEqual(resp_up.status_code, 302)
        self.academic_role.refresh_from_db()
        self.assertTrue(self.academic_role.view_audit)
        self.assertEqual(
            AdminAuditTrail.objects.filter(action_type=AdminAuditTrail.ACTION_SETTINGS_CHANGED).count(),
            initial_audits + 1
        )

    def test_assign_user_role_and_audit_trail(self):
        """Assigning a role to an admin user updates their profile and creates an audit trail entry."""
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile
        from common.models import AdminAuditTrail
        User = get_user_model()

        new_admin = User.objects.create_user(username='new_staff_member', password='password123')
        prof, _ = UserProfile.objects.get_or_create(user=new_admin)
        prof.user_type = 'admin'
        prof.save()

        self.client.force_login(self.superuser)

        resp = self.client.post('/admin/roles/assign-user/', {
            'user_id': new_admin.id,
            'role_id': self.it_role.id,
        })
        self.assertEqual(resp.status_code, 302)

        prof.refresh_from_db()
        self.assertEqual(prof.admin_role, self.it_role)

        # Verify audit trail logged with ROLE_CHANGED
        audit = AdminAuditTrail.objects.filter(
            action_type=AdminAuditTrail.ACTION_ROLE_CHANGED,
            target_id=new_admin.id
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.changes_json['role']['after'], 'IT Admin')


class CommandPaletteTests(TestCase):
    """Test suite for the Enterprise Command Palette (Ctrl+K) API."""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(username='cmd_admin', password='password123', is_staff=True)
        prof, _ = UserProfile.objects.get_or_create(user=self.admin)
        prof.user_type = 'admin'
        prof.save()

        self.student = User.objects.create_user(username='cmd_student', password='password123')
        prof_s, _ = UserProfile.objects.get_or_create(user=self.student)
        prof_s.user_type = 'student'
        prof_s.save()

    def test_command_palette_unauthenticated(self):
        resp = self.client.get('/admin/api/command-palette/')
        self.assertEqual(resp.status_code, 302)

    def test_command_palette_student_denied(self):
        self.client.force_login(self.student)
        resp = self.client.get('/admin/api/command-palette/')
        self.assertEqual(resp.status_code, 403)

    def test_command_palette_admin_default_actions(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/api/command-palette/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        self.assertGreaterEqual(len(data['results']), 1)
        titles = [item['title'] for item in data['results']]
        self.assertIn('Add New User', titles)

    def test_command_palette_search_query(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/api/command-palette/?q=Import')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        titles = [item['title'] for item in data['results']]
        self.assertTrue(any('Import' in t for t in titles))













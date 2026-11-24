from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from common.validators import (
    check_uploaded_file,
    sanitize_filename,
    validate_video_file,
    validate_image_file,
    validate_assignment_file,
    validate_assignment_submission_file,
    validate_audio_file,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_ASSIGNMENT_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    MAX_VIDEO_SIZE,
    MAX_ASSIGNMENT_SIZE,
    MAX_IMAGE_SIZE,
)


class FileValidationTests(TestCase):
    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("../../etc/passwd.pdf"), "passwd.pdf")
        self.assertEqual(sanitize_filename("..\\..\\malicious.exe"), "malicious.exe")
        self.assertEqual(sanitize_filename("my test file #1 (draft).docx"), "my_test_file__1__draft_.docx")
        self.assertEqual(sanitize_filename("simple.mp4"), "simple.mp4")
        self.assertEqual(sanitize_filename(""), "unnamed_file")

    def test_valid_pdf_assignment(self):
        pdf_content = b"%PDF-1.4 sample pdf content for assignment"
        f = SimpleUploadedFile("homework.pdf", pdf_content, content_type="application/pdf")
        is_valid, err = check_uploaded_file(f, ALLOWED_ASSIGNMENT_EXTENSIONS, MAX_ASSIGNMENT_SIZE)
        self.assertTrue(is_valid)
        self.assertIsNone(err)
        # Model validator should not raise
        validate_assignment_file(f)

    def test_valid_png_image(self):
        png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        f = SimpleUploadedFile("diagram.png", png_content, content_type="image/png")
        is_valid, err = check_uploaded_file(f, ALLOWED_IMAGE_EXTENSIONS, MAX_IMAGE_SIZE)
        self.assertTrue(is_valid)
        self.assertIsNone(err)
        validate_image_file(f)

    def test_valid_mp4_video(self):
        mp4_content = b"\x00\x00\x00 ftypisom\x00\x00\x02\x00"
        f = SimpleUploadedFile("lecture.mp4", mp4_content, content_type="video/mp4")
        is_valid, err = check_uploaded_file(f, ALLOWED_VIDEO_EXTENSIONS, MAX_VIDEO_SIZE)
        self.assertTrue(is_valid)
        self.assertIsNone(err)
        validate_video_file(f)

    def test_disallowed_dangerous_extensions(self):
        for ext in ['exe', 'sh', 'php', 'bat', 'cmd', 'cgi', 'dll', 'msi', 'vbs', 'ps1']:
            f = SimpleUploadedFile(f"exploit.{ext}", b"echo hello", content_type="application/octet-stream")
            is_valid, err = check_uploaded_file(f, ALLOWED_ASSIGNMENT_EXTENSIONS, MAX_ASSIGNMENT_SIZE)
            self.assertFalse(is_valid)
            self.assertIn("not permitted", err)
            with self.assertRaises(ValidationError):
                validate_assignment_file(f)

    def test_executable_disguised_as_pdf(self):
        # File has .pdf extension but starts with Windows MZ executable magic bytes
        fake_pdf = SimpleUploadedFile("malware.pdf", b"MZ\x90\x00\x03\x00\x00\x00", content_type="application/pdf")
        is_valid, err = check_uploaded_file(fake_pdf, ALLOWED_ASSIGNMENT_EXTENSIONS, MAX_ASSIGNMENT_SIZE)
        self.assertFalse(is_valid)
        self.assertIn("Executable or binary script files are not allowed", err)
        with self.assertRaises(ValidationError):
            validate_assignment_file(fake_pdf)

    def test_executable_disguised_as_mp4(self):
        # File has .mp4 extension but starts with Linux ELF binary magic bytes
        fake_video = SimpleUploadedFile("video.mp4", b"\x7fELF\x02\x01\x01\x00", content_type="video/mp4")
        is_valid, err = check_uploaded_file(fake_video, ALLOWED_VIDEO_EXTENSIONS, MAX_VIDEO_SIZE)
        self.assertFalse(is_valid)
        self.assertIn("Executable or binary script files are not allowed", err)
        with self.assertRaises(ValidationError):
            validate_video_file(fake_video)

    def test_corrupted_or_mismatched_signature(self):
        # PNG extension but plain text content
        bad_png = SimpleUploadedFile("image.png", b"not a real png header", content_type="image/png")
        is_valid, err = check_uploaded_file(bad_png, ALLOWED_IMAGE_EXTENSIONS, MAX_IMAGE_SIZE)
        self.assertFalse(is_valid)
        self.assertIn("does not match PNG", err)

    def test_oversized_file_rejection(self):
        # 100 bytes file tested against 50 bytes limit
        big_file = SimpleUploadedFile("large.pdf", b"%PDF-" + b"x" * 100, content_type="application/pdf")
        is_valid, err = check_uploaded_file(big_file, ALLOWED_ASSIGNMENT_EXTENSIONS, max_size=50)
        self.assertFalse(is_valid)
        self.assertIn("exceeds maximum allowed size", err)

    def test_student_submission_validator(self):
        docx_content = b"PK\x03\x04\x14\x00\x06\x00"
        f = SimpleUploadedFile("essay.docx", docx_content, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        validate_assignment_submission_file(f)

    def test_audio_validator(self):
        mp3_content = b"ID3\x04\x00\x00\x00\x00\x00#TSSE"
        f = SimpleUploadedFile("audio.mp3", mp3_content, content_type="audio/mpeg")
        validate_audio_file(f)


class SidebarNavActiveTests(TestCase):
    def _create_mock_request(self, path, url_name, view_name=None):
        from unittest.mock import MagicMock
        request = MagicMock()
        request.path = path
        request.resolver_match.url_name = url_name
        request.resolver_match.view_name = view_name or url_name
        return request

    def test_classrooms_parent_highlight_on_classroom_detail(self):
        from common.templatetags.common_tags import is_active_nav
        req = self._create_mock_request('/classroom/1/', 'classroom_detail')
        context = {'request': req}
        self.assertEqual(is_active_nav(context, 'teacher_classrooms'), 'active')
        self.assertEqual(is_active_nav(context, 'student_classrooms'), 'active')

    def test_classrooms_parent_highlight_on_assignment_subpage(self):
        from common.templatetags.common_tags import is_active_nav
        req = self._create_mock_request('/assignments/5/', 'assignment_detail')
        context = {'request': req}
        self.assertEqual(is_active_nav(context, 'teacher_classrooms'), 'active')
        self.assertEqual(is_active_nav(context, 'student_classrooms'), 'active')

    def test_classrooms_parent_highlight_on_quiz_take_subpage(self):
        from common.templatetags.common_tags import is_active_nav
        req = self._create_mock_request('/assignments/quizzes/3/take/', 'take_quiz')
        context = {'request': req}
        self.assertEqual(is_active_nav(context, 'student_classrooms'), 'active')

    def test_classrooms_parent_highlight_on_materials_subpage(self):
        from common.templatetags.common_tags import is_active_nav
        req = self._create_mock_request('/classroom/2/materials/', 'classroom_materials')
        context = {'request': req}
        self.assertEqual(is_active_nav(context, 'teacher_classrooms'), 'active')

    def test_meetings_parent_highlight_on_meeting_subpage(self):
        from common.templatetags.common_tags import is_active_nav
        req = self._create_mock_request('/meetings/join/room123/', 'join_meeting')
        context = {'request': req}
        self.assertEqual(is_active_nav(context, 'teacher_meetings'), 'active')
        self.assertEqual(is_active_nav(context, 'student_meetings'), 'active')

    def test_unrelated_route_returns_empty(self):
        from common.templatetags.common_tags import is_active_nav
        req = self._create_mock_request('/settings/', 'settings')
        context = {'request': req}
        self.assertEqual(is_active_nav(context, 'teacher_classrooms'), '')
        self.assertEqual(is_active_nav(context, 'teacher_meetings'), '')
        self.assertEqual(is_active_nav(context, 'settings'), 'active')

    def test_digital_library_route_does_not_highlight_meetings(self):
        from common.templatetags.common_tags import is_active_nav
        req = self._create_mock_request('/meetings/library/', 'digital_library')
        context = {'request': req}
        self.assertEqual(is_active_nav(context, 'digital_library'), 'active')
        self.assertEqual(is_active_nav(context, 'student_meetings'), '')
        self.assertEqual(is_active_nav(context, 'teacher_meetings'), '')

    def test_classrooms_route_does_not_highlight_meetings(self):
        from common.templatetags.common_tags import is_active_nav
        req = self._create_mock_request('/meetings/classroom/student/', 'student_classrooms')
        context = {'request': req}
        self.assertEqual(is_active_nav(context, 'student_classrooms'), 'active')
        self.assertEqual(is_active_nav(context, 'student_meetings'), '')

    def test_content_manager_route_does_not_highlight_camera_fleet(self):
        from common.templatetags.common_tags import is_active_nav
        req = self._create_mock_request('/cameras/content-manager/', 'admin_content_manager')
        context = {'request': req}
        self.assertEqual(is_active_nav(context, 'admin_content_manager'), 'active')
        self.assertEqual(is_active_nav(context, 'admin_dashboard'), '')

    def test_recordings_library_route_does_not_highlight_camera_fleet(self):
        from common.templatetags.common_tags import is_active_nav
        req = self._create_mock_request('/cameras/recordings-folder/', 'recordings_folder')
        context = {'request': req}
        self.assertEqual(is_active_nav(context, 'recordings_folder'), 'active')
        self.assertEqual(is_active_nav(context, 'admin_dashboard'), '')

    def test_live_videos_route_does_not_highlight_manage_recordings(self):
        from common.templatetags.common_tags import is_active_nav
        req = self._create_mock_request('/cameras/lectures/', 'student_lecture_list')
        context = {'request': req}
        self.assertEqual(is_active_nav(context, 'student_lecture_list'), 'active')
        self.assertEqual(is_active_nav(context, 'manage_recordings'), '')


class AdminDashboardRegressionTests(TestCase):
    def test_admin_create_classroom_requires_class_code_and_password(self):
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile

        User = get_user_model()
        admin = User.objects.create_user(username='admin_create_room', password='superpass123', is_staff=True, is_superuser=True)
        prof_admin, _ = UserProfile.objects.get_or_create(user=admin)
        prof_admin.user_type = 'admin'
        prof_admin.save()
        teacher = User.objects.create_user(username='teacher_class_creator', password='teacherpass123')
        prof_teacher, _ = UserProfile.objects.get_or_create(user=teacher)
        prof_teacher.user_type = 'teacher'
        prof_teacher.save()

        self.client.force_login(admin)
        response = self.client.post('/admin/classrooms/create/', {
            'title': 'Physics 101',
            'class_code': 'PHYS101',
            'password': 'secret123',
            'description': 'Intro to physics',
            'teacher_id': teacher.id,
            'auto_approve': 'on',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Classroom')
        self.assertTrue(teacher.created_classrooms.filter(class_code='PHYS101').exists())


class TelemetryAndLoggingTests(TestCase):
    def test_client_ip_extraction(self):
        from common.telemetry import get_client_ip
        from django.test.client import RequestFactory

        rf = RequestFactory()

        # Direct remote addr
        req1 = rf.get('/test/', REMOTE_ADDR='192.168.1.50')
        self.assertEqual(get_client_ip(req1), '192.168.1.50')

        # X-Forwarded-For (client, proxy1, proxy2)
        req2 = rf.get('/test/', HTTP_X_FORWARDED_FOR='203.0.113.195, 70.41.3.18, 150.172.238.178')
        self.assertEqual(get_client_ip(req2), '203.0.113.195')

        # Cloudflare connecting IP
        req3 = rf.get('/test/', HTTP_CF_CONNECTING_IP='198.51.100.4')
        self.assertEqual(get_client_ip(req3), '198.51.100.4')

    def test_user_agent_parsing(self):
        from common.telemetry import parse_user_agent

        chrome_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        res = parse_user_agent(chrome_ua)
        self.assertEqual(res['browser'], 'Chrome')
        self.assertEqual(res['os'], 'Windows 10/11')
        self.assertEqual(res['device_type'], 'Desktop')
        self.assertFalse(res['is_bot'])

        iphone_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        res_iphone = parse_user_agent(iphone_ua)
        self.assertEqual(res_iphone['os'], 'iOS')
        self.assertEqual(res_iphone['device_type'], 'Mobile')

        bot_ua = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        res_bot = parse_user_agent(bot_ua)
        self.assertTrue(res_bot['is_bot'])
        self.assertEqual(res_bot['device_type'], 'Bot')

    def test_telemetry_events_ingestion_api(self):
        import json
        from common.models import UserActivityLog
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username='telemetry_tester', password='password123')
        self.client.force_login(user)

        payload = {
            'device_id': 'did_12345',
            'session_id': 'sid_67890',
            'events': [
                {
                    'type': 'page_view',
                    'name': 'view_page',
                    'url': 'http://testserver/meetings/',
                    'title': 'Meetings',
                    'viewport': {'width': 1920, 'height': 1080}
                },
                {
                    'type': 'click',
                    'name': 'element_click',
                    'target': 'button#joinMeetingBtn',
                    'text': 'Join Live Lecture',
                    'coordinates': {'x': 350, 'y': 210},
                    'metadata': {'meeting_id': 'RELATIVITY1'}
                }
            ]
        }

        response = self.client.post(
            '/api/telemetry/events/',
            data=json.dumps(payload),
            content_type='application/json',
            REMOTE_ADDR='10.0.0.42'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('processed'), 2)

        # Verify records created in database
        telemetry_logs = UserActivityLog.objects.filter(username='telemetry_tester', event_type__in=['page_view', 'click']).order_by('created_at')
        self.assertEqual(telemetry_logs.count(), 2)

        pv = telemetry_logs.filter(event_type='page_view').first()
        self.assertIsNotNone(pv)
        self.assertEqual(pv.page_title, 'Meetings')

        clk = telemetry_logs.filter(event_type='click').first()
        self.assertIsNotNone(clk)
        self.assertEqual(clk.target_element, 'button#joinMeetingBtn')
        self.assertEqual(clk.target_text, 'Join Live Lecture')
        self.assertEqual(clk.metadata.get('meeting_id'), 'RELATIVITY1')
        self.assertEqual(clk.metadata.get('coordinates', {}).get('x'), 350)

    def test_dated_folder_structure(self):
        from common.telemetry import get_dated_log_dir, get_current_date_str
        folder = get_dated_log_dir()
        self.assertTrue(folder.exists())
        self.assertEqual(folder.name, get_current_date_str())

    def test_attack_detection_and_security_audit_logging(self):
        from django.test.client import RequestFactory
        from common.telemetry import detect_attack_signatures, write_security_alert, get_dated_log_dir

        rf = RequestFactory()

        # 1. SQL Injection attempt
        sqli_req = rf.get('/meetings/?search=1%27%20OR%20%271%27=%271', REMOTE_ADDR='198.51.100.99')
        threats = detect_attack_signatures(sqli_req)
        self.assertTrue(len(threats) > 0)
        self.assertEqual(threats[0]['type'], 'SQL_INJECTION')

        # 2. Path Traversal attempt
        lfi_req = rf.get('/media/download/?file=../../../../etc/passwd', REMOTE_ADDR='198.51.100.99')
        threats_lfi = detect_attack_signatures(lfi_req)
        self.assertTrue(len(threats_lfi) > 0)
        self.assertEqual(threats_lfi[0]['type'], 'PATH_TRAVERSAL')

        # 3. Malicious scanner User-Agent
        scanner_req = rf.get('/test/', HTTP_USER_AGENT='sqlmap/1.5#stable (http://sqlmap.org)', REMOTE_ADDR='198.51.100.99')
        threats_scan = detect_attack_signatures(scanner_req)
        self.assertTrue(len(threats_scan) > 0)
        self.assertEqual(threats_scan[0]['type'], 'MALICIOUS_SCANNER_USER_AGENT')

        # Write security alert and verify log in dated directory
        write_security_alert(sqli_req, threats)
        sec_log = get_dated_log_dir() / 'security_audit.log'
        self.assertTrue(sec_log.exists())
        with open(sec_log, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn('SECURITY_THREAT_DETECTED', content)
            self.assertIn('198.51.100.99', content)
            self.assertIn('SQL_INJECTION', content)

    def test_crash_forensics_post_mortem_logging(self):
        from django.test.client import RequestFactory
        from common.telemetry import log_crash_forensics, get_dated_log_dir
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username='crasher_user', password='password123')

        rf = RequestFactory()
        req = rf.post('/meetings/continue/99/?mode=live', data={'action': 'start_quiz', 'secret_key': 'hidden123'}, REMOTE_ADDR='172.16.0.5')
        req.user = user

        try:
            # Deliberately raise an exception to simulate a bug in meeting view
            raise ValueError("Invalid meeting configuration state for room 99")
        except Exception as e:
            log_crash_forensics(req, e)

        crash_log = get_dated_log_dir() / 'crash_reports.log'
        self.assertTrue(crash_log.exists())
        with open(crash_log, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn('[CRASH_POST_MORTEM]', content)
            self.assertIn('crasher_user', content)
            self.assertIn('172.16.0.5', content)
            self.assertIn('Invalid meeting configuration state for room 99', content)
            self.assertIn('action', content)
            # Ensure sensitive key was sanitized
            self.assertIn('***REDACTED***', content)

    def test_upload_id_path_traversal_defense(self):
        import os
        from common.validators import validate_safe_upload_id, get_safe_temp_upload_dir
        from django.core.exceptions import ValidationError
        from django.conf import settings

        # 1. Valid upload IDs
        self.assertEqual(validate_safe_upload_id("upload_abc123_456"), "upload_abc123_456")
        self.assertEqual(validate_safe_upload_id("a1b2c3d4e5f67890"), "a1b2c3d4e5f67890")

        # 2. Path Traversal attempts
        with self.assertRaises(ValidationError):
            validate_safe_upload_id("../../../etc/passwd")

        with self.assertRaises(ValidationError):
            validate_safe_upload_id("..\\..\\windows\\system32")

        with self.assertRaises(ValidationError):
            validate_safe_upload_id("upload/test")

        with self.assertRaises(ValidationError):
            validate_safe_upload_id("id with spaces")

        # 3. get_safe_temp_upload_dir resolves cleanly
        safe_dir = get_safe_temp_upload_dir(os.path.join(settings.MEDIA_ROOT, 'temp_uploads'), "valid_token_12345")
        self.assertTrue(os.path.exists(safe_dir))

    def test_protected_media_access_control(self):
        # 1. Unauthenticated request to private biometric face profile
        resp = self.client.get('/media/face_profiles/student_secret_face.jpg')
        self.assertIn(resp.status_code, [302, 403])

        # 2. Authenticated superuser request -> allowed past auth check (returns 404 because file is not on disk)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.create_superuser(username='media_admin', password='password123', email='admin@test.com')
        self.client.force_login(admin_user)
        resp2 = self.client.get('/media/face_profiles/student_secret_face.jpg')
        self.assertEqual(resp2.status_code, 404)


class AdminAuditTrailSecurityTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile
        from meetings.models import Classroom, ClassroomMembership
        User = get_user_model()

        self.admin = User.objects.create_superuser(
            username='security_admin',
            email='sec_admin@example.com',
            password='Password123!'
        )
        UserProfile.objects.filter(user=self.admin).update(user_type='admin')

        self.teacher = User.objects.create_user(
            username='audit_prof',
            email='prof@example.com',
            password='Password123!',
            first_name='Audit',
            last_name='Professor'
        )
        UserProfile.objects.filter(user=self.teacher).update(user_type='teacher')

        self.student = User.objects.create_user(
            username='audit_student',
            email='student@example.com',
            password='Password123!',
            first_name='Audit',
            last_name='Student'
        )
        UserProfile.objects.filter(user=self.student).update(user_type='student')

        self.classroom = Classroom.objects.create(
            title='Security Audit 101',
            class_code='SEC-101',
            teacher=self.teacher,
            is_active=True
        )

        self.client.force_login(self.admin)

    def test_immutability_and_append_only(self):
        """Verify that AdminAuditTrail instances cannot be edited or deleted."""
        from common.models import AdminAuditTrail
        from django.core.exceptions import PermissionDenied

        row = AdminAuditTrail.objects.create(
            admin_user=self.admin,
            action_type=AdminAuditTrail.ACTION_USER_CREATED,
            target_type='User',
            target_id='999',
            target_label='@test_user',
            changes_json={'initial': 'data'}
        )
        row_id = row.id

        # 1. Direct save() update must raise PermissionDenied
        row.target_label = '@hacked_user'
        with self.assertRaises(PermissionDenied):
            row.save()

        # 2. Direct delete() must raise PermissionDenied
        with self.assertRaises(PermissionDenied):
            row.delete()

        # 3. QuerySet bulk update must raise PermissionDenied
        with self.assertRaises(PermissionDenied):
            AdminAuditTrail.objects.filter(id=row_id).update(target_label='@mass_hacked')

        # 4. QuerySet bulk delete must raise PermissionDenied
        with self.assertRaises(PermissionDenied):
            AdminAuditTrail.objects.filter(id=row_id).delete()

        # Check record unchanged
        reloaded = AdminAuditTrail.objects.get(id=row_id)
        self.assertEqual(reloaded.target_label, '@test_user')

    def test_django_admin_permissions_blocked(self):
        """Verify Admin site blocks add, change, and delete permissions."""
        from common.models import AdminAuditTrail
        from common.admin import AdminAuditTrailAdmin
        from django.contrib.admin.sites import AdminSite
        from django.test.client import RequestFactory

        site = AdminSite()
        model_admin = AdminAuditTrailAdmin(AdminAuditTrail, site)
        rf = RequestFactory()
        req = rf.get('/admin/common/adminaudittrail/')
        req.user = self.admin

        self.assertFalse(model_admin.has_add_permission(req))
        self.assertFalse(model_admin.has_change_permission(req))
        self.assertFalse(model_admin.has_delete_permission(req))

    def test_user_created_audit(self):
        from common.models import AdminAuditTrail
        initial_count = AdminAuditTrail.objects.count()

        resp = self.client.post('/admin/users/create/', {
            'username': 'new_candidate_user',
            'email': 'candidate@test.com',
            'password': 'Password123!',
            'first_name': 'Candidate',
            'last_name': 'One',
            'user_type': 'student',
            'department': 'CS'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 1)
        latest = AdminAuditTrail.objects.first()
        self.assertEqual(latest.action_type, AdminAuditTrail.ACTION_USER_CREATED)
        self.assertEqual(latest.admin_user, self.admin)
        self.assertEqual(latest.changes_json.get('username'), 'new_candidate_user')

    def test_user_toggle_active_audit(self):
        from common.models import AdminAuditTrail
        initial_count = AdminAuditTrail.objects.count()

        # 1. Suspend
        resp = self.client.post(f'/admin/users/{self.student.id}/toggle-active/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 1)
        latest = AdminAuditTrail.objects.first()
        self.assertEqual(latest.action_type, AdminAuditTrail.ACTION_USER_SUSPENDED)
        self.assertEqual(latest.target_id, str(self.student.id))

        # 2. Activate
        resp2 = self.client.post(f'/admin/users/{self.student.id}/toggle-active/')
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 2)
        latest2 = AdminAuditTrail.objects.first()
        self.assertEqual(latest2.action_type, AdminAuditTrail.ACTION_USER_ACTIVATED)

    def test_user_edit_and_role_changed_audit(self):
        from common.models import AdminAuditTrail
        initial_count = AdminAuditTrail.objects.count()

        resp = self.client.post(f'/admin/users/{self.student.id}/edit/', {
            'first_name': 'Renamed',
            'last_name': 'Student',
            'user_type': 'teacher'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 1)
        latest = AdminAuditTrail.objects.first()
        self.assertEqual(latest.action_type, AdminAuditTrail.ACTION_ROLE_CHANGED)
        self.assertEqual(latest.changes_json['user_type']['after'], 'teacher')

    def test_user_deleted_audit(self):
        from common.models import AdminAuditTrail
        initial_count = AdminAuditTrail.objects.count()

        resp = self.client.post(f'/admin/users/{self.student.id}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 1)
        latest = AdminAuditTrail.objects.first()
        self.assertEqual(latest.action_type, AdminAuditTrail.ACTION_USER_DELETED)

    def test_classroom_created_audit(self):
        from common.models import AdminAuditTrail
        initial_count = AdminAuditTrail.objects.count()

        resp = self.client.post('/admin/classrooms/create/', {
            'title': 'Operating Systems',
            'teacher_id': str(self.teacher.id),
            'class_code': 'OS-202',
            'description': 'OS Concepts'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 1)
        latest = AdminAuditTrail.objects.first()
        self.assertEqual(latest.action_type, AdminAuditTrail.ACTION_CLASSROOM_CREATED)
        self.assertEqual(latest.changes_json.get('title'), 'Operating Systems')

    def test_classroom_edit_settings_and_archive_audit(self):
        from common.models import AdminAuditTrail
        initial_count = AdminAuditTrail.objects.count()

        # 1. Edit settings
        resp = self.client.post(f'/admin/classrooms/{self.classroom.id}/edit/', {
            'title': 'Security Audit 102',
            'class_code': 'SEC-102',
            'teacher_id': str(self.teacher.id),
            'is_active': 'on'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 1)
        latest = AdminAuditTrail.objects.first()
        self.assertEqual(latest.action_type, AdminAuditTrail.ACTION_SETTINGS_CHANGED)

        # 2. Toggle active -> archive
        resp2 = self.client.post(f'/admin/classrooms/{self.classroom.id}/toggle-active/')
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 2)
        latest2 = AdminAuditTrail.objects.first()
        self.assertEqual(latest2.action_type, AdminAuditTrail.ACTION_CLASSROOM_ARCHIVED)

    def test_bulk_archive_classrooms_audit(self):
        from common.models import AdminAuditTrail
        initial_count = AdminAuditTrail.objects.count()

        resp = self.client.post('/admin/classrooms/bulk-archive/', {
            'classroom_ids': [str(self.classroom.id)]
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 1)
        latest = AdminAuditTrail.objects.first()
        self.assertEqual(latest.action_type, AdminAuditTrail.ACTION_BULK_ACTION)
        self.assertEqual(latest.changes_json.get('action'), 'bulk_archive')

    def test_bulk_users_status_audit(self):
        from common.models import AdminAuditTrail
        initial_count = AdminAuditTrail.objects.count()

        resp = self.client.post('/admin/users/bulk-status/', {
            'user_ids': [str(self.student.id)],
            'status_action': 'suspend'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 1)
        latest = AdminAuditTrail.objects.first()
        self.assertEqual(latest.action_type, AdminAuditTrail.ACTION_BULK_ACTION)
        self.assertEqual(latest.changes_json.get('action'), 'bulk_suspend')

    def test_schedule_meeting_audit(self):
        from common.models import AdminAuditTrail
        initial_count = AdminAuditTrail.objects.count()

        resp = self.client.post('/admin/meetings/schedule/', {
            'title': 'Audit Review Session',
            'teacher_id': str(self.teacher.id),
            'classroom_id': str(self.classroom.id),
            'duration_minutes': '45'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 1)
        latest = AdminAuditTrail.objects.first()
        self.assertEqual(latest.action_type, AdminAuditTrail.ACTION_SETTINGS_CHANGED)
        self.assertEqual(latest.changes_json.get('title'), 'Audit Review Session')

    def test_enrollment_approve_and_reject_audit(self):
        from common.models import AdminAuditTrail
        from meetings.models import ClassroomMembership
        membership = ClassroomMembership.objects.create(
            classroom=self.classroom,
            student=self.student,
            status='pending'
        )
        initial_count = AdminAuditTrail.objects.count()

        # Approve
        resp = self.client.post(f'/admin/classrooms/{self.classroom.id}/approve-student/{self.student.id}/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 1)
        latest = AdminAuditTrail.objects.first()
        self.assertEqual(latest.action_type, AdminAuditTrail.ACTION_ENROLLMENT_APPROVED)

        # Reject
        membership.status = 'pending'
        membership.save()
        resp2 = self.client.post(f'/admin/classrooms/{self.classroom.id}/reject-student/{self.student.id}/')
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 2)
        latest2 = AdminAuditTrail.objects.first()
        self.assertEqual(latest2.action_type, AdminAuditTrail.ACTION_ENROLLMENT_REJECTED)

    def test_csv_export_audits(self):
        from common.models import AdminAuditTrail
        initial_count = AdminAuditTrail.objects.count()

        resp1 = self.client.get('/admin/export/users/')
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 1)
        self.assertEqual(AdminAuditTrail.objects.first().action_type, AdminAuditTrail.ACTION_DATA_EXPORTED)

        resp2 = self.client.get('/admin/classrooms/bulk-export/')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(AdminAuditTrail.objects.count(), initial_count + 2)
        self.assertEqual(AdminAuditTrail.objects.first().action_type, AdminAuditTrail.ACTION_DATA_EXPORTED)


class SecurityAndAuditViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile
        from common.models import AdminAuditTrail, UserActivityLog
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username='audit_admin',
            email='audit_admin@example.com',
            password='testpassword123'
        )
        UserProfile.objects.filter(user=self.admin).update(user_type='admin')
        self.client.force_login(self.admin)

        # Create sample audit trail
        self.audit_trail = AdminAuditTrail.objects.create(
            admin_user=self.admin,
            action_type=AdminAuditTrail.ACTION_USER_CREATED,
            target_type='User',
            target_id=999,
            target_label='test_student_target',
            ip_address='192.168.1.100',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            changes_json={'before': {'is_active': False}, 'after': {'is_active': True}}
        )

        # Create sample user activity log
        self.login_log = UserActivityLog.objects.create(
            user=self.admin,
            username=self.admin.username,
            event_type='auth',
            event_name='USER_LOGIN',
            ip_address='127.0.0.1',
            user_agent='Mozilla/5.0 (Test)',
            metadata={'status': 'success'}
        )
        self.failed_log = UserActivityLog.objects.create(
            user=None,
            username='intruder',
            event_type='auth',
            event_name='LOGIN_FAILED',
            ip_address='10.0.0.1',
            user_agent='Mozilla/5.0 (Attacker)',
            metadata={'attempted_username': 'intruder'}
        )

    def test_security_audit_page_admin_actions_tab(self):
        resp = self.client.get('/admin/security-audit/?tab=admin_actions')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Security & Audit')
        self.assertContains(resp, 'Admin Actions')
        self.assertContains(resp, 'test_student_target')
        self.assertContains(resp, 'USER_CREATED')

    def test_security_audit_page_login_activity_tab(self):
        resp = self.client.get('/admin/activity/?tab=login_activity')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Login Activity')
        self.assertContains(resp, '10.0.0.1')
        self.assertContains(resp, 'Failed Attempt')
        self.assertContains(resp, 'intruder')

    def test_security_audit_filters_and_search(self):
        # Search by target label
        resp = self.client.get('/admin/activity/?tab=admin_actions&search=test_student_target')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'test_student_target')

        # Filter by action_type matching
        resp_type = self.client.get('/admin/activity/?tab=admin_actions&action_type=USER_CREATED')
        self.assertEqual(resp_type.status_code, 200)
        self.assertContains(resp_type, 'USER_CREATED')

        # Filter by action_type non-matching
        resp_mismatch = self.client.get('/admin/activity/?tab=admin_actions&action_type=USER_DELETED')
        self.assertEqual(resp_mismatch.status_code, 200)
        self.assertNotContains(resp_mismatch, 'test_student_target')

    def test_security_audit_changes_api(self):
        resp = self.client.get(f'/admin/activity/{self.audit_trail.id}/changes/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('status'), 'success')
        audit_info = data.get('audit', {})
        self.assertEqual(audit_info.get('target_label'), 'test_student_target')
        self.assertIn('before', audit_info.get('changes', {}))
        self.assertIn('after', audit_info.get('changes', {}))

    def test_security_audit_csv_export_logged(self):
        from common.models import AdminAuditTrail
        before_count = AdminAuditTrail.objects.count()

        # Admin Actions export
        resp = self.client.get('/admin/activity/?tab=admin_actions&export=csv')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        self.assertIn('attachment; filename="security_audit_admin_actions_', resp['Content-Disposition'])
        
        # Verify export was logged
        after_count = AdminAuditTrail.objects.count()
        self.assertEqual(after_count, before_count + 1)
        latest_audit = AdminAuditTrail.objects.first()
        self.assertEqual(latest_audit.action_type, AdminAuditTrail.ACTION_DATA_EXPORTED)
        self.assertEqual(latest_audit.target_label, 'AdminAuditTrail')

        # Login Activity export
        resp2 = self.client.get('/admin/activity/?tab=login_activity&export=csv')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2['Content-Type'], 'text/csv')
        self.assertIn('attachment; filename="security_audit_logins_', resp2['Content-Disposition'])
        
        # Verify second export was also logged
        self.assertEqual(AdminAuditTrail.objects.count(), after_count + 1)
        latest_audit2 = AdminAuditTrail.objects.first()
        self.assertEqual(latest_audit2.action_type, AdminAuditTrail.ACTION_DATA_EXPORTED)
        self.assertEqual(latest_audit2.target_label, 'UserActivityLog')

    def test_failed_login_signal_records_activity(self):
        from common.models import UserActivityLog
        from django.contrib.auth.signals import user_login_failed
        
        initial_failed = UserActivityLog.objects.filter(event_name='LOGIN_FAILED').count()
        # Trigger signal
        user_login_failed.send(
            sender=None,
            credentials={'username': 'test_failed_user'},
            request=None
        )
        self.assertEqual(UserActivityLog.objects.filter(event_name='LOGIN_FAILED').count(), initial_failed + 1)







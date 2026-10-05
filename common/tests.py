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
        UserProfile.objects.get_or_create(user=admin, defaults={'user_type': 'admin'})
        teacher = User.objects.create_user(username='teacher_class_creator', password='teacherpass123')
        UserProfile.objects.get_or_create(user=teacher, defaults={'user_type': 'teacher'})

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





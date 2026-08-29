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



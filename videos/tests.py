from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from videos.models import Video

User = get_user_model()


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.db')
class VideoUploadValidationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(username='teacher_vid', password='password123')
        self.teacher.userprofile.user_type = 'teacher'
        self.teacher.userprofile.save()

    def test_upload_disallowed_video_extension_fails(self):
        self.client.login(username='teacher_vid', password='password123')
        bad_file = SimpleUploadedFile("malware.exe", b"MZ\x90\x00", content_type="application/x-msdownload")

        response = self.client.post(
            "/videos/upload/",
            {
                'title': 'Test Video',
                'video': bad_file
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Video.objects.count(), 0)

    def test_upload_valid_video_succeeds(self):
        self.client.login(username='teacher_vid', password='password123')
        valid_video = SimpleUploadedFile("lecture.mp4", b"\x00\x00\x00 ftypisom", content_type="video/mp4")
        valid_thumb = SimpleUploadedFile("thumb.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF", content_type="image/jpeg")

        response = self.client.post(
            "/videos/upload/",
            {
                'title': 'Lecture 1',
                'description': 'Introduction',
                'video': valid_video,
                'thumbnail': valid_thumb
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Video.objects.count(), 1)
        video = Video.objects.first()
        self.assertEqual(video.title, 'Lecture 1')

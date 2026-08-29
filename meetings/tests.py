from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from meetings.models import Meeting, Classroom

User = get_user_model()


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.db')
class MeetingParticipantIdentityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username='teacher_host',
            password='password123',
            first_name='Albert',
            last_name='Einstein'
        )
        self.teacher_profile = self.teacher.userprofile
        self.teacher_profile.user_type = 'teacher'
        self.teacher_profile.display_name = 'Prof. Einstein'
        self.teacher_profile.avatar_url = 'https://example.com/einstein.png'
        self.teacher_profile.save()

        self.classroom = Classroom.objects.create(
            title='Physics 101',
            teacher=self.teacher,
            class_code='PHYS101'
        )

        self.meeting = Meeting.objects.create(
            classroom=self.classroom,
            teacher=self.teacher,
            title='Relativity Lecture',
            meeting_code='RELATIVITY1',
            scheduled_time=timezone.now(),
            status='live'
        )

    def test_livekit_token_contains_updated_display_name_and_avatar(self):
        self.client.login(username='teacher_host', password='password123')
        response = self.client.get(f'/meetings/token/{self.meeting.meeting_code}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('token', data)

    def test_join_meeting_context_contains_display_name_and_pfp(self):
        self.client.login(username='teacher_host', password='password123')
        response = self.client.get(f'/meetings/join/{self.meeting.meeting_code}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('display_name', response.context)
        self.assertEqual(response.context['display_name'], 'Prof. Einstein')
        self.assertEqual(response.context['pfp_url'], 'https://example.com/einstein.png')


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.db')
class MeetingTimeLimitLifecycleTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(username='teacher1', password='password123')
        self.teacher.userprofile.user_type = 'teacher'
        self.teacher.userprofile.save()

        self.student = User.objects.create_user(username='student1', password='password123')
        self.student.userprofile.user_type = 'student'
        self.student.userprofile.save()

        self.classroom = Classroom.objects.create(
            title='Math 101', teacher=self.teacher, class_code='MATH101'
        )

        # Scheduled 2 hours ago with 60 min duration (already expired)
        self.expired_time = timezone.now() - timezone.timedelta(hours=2)
        self.meeting = Meeting.objects.create(
            classroom=self.classroom,
            teacher=self.teacher,
            title='Algebra Class',
            meeting_code='ALGEBRA101',
            scheduled_time=self.expired_time,
            started_at=self.expired_time,
            duration_minutes=60,
            status='live'
        )

    def test_is_expired_helper(self):
        self.assertTrue(self.meeting.is_expired())

        # Future meeting
        future_meeting = Meeting.objects.create(
            classroom=self.classroom,
            teacher=self.teacher,
            title='Calculus Class',
            meeting_code='CALC101',
            scheduled_time=timezone.now(),
            started_at=timezone.now(),
            duration_minutes=60,
            status='live'
        )
        self.assertFalse(future_meeting.is_expired())

    def test_expired_meeting_teacher_absent_auto_ends(self):
        from meetings.services import check_and_process_meeting_expiration
        processed, action = check_and_process_meeting_expiration(self.meeting)
        self.assertTrue(processed)
        self.assertEqual(action, 'ended')
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, 'ended')
        self.assertIsNotNone(self.meeting.ended_at)

    def test_expired_meeting_teacher_present_prompts_continuation(self):
        from meetings.models import MeetingParticipant
        from meetings.services import check_and_process_meeting_expiration
        MeetingParticipant.objects.create(meeting=self.meeting, user=self.teacher, is_active=True)

        processed, action = check_and_process_meeting_expiration(self.meeting)
        self.assertTrue(processed)
        self.assertEqual(action, 'prompt_sent')
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, 'live')  # Still live

    def test_teacher_continues_meeting_view(self):
        from meetings.models import MeetingParticipant
        MeetingParticipant.objects.create(meeting=self.meeting, user=self.teacher, is_active=True)

        self.client.login(username='teacher1', password='password123')
        response = self.client.post(f'/meetings/continue/{self.meeting.id}/')
        self.assertEqual(response.status_code, 200)
        self.meeting.refresh_from_db()
        self.assertTrue(self.meeting.is_extended)

    def test_teacher_leaves_after_continuation_auto_ends(self):
        from meetings.models import MeetingParticipant
        from meetings.services import check_and_process_meeting_expiration
        tp = MeetingParticipant.objects.create(meeting=self.meeting, user=self.teacher, is_active=True)
        self.meeting.is_extended = True
        self.meeting.save()

        # Teacher leaves -> is_active becomes False
        tp.is_active = False
        tp.save()

        processed, action = check_and_process_meeting_expiration(self.meeting)
        self.assertTrue(processed)
        self.assertEqual(action, 'ended')
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, 'ended')

    def test_periodic_task_ends_expired_meetings(self):
        from meetings.tasks import check_expired_meetings_task
        res = check_expired_meetings_task()
        self.assertIn('Processed expiration check for 1 meeting(s)', res)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, 'ended')


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.db')
class MeetingRecordingUploadTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(username='teacher_rec', password='password123')
        self.teacher.userprofile.user_type = 'teacher'
        self.teacher.userprofile.save()

        self.meeting = Meeting.objects.create(
            teacher=self.teacher,
            title='Recorded Physics Class',
            meeting_code='RECPHYS101',
            scheduled_time=timezone.now(),
            status='live'
        )

    def test_meeting_chunked_upload_single_chunk_mkv(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from cameras.models import CameraRecording

        self.client.login(username='teacher_rec', password='password123')
        dummy_ebml_header = b'\x1a\x45\xdf\xa3' + b'\x00' * 512
        uploaded_chunk = SimpleUploadedFile("chunk_0.tmp", dummy_ebml_header, content_type="video/x-matroska")

        response = self.client.post('/meetings/recording/upload/', {
            'chunk': uploaded_chunk,
            'filename': 'lecture_recording.mkv',
            'chunkIndex': '0',
            'totalChunks': '1',
            'uploadId': 'upload_test_123',
            'meeting_id': str(self.meeting.id)
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('recording_id', data)

        rec = CameraRecording.objects.get(id=data['recording_id'])
        self.assertEqual(rec.teacher, self.teacher)
        self.assertTrue(rec.video_file.name.endswith('.mkv'))



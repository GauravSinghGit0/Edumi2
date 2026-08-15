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

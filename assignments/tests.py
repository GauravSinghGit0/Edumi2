from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from datetime import timedelta
from meetings.models import Classroom
from assignments.models import Assignment, AssignmentSubmission, AssignmentSubmissionFile

User = get_user_model()


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.db')
class AssignmentUploadValidationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(username='teacher1', password='password123')
        self.teacher.userprofile.user_type = 'teacher'
        self.teacher.userprofile.save()

        self.student = User.objects.create_user(username='student1', password='password123')
        self.student.userprofile.user_type = 'student'
        self.student.userprofile.save()

        self.classroom = Classroom.objects.create(
            title='Math 101',
            teacher=self.teacher,
            class_code='MATH101'
        )
        self.classroom.memberships.create(student=self.student, status='approved')

    def test_create_assignment_with_disallowed_file_fails(self):
        self.client.login(username='teacher1', password='password123')
        bad_file = SimpleUploadedFile("payload.exe", b"MZ\x90\x00\x03", content_type="application/octet-stream")
        
        response = self.client.post(
            f"/assignments/classroom/{self.classroom.id}/create/",
            {
                'title': 'Homework 1',
                'description': 'Solve exercises',
                'instructions': 'Submit PDF',
                'total_marks': 100,
                'due_date': (timezone.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                'due_time': '23:59',
                'question_files': [bad_file],
                'action': 'publish'
            }
        )
        # Assignment should not be created
        self.assertEqual(Assignment.objects.filter(classroom=self.classroom).count(), 0)

    def test_create_assignment_with_valid_file_succeeds(self):
        self.client.login(username='teacher1', password='password123')
        good_file = SimpleUploadedFile("questions.pdf", b"%PDF-1.4 sample content", content_type="application/pdf")
        
        response = self.client.post(
            f"/assignments/classroom/{self.classroom.id}/create/",
            {
                'title': 'Homework 1',
                'description': 'Solve exercises',
                'instructions': 'Submit PDF',
                'total_marks': 100,
                'due_date': (timezone.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                'due_time': '23:59',
                'question_files': [good_file],
                'action': 'publish'
            }
        )
        self.assertEqual(Assignment.objects.filter(classroom=self.classroom).count(), 1)
        assignment = Assignment.objects.get(classroom=self.classroom)
        self.assertEqual(assignment.question_files.count(), 1)

    def test_submit_assignment_with_disallowed_file_fails(self):
        assignment = Assignment.objects.create(
            classroom=self.classroom,
            title='Homework 1',
            total_marks=100,
            due_date=timezone.now() + timedelta(days=7),
            created_by=self.teacher,
            status='published'
        )
        self.client.login(username='student1', password='password123')
        bad_file = SimpleUploadedFile("shell.sh", b"#!/bin/bash\nrm -rf /", content_type="application/x-sh")
        
        response = self.client.post(
            f"/assignments/{assignment.id}/submit/",
            {
                'submission_files': [bad_file]
            }
        )
        self.assertEqual(AssignmentSubmissionFile.objects.count(), 0)

    def test_submit_assignment_with_valid_pdf_succeeds(self):
        assignment = Assignment.objects.create(
            classroom=self.classroom,
            title='Homework 1',
            total_marks=100,
            due_date=timezone.now() + timedelta(days=7),
            created_by=self.teacher,
            status='published'
        )
        self.client.login(username='student1', password='password123')
        good_file = SimpleUploadedFile("solution.pdf", b"%PDF-1.4 my submission", content_type="application/pdf")
        
        response = self.client.post(
            f"/assignments/{assignment.id}/submit/",
            {
                'submission_files': [good_file]
            }
        )
        self.assertEqual(AssignmentSubmission.objects.filter(assignment=assignment, student=self.student).count(), 1)
        self.assertEqual(AssignmentSubmissionFile.objects.count(), 1)

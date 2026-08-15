from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from meetings.models import Classroom
from common.validators import (
    validate_assignment_file,
    validate_assignment_submission_file,
    validate_image_file,
)

User = get_user_model()


def assignment_question_upload_path(instance, filename):
    """Generate upload path for assignment question files"""
    return f"assignments/{instance.assignment.id}/questions/{filename}"


def assignment_submission_upload_path(instance, filename):
    """Generate upload path for assignment submission files"""
    return f"assignments/{instance.submission.assignment.id}/submissions/{instance.submission.student.username}/{filename}"


class Assignment(models.Model):
    """Model for assignments created by teachers for classrooms"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='assignments')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True)
    total_marks = models.IntegerField(default=100)
    due_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_assignments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-due_date', '-created_at']
        verbose_name = 'Assignment'
        verbose_name_plural = 'Assignments'

    def __str__(self):
        return f"{self.title} ({self.classroom.title})"

    def is_past_due(self):
        """Check if assignment is past due date"""
        return timezone.now() > self.due_date

    def get_submission_status(self, student):
        """Get submission status for a specific student"""
        try:
            submission = self.submissions.get(student=student)
            if submission.submitted_at > self.due_date:
                return 'late'
            return 'submitted'
        except AssignmentSubmission.DoesNotExist:
            if self.is_past_due():
                return 'missing'
            return 'pending'


class AssignmentQuestionFile(models.Model):
    """Model for files attached to assignments (questions, images, PDFs, etc.)"""
    FILE_TYPE_CHOICES = [
        ('file', 'File'),
        ('link', 'Link'),
    ]
    
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='question_files')
    file = models.FileField(upload_to=assignment_question_upload_path, blank=True, null=True, validators=[validate_assignment_file])
    link_url = models.URLField(blank=True, null=True)
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES, default='file')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']

    def __str__(self):
        return f"{self.filename} for {self.assignment.title}"


class AssignmentSubmission(models.Model):
    """Model for student submissions to assignments"""
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('late', 'Late Submission'),
        ('returned', 'Returned'),
    ]

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assignment_submissions')
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    marks_obtained = models.IntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)
    evaluated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='evaluated_submissions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['assignment', 'student']
        ordering = ['-submitted_at']
        verbose_name = 'Assignment Submission'
        verbose_name_plural = 'Assignment Submissions'

    def __str__(self):
        return f"{self.student.username} - {self.assignment.title}"

    def save(self, *args, **kwargs):
        """Set status to late if submitted after due date"""
        if self.submitted_at and self.assignment.due_date:
            if self.submitted_at > self.assignment.due_date:
                self.status = 'late'
            else:
                self.status = 'submitted'
        super().save(*args, **kwargs)


class AssignmentSubmissionFile(models.Model):
    """Model for files submitted by students as part of their assignment"""
    FILE_TYPE_CHOICES = [
        ('file', 'File'),
        ('link', 'Link'),
    ]
    
    submission = models.ForeignKey(AssignmentSubmission, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to=assignment_submission_upload_path, blank=True, null=True, validators=[validate_assignment_submission_file])
    link_url = models.URLField(blank=True, null=True)
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES, default='file')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return f"{self.filename} for {self.submission}"


class Quiz(models.Model):
    """Model for quizzes created by teachers for classrooms"""
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="quizzes")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    total_marks = models.IntegerField(default=100)
    time_limit = models.IntegerField(blank=True, null=True, help_text="Time limit in minutes")
    due_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_quizzes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-due_date", "-created_at"]
        verbose_name = "Quiz"
        verbose_name_plural = "Quizzes"

    def __str__(self):
        return f"{self.title} ({self.classroom.title})"


class Question(models.Model):
    """Model for individual questions in a quiz"""
    QUESTION_TYPE_CHOICES = [
        ("mcq", "Multiple Choice"),
        ("text", "Text Answer"),
    ]

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPE_CHOICES)
    question_text = models.TextField()
    question_image = models.ImageField(upload_to="quizzes/questions/", blank=True, null=True, validators=[validate_image_file])
    marks = models.IntegerField(default=1)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "Question"
        verbose_name_plural = "Questions"

    def __str__(self):
        return f"Q{self.order + 1}: {self.question_text[:50]}"


class Choice(models.Model):
    """Model for choices in multiple-choice questions"""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    choice_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "Choice"
        verbose_name_plural = "Choices"

    def __str__(self):
        return self.choice_text[:50]


class QuizSubmission(models.Model):
    """Model for student submissions to quizzes"""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="quiz_submissions")
    # Timer tracking
    started_at = models.DateTimeField(null=True, blank=True, help_text="When the student opened the quiz")
    submitted_at = models.DateTimeField(auto_now_add=True)
    time_taken_seconds = models.IntegerField(null=True, blank=True, help_text="Seconds taken to complete the quiz")
    # Grading
    marks_obtained = models.IntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)
    evaluated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="evaluated_quizzes")

    class Meta:
        unique_together = ["quiz", "student"]
        ordering = ["-submitted_at"]
        verbose_name = "Quiz Submission"
        verbose_name_plural = "Quiz Submissions"

    def __str__(self):
        return f"{self.student.username} - {self.quiz.title}"

    @property
    def time_taken_display(self):
        """Returns human-readable time taken, e.g. '4m 32s'"""
        if self.time_taken_seconds is None:
            return "—"
        mins, secs = divmod(self.time_taken_seconds, 60)
        if mins:
            return f"{mins}m {secs}s"
        return f"{secs}s"


class StudentAnswer(models.Model):
    """Model for individual student answers in a quiz submission"""
    submission = models.ForeignKey(QuizSubmission, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    text_answer = models.TextField(blank=True)
    selected_choice = models.ForeignKey(Choice, on_delete=models.SET_NULL, null=True, blank=True, related_name="selected_by")
    marks_obtained = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = ["submission", "question"]
        ordering = ["question__order"]
        verbose_name = "Student Answer"
        verbose_name_plural = "Student Answers"

    def __str__(self):
        return f"Answer to Q{self.question.order + 1} by {self.submission.student.username}"

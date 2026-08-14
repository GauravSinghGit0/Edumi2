from django.contrib import admin
from .models import (
    Assignment, AssignmentQuestionFile, AssignmentSubmission, AssignmentSubmissionFile,
    Quiz, Question, Choice, QuizSubmission, StudentAnswer
)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'classroom', 'created_by', 'due_date', 'status', 'total_marks')
    list_filter = ('status', 'classroom', 'created_by', 'due_date')
    search_fields = ('title', 'description', 'instructions')
    date_hierarchy = 'due_date'


@admin.register(AssignmentQuestionFile)
class AssignmentQuestionFileAdmin(admin.ModelAdmin):
    list_display = ('filename', 'assignment', 'file_type', 'uploaded_at')
    list_filter = ('assignment', 'file_type')
    search_fields = ('filename',)


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'student', 'status', 'submitted_at', 'marks_obtained')
    list_filter = ('status', 'assignment', 'student')
    search_fields = ('student__username', 'assignment__title')


@admin.register(AssignmentSubmissionFile)
class AssignmentSubmissionFileAdmin(admin.ModelAdmin):
    list_display = ('filename', 'submission', 'file_type', 'uploaded_at')
    list_filter = ('file_type',)
    search_fields = ('filename',)


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'classroom', 'created_by', 'due_date', 'status', 'total_marks')
    list_filter = ('status', 'classroom', 'created_by', 'due_date')
    search_fields = ('title', 'description')
    date_hierarchy = 'due_date'
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'question_type', 'order', 'marks')
    list_filter = ('quiz', 'question_type')
    search_fields = ('question_text',)
    inlines = [ChoiceInline]


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ('question', 'choice_text', 'is_correct')
    list_filter = ('question', 'is_correct')


@admin.register(QuizSubmission)
class QuizSubmissionAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'student', 'submitted_at', 'marks_obtained')
    list_filter = ('quiz', 'student')
    search_fields = ('student__username', 'quiz__title')


@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = ('submission', 'question', 'marks_obtained')
    list_filter = ('submission', 'question')

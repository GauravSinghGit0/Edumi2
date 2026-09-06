"""
Quiz URL Configuration
"""
from django.urls import path
from assignments.views.quiz_views import (
    classroom_quizzes,
    create_quiz,
    edit_quiz,
    quiz_detail,
    quiz_submissions,
    delete_quiz,
    toggle_quiz_status,
    add_question,
    edit_question,
    delete_question,
    take_quiz,
    quiz_time_status,
    evaluate_quiz_submission,
)


urlpatterns = [
    # Classroom quizzes list
    path('classroom/<int:classroom_id>/', classroom_quizzes, name='classroom_quizzes'),

    # Teacher views
    path('classroom/<int:classroom_id>/create/', create_quiz, name='create_quiz'),
    path('<int:quiz_id>/edit/', edit_quiz, name='edit_quiz'),
    path('<int:quiz_id>/delete/', delete_quiz, name='delete_quiz'),
    path('<int:quiz_id>/toggle-status/', toggle_quiz_status, name='toggle_quiz_status'),
    path('<int:quiz_id>/', quiz_detail, name='quiz_detail'),
    path('<int:quiz_id>/submissions/', quiz_submissions, name='quiz_submissions'),
    path('<int:quiz_id>/add-question/', add_question, name='add_question'),
    path('questions/<int:question_id>/edit/', edit_question, name='edit_question'),
    path('questions/<int:question_id>/delete/', delete_question, name='delete_question'),
    path('submissions/<int:submission_id>/evaluate/', evaluate_quiz_submission, name='evaluate_quiz_submission'),

    # Student views
    path('<int:quiz_id>/take/', take_quiz, name='take_quiz'),
    path('<int:quiz_id>/time-status/', quiz_time_status, name='quiz_time_status'),
]

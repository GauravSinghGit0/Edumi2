"""
Assignment URL Configuration
"""
from django.urls import path
from assignments.views.assignment_views import (
    classroom_assignments,
    create_assignment,
    edit_assignment,
    delete_assignment,
    toggle_assignment_status,
    assignment_detail,
    assignment_submissions,
    submit_assignment,
    evaluate_submission,
    delete_question_file
)


urlpatterns = [
    # Classroom assignments list
    path('classroom/<int:classroom_id>/', classroom_assignments, name='classroom_assignments'),
    
    # Teacher views
    path('classroom/<int:classroom_id>/create/', create_assignment, name='create_assignment'),
    path('<int:assignment_id>/edit/', edit_assignment, name='edit_assignment'),
    path('<int:assignment_id>/delete/', delete_assignment, name='delete_assignment'),
    path('<int:assignment_id>/toggle-status/', toggle_assignment_status, name='toggle_assignment_status'),
    path('<int:assignment_id>/', assignment_detail, name='assignment_detail'),
    path('<int:assignment_id>/submissions/', assignment_submissions, name='assignment_submissions'),
    path('submissions/<int:submission_id>/evaluate/', evaluate_submission, name='evaluate_submission'),
    path('question-files/<int:file_id>/delete/', delete_question_file, name='delete_question_file'),
    
    # Student views
    path('<int:assignment_id>/submit/', submit_assignment, name='submit_assignment'),
]

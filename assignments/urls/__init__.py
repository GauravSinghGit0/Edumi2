"""
Assignments URL Configuration
"""
from django.urls import path, include

urlpatterns = [
    path('', include('assignments.urls.assignment_urls')),
    path('quizzes/', include('assignments.urls.quiz_urls')),
]

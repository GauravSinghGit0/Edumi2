# accounts/urls/profile_urls.py
from django.urls import path
from accounts import views

urlpatterns = [
    path('teacher-dashboard/',          views.teacher_dashboard,  name='teacher_dashboard'),
    path('student-dashboard/',          views.student_dashboard,  name='student_dashboard'),
    path('profile/',                    views.profile_view,        name='profile_view'),
    path('profile/edit/',               views.edit_profile,        name='edit_profile'),   # MUST be before <str:username>/
    path('profile/<str:username>/',     views.profile_view,        name='profile_view'),
    path('profile/<str:username>/',     views.profile_view,        name='user_profile'),
    path('directory/',                  views.directory,           name='directory'),
    path('directory/search/',           views.search_users,        name='search_users'),
]

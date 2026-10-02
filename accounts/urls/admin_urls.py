# accounts/urls/admin_urls.py
from django.urls import path
from django.shortcuts import redirect
from accounts import views
from accounts.views import admin_list_views

urlpatterns = [
    path('admin/dashboard/',                    views.admin_panel,                          name='admin_panel'),
    path('admin/users/',                        views.user_management,                      name='user_management'),
    path('admin/users/<int:user_id>/edit/',     views.admin_edit_user,                      name='admin_edit_user'),
    path('admin/users/<int:user_id>/delete/',   views.delete_user,                          name='delete_user'),
    path('admin/architecture/',                 views.architecture_view,                    name='architecture'),

    # Legacy redirects to prevent 404s
    path('admin-panel/',                        lambda request: redirect('admin_panel', permanent=True)),
    path('user-management/',                    lambda request: redirect('user_management', permanent=True)),
    path('user-management/<int:user_id>/edit/', lambda request, user_id: redirect('admin_edit_user', user_id=user_id, permanent=True)),
    path('delete-user/<int:user_id>/',          lambda request, user_id: redirect('delete_user', user_id=user_id, permanent=True)),
    path('architecture/',                       lambda request: redirect('architecture', permanent=True)),

    # User 360 & status controls
    path('admin/users/<int:user_id>/',                  views.admin_user_detail,            name='admin_user_detail'),
    path('admin/users/<int:user_id>/toggle-active/',     views.admin_toggle_user_active,     name='admin_toggle_user_active'),

    # Teacher Management & Teacher 360
    path('admin/teachers/',                     admin_list_views.admin_all_teachers,        name='admin_all_teachers'),
    path('admin/teachers/<int:teacher_id>/',    views.admin_teacher_detail,                 name='admin_teacher_detail'),

    # Course / Classroom Management & Classroom 360
    path('admin/classrooms/',                   admin_list_views.admin_all_classrooms,      name='admin_all_classrooms'),
    path('admin/classrooms/<int:classroom_id>/',admin_list_views.admin_classroom_detail,   name='admin_classroom_detail'),

    # Classes / Meeting Management & Meeting Detail
    path('admin/meetings/',                     admin_list_views.admin_all_meetings,        name='admin_all_meetings'),
    path('admin/meetings/<int:meeting_id>/',    admin_list_views.admin_meeting_detail,      name='admin_meeting_detail'),
    path('admin/live-meetings/',                admin_list_views.admin_live_meetings,       name='admin_live_meetings'),

    # Aliases
    path('admin/users/all/',                    admin_list_views.admin_all_users,           name='admin_all_users'),
    path('admin/students/',                     admin_list_views.admin_all_students,        name='admin_all_students'),
    path('admin/cameras/',                      admin_list_views.admin_all_cameras,         name='admin_all_cameras'),

    # Action Views
    path('admin/users/create/',                 views.admin_create_user,            name='admin_create_user'),
    path('admin/classrooms/create/',            views.admin_create_classroom,       name='admin_create_classroom'),
    path('admin/meetings/schedule/',            views.admin_schedule_meeting,       name='admin_schedule_meeting'),
    path('admin/classrooms/<int:classroom_id>/approve-student/<int:student_id>/', views.admin_approve_student, name='admin_approve_student'),
    path('admin/classrooms/<int:classroom_id>/reject-student/<int:student_id>/',  views.admin_reject_student,  name='admin_reject_student'),
    path('admin/export/users/',                 views.admin_export_users_csv,       name='admin_export_users_csv'),
    path('admin/activity/',                     views.admin_activity_feed,          name='admin_activity_feed'),
]


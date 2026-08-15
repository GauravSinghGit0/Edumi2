# accounts/urls/admin_urls.py
from django.urls import path
from accounts import views
from accounts import admin_list_views

urlpatterns = [
    path('admin-panel/',                    views.admin_panel,                          name='admin_panel'),
    path('user-management/',                views.user_management,                      name='user_management'),
    path('user-management/<int:user_id>/edit/', views.admin_edit_user,                  name='admin_edit_user'),
    path('delete-user/<int:user_id>/',      views.delete_user,                          name='delete_user'),
    path('architecture/',                   views.architecture_view,                    name='architecture'),

    # Admin list views
    path('admin/users/',                    admin_list_views.admin_all_users,           name='admin_all_users'),
    path('admin/students/',                 admin_list_views.admin_all_students,        name='admin_all_students'),
    path('admin/teachers/',                 admin_list_views.admin_all_teachers,        name='admin_all_teachers'),
    path('admin/meetings/',                 admin_list_views.admin_all_meetings,        name='admin_all_meetings'),
    path('admin/live-meetings/',            admin_list_views.admin_live_meetings,       name='admin_live_meetings'),
    path('admin/cameras/',                  admin_list_views.admin_all_cameras,         name='admin_all_cameras'),
]

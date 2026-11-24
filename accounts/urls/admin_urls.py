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

    # Teacher Management & Teacher 360 (Redirect legacy roster to upgraded directory)
    path('admin/teachers/',                     lambda request: redirect('/admin/users/?tab=teachers', permanent=False), name='admin_all_teachers'),
    path('admin/teachers/roster/',              admin_list_views.admin_all_teachers,        name='admin_all_teachers_roster'),
    path('admin/teachers/<int:teacher_id>/',    views.admin_teacher_detail,                 name='admin_teacher_detail'),

    # Course / Classroom Management & Classroom 360
    path('admin/classrooms/',                   admin_list_views.admin_all_classrooms,      name='admin_all_classrooms'),
    path('admin/classrooms/<int:classroom_id>/',admin_list_views.admin_classroom_detail,   name='admin_classroom_detail'),

    # Classes / Meeting Management & Meeting Detail
    path('admin/meetings/',                     admin_list_views.admin_all_meetings,        name='admin_all_meetings'),
    path('admin/meetings/<int:meeting_id>/',    admin_list_views.admin_meeting_detail,      name='admin_meeting_detail'),
    path('admin/meetings/<int:meeting_id>/export-attendance/', views.admin_export_meeting_attendance_csv, name='admin_export_meeting_attendance_csv'),
    path('admin/meetings/<int:meeting_id>/force-end/', views.admin_force_end_meeting,       name='admin_force_end_meeting'),
    path('admin/live-meetings/',                admin_list_views.admin_live_meetings,       name='admin_live_meetings'),
    path('admin/live-monitor/',                 admin_list_views.admin_live_monitor,        name='admin_live_monitor'),

    # Aliases
    path('admin/users/all/',                    admin_list_views.admin_all_users,           name='admin_all_users'),
    path('admin/students/',                     admin_list_views.admin_all_students,        name='admin_all_students'),
    path('admin/cameras/',                      admin_list_views.admin_all_cameras,         name='admin_all_cameras'),

    # Action Views
    path('admin/users/create/',                 views.admin_create_user,            name='admin_create_user'),
    path('admin/classrooms/create/',            views.admin_create_classroom,       name='admin_create_classroom'),
    path('admin/classrooms/<int:classroom_id>/edit/', views.admin_edit_classroom,   name='admin_edit_classroom'),
    path('admin/classrooms/<int:classroom_id>/toggle-active/', views.admin_toggle_classroom_active, name='admin_toggle_classroom_active'),
    path('admin/classrooms/bulk-archive/',      views.admin_bulk_archive_classrooms, name='admin_bulk_archive_classrooms'),
    path('admin/classrooms/bulk-export/',       views.admin_bulk_export_classrooms,  name='admin_bulk_export_classrooms'),
    path('admin/users/bulk-status/',            views.admin_bulk_users_status,       name='admin_bulk_users_status'),
    path('admin/users/bulk-role/',              views.admin_bulk_change_role,        name='admin_bulk_change_role'),
    path('admin/users/<int:user_id>/reset-password/', views.admin_reset_password_link, name='admin_reset_password_link'),
    path('admin/meetings/schedule/',            views.admin_schedule_meeting,       name='admin_schedule_meeting'),
    path('admin/classrooms/<int:classroom_id>/approve-student/<int:student_id>/', views.admin_approve_student, name='admin_approve_student'),
    path('admin/classrooms/<int:classroom_id>/reject-student/<int:student_id>/',  views.admin_reject_student,  name='admin_reject_student'),
    path('admin/export/users/',                 views.admin_export_users_csv,       name='admin_export_users_csv'),
    path('admin/activity/',                     views.admin_activity_feed,          name='admin_activity_feed'),
    path('admin/security-audit/',               views.admin_activity_feed,          name='admin_security_audit'),
    path('admin/activity/<int:audit_id>/changes/', views.admin_audit_changes_api,   name='admin_audit_changes_api'),
    path('admin/api/dashboard-metrics/',        views.admin_dashboard_metrics_api,  name='admin_dashboard_metrics_api'),
    path('admin/system-health/',                views.admin_system_health,           name='admin_system_health'),
    path('admin/api/system-health/',            views.admin_system_health_api,       name='admin_system_health_api'),

    # Bulk User Importer Wizard Endpoints
    path('admin/users/import/sample-template/', views.admin_user_import_sample_csv, name='admin_user_import_sample_csv'),
    path('admin/users/import/preview/',         views.admin_user_import_preview,    name='admin_user_import_preview'),
    path('admin/users/import/execute/',         views.admin_user_import_execute,    name='admin_user_import_execute'),
    path('admin/api/user-import-progress/<str:task_id>/', views.admin_user_import_progress_api, name='admin_user_import_progress_api'),
    path('admin/api/user-import-failed-csv/<str:task_id>/', views.admin_user_import_failed_csv, name='admin_user_import_failed_csv'),

    # Reports & Analytics Endpoints
    path('admin/reports/',                      views.admin_reports,                name='admin_reports'),
    path('admin/reports/<str:report_type>/csv/', views.admin_export_report_csv,     name='admin_export_report_csv'),
    path('admin/reports/<str:report_type>/pdf/', views.admin_export_report_pdf,     name='admin_export_report_pdf'),

    # Settings & Governance Endpoints
    path('admin/settings/',                     views.admin_settings,               name='admin_settings'),
    path('admin/settings/<str:section>/update/', views.admin_update_settings,       name='admin_update_settings'),
    path('admin/settings/academic/semester/',   views.admin_semester_crud,          name='admin_semester_crud'),
    path('admin/settings/academic/department/', views.admin_department_crud,        name='admin_department_crud'),
    path('admin/settings/test-email/',          views.admin_test_email,             name='admin_test_email'),

    # Approvals Queue Endpoints
    path('admin/approvals/',                     views.admin_approvals,              name='admin_approvals'),
    path('admin/approvals/enrollment/<int:membership_id>/<str:action>/', views.admin_approval_enrollment_action, name='admin_approval_enrollment_action'),
    path('admin/approvals/teacher/<int:user_id>/<str:action>/', views.admin_approval_teacher_action, name='admin_approval_teacher_action'),
    path('admin/approvals/bulk/',                views.admin_approvals_bulk,         name='admin_approvals_bulk'),

    # Campus Announcements Endpoints
    path('admin/announcements/',                 views.admin_announcements,          name='admin_announcements'),
    path('admin/announcements/<int:announcement_id>/send-now/', views.admin_announcement_send_now, name='admin_announcement_send_now'),
    path('admin/announcements/<int:announcement_id>/delete/', views.admin_announcement_delete, name='admin_announcement_delete'),

    # Granular Roles & Permissions Endpoints
    path('admin/roles/',                         views.admin_roles,                  name='admin_roles'),
    path('admin/roles/update/',                  views.admin_role_update,            name='admin_role_update'),
    path('admin/roles/assign-user/',             views.admin_assign_user_role,       name='admin_assign_user_role'),

    # Command Palette (Ctrl+K)
    path('admin/api/command-palette/',           views.admin_command_palette_api,    name='admin_command_palette_api'),
]


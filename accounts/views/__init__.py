# accounts/views/__init__.py
# Re-exports everything for backwards compatibility.
from .auth_views import (
    login_view, register, home, dismiss_welcome, save_emoji_avatar,
    error_404, error_500, settings_view,
    verify_email_sent_view, verify_email, resend_verification_email, check_availability,
    password_reset_request, password_reset_done, password_reset_confirm, password_reset_complete
)
from .profile_views import profile_view, edit_profile, directory, search_users
from .admin_views import (
    admin_panel, user_management, admin_edit_user, delete_user, architecture_view,
    admin_user_detail, admin_toggle_user_active, admin_teacher_detail,
    admin_create_user, admin_create_classroom, admin_schedule_meeting,
    admin_approve_student, admin_reject_student, admin_export_users_csv,
    admin_activity_feed, admin_audit_changes_api, admin_dashboard_metrics_api,
    admin_edit_classroom, admin_toggle_classroom_active,
    admin_bulk_archive_classrooms, admin_bulk_export_classrooms,
    admin_bulk_users_status, admin_bulk_change_role, admin_reset_password_link,
    admin_user_import_sample_csv, admin_user_import_preview,
    admin_user_import_execute, admin_user_import_progress_api,
    admin_user_import_failed_csv,
    admin_force_end_meeting, admin_export_meeting_attendance_csv,
    admin_system_health, admin_system_health_api,
    admin_reports, admin_export_report_csv, admin_export_report_pdf,
    admin_settings, admin_update_settings, admin_semester_crud,
    admin_department_crud, admin_test_email,
    admin_approvals, admin_approval_enrollment_action, admin_approval_teacher_action,
    admin_approvals_bulk, admin_announcements, admin_announcement_send_now,
    admin_announcement_delete,
    admin_roles, admin_role_update, admin_assign_user_role,
    admin_command_palette_api
)
from .messaging_views import inbox, conversation_detail, start_conversation, send_message, search_users_ajax, delete_conversation
from .dashboard_views import teacher_dashboard, student_dashboard

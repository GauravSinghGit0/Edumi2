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
    admin_activity_feed
)
from .messaging_views import inbox, conversation_detail, start_conversation, send_message, search_users_ajax, delete_conversation
from .dashboard_views import teacher_dashboard, student_dashboard

# accounts/views/__init__.py
# Re-exports everything for backwards compatibility.
from .auth_views import (
    login_view, register, home, dismiss_welcome, save_emoji_avatar,
    error_404, error_500, settings_view,
    verify_email_sent_view, verify_email, resend_verification_email, check_availability
)
from .profile_views import profile_view, edit_profile, directory, search_users
from .admin_views import admin_panel, user_management, admin_edit_user, delete_user, architecture_view
from .messaging_views import inbox, conversation_detail, start_conversation, send_message, search_users_ajax, delete_conversation
from .dashboard_views import teacher_dashboard, student_dashboard

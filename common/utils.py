"""
Core utility functions shared across all apps
"""
import random
import string
from django.utils import timezone
from datetime import timedelta


def generate_unique_code(length=8, chars=None):
    """
    Generate a unique random alphanumeric code
    """
    if chars is None:
        chars = string.ascii_uppercase + string.digits
    
    return ''.join(random.choice(chars) for _ in range(length))


def format_duration(seconds):
    """
    Convert seconds to human-readable duration string
    e.g. 3661 seconds → "1h 1m 1s"
    """
    if not isinstance(seconds, int) or seconds < 0:
        return "0s"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if remaining_seconds > 0 or not parts:
        parts.append(f"{remaining_seconds}s")
    
    return " ".join(parts)


def get_user_type(user):
    """
    Get user type from UserProfile, returns None if no profile
    """
    if not user or not user.is_authenticated:
        return None
    
    if hasattr(user, 'userprofile'):
        return user.userprofile.user_type
    
    return None


def is_teacher(user):
    """Check if user is a teacher"""
    return get_user_type(user) == 'teacher'


def is_student(user):
    """Check if user is a student"""
    return get_user_type(user) == 'student'


def is_admin(user):
    """Check if user is an admin/superuser"""
    if not (user and user.is_authenticated):
        return False
    return user.is_superuser or getattr(user, 'is_staff', False) or (hasattr(user, 'userprofile') and user.userprofile.user_type == 'admin')


def is_superuser_or_teacher(user):
    """Check if user is superuser or teacher"""
    return is_admin(user) or is_teacher(user)


def time_since(dt):
    """
    Get human-readable time since datetime
    """
    if not dt:
        return ""
    
    now = timezone.now()
    diff = now - dt
    
    if diff < timedelta(minutes=1):
        return "just now"
    elif diff < timedelta(hours=1):
        mins = int(diff.total_seconds() // 60)
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    elif diff < timedelta(days=1):
        hours = int(diff.total_seconds() // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff < timedelta(weeks=1):
        days = int(diff.days)
        return f"{days} day{'s' if days != 1 else ''} ago"
    else:
        return dt.strftime("%b %d, %Y")


def get_user_display_name(user):
    """
    Get user display name: UserProfile.get_display_name() -> user.get_full_name() -> user.username
    """
    if not user:
        return ""
    profile = getattr(user, 'userprofile', None)
    if profile:
        return profile.get_display_name()
    if hasattr(user, 'get_full_name') and user.get_full_name():
        return user.get_full_name()
    return getattr(user, 'username', str(user))


def get_user_avatar_url(user):
    """
    Get avatar URL: UserProfile.get_profile_picture_url() -> ui-avatars.com fallback
    """
    if not user:
        return "https://ui-avatars.com/api/?name=User&background=1877f2&color=fff&size=200"
    profile = getattr(user, 'userprofile', None)
    if profile:
        return profile.get_profile_picture_url()
    import urllib.parse
    name = get_user_display_name(user) or "User"
    return f"https://ui-avatars.com/api/?name={urllib.parse.quote(name)}&background=1877f2&color=fff&size=200"


def get_user_identity(user):
    """
    Unified identity dictionary for any user across LMS modules.
    Delegates to IdentityService (Single Source of Truth).
    """
    if not user:
        return {}
    from accounts.identity import IdentityService
    return IdentityService.get_identity(user)



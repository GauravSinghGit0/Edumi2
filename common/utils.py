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
    return user.is_authenticated and user.is_superuser


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

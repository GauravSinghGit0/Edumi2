"""
Custom template tags and filters for common use
"""
from django import template
from common.utils import format_duration, time_since, is_teacher, is_student, get_user_type

register = template.Library()


@register.filter(name='format_duration')
def format_duration_filter(seconds):
    """
    Format seconds into human-readable duration
    Usage: {{ 3661|format_duration }} → "1h 1m 1s"
    """
    return format_duration(seconds)


@register.filter(name='duration_hms')
def duration_hms_filter(duration):
    """
    Format a duration (timedelta or seconds) into HH:MM:SS format
    Usage: {{ recording.duration|duration_hms }}
    """
    if duration is None:
        return "--:--:--"
    
    if hasattr(duration, 'total_seconds'):
        seconds = int(duration.total_seconds())
    else:
        try:
            seconds = int(float(duration))
        except (ValueError, TypeError):
            return "--:--:--"
            
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"



@register.filter(name='time_since')
def time_since_filter(dt):
    """
    Show time since datetime
    Usage: {{ post.created_at|time_since }}
    """
    return time_since(dt)


@register.filter(name='is_teacher')
def is_teacher_filter(user):
    """
    Check if user is a teacher
    Usage: {% if user|is_teacher %}
    """
    return is_teacher(user)


@register.filter(name='is_student')
def is_student_filter(user):
    """
    Check if user is a student
    Usage: {% if user|is_student %}
    """
    return is_student(user)


@register.simple_tag
def get_user_type_tag(user):
    """
    Get user type as template tag
    Usage: {% get_user_type_tag user as user_type %}
    """
    return get_user_type(user)


@register.filter(name='percentage')
def percentage(value, total):
    """
    Calculate percentage
    Usage: {{ value|percentage:total }}
    """
    if total == 0:
        return 0
    return round((value / total) * 100)


@register.filter(name='truncate_chars')
def truncate_chars(text, max_length):
    """
    Truncate text to max_length with ellipsis
    Usage: {{ long_text|truncate_chars:50 }}
    """
    if not text:
        return ""
    
    text = str(text)
    if len(text) <= max_length:
        return text
    
    return text[:max_length-3] + "..."


@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Get dictionary item by key in Django templates
    Usage: {{ dict|get_item:key }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter(name='user_display_name')
def user_display_name_filter(user):
    """
    Get user display name: {{ user|user_display_name }}
    """
    from common.utils import get_user_display_name
    return get_user_display_name(user)


@register.filter(name='user_avatar_url')
def user_avatar_url_filter(user):
    """
    Get user profile picture / avatar URL: {{ user|user_avatar_url }}
    """
    from common.utils import get_user_avatar_url
    return get_user_avatar_url(user)


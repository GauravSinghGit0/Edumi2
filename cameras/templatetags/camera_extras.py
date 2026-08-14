from django import template

register = template.Library()

@register.filter
def filter_published(recordings):
    """Filter recordings to only published ones"""
    return [rec for rec in recordings if rec.is_published]

@register.filter
def duration_format(duration):
    """Format a DurationField into a human-readable string (HH:MM:SS)"""
    if not duration:
        return "00:00"
    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

"""
Custom template tags and filters for common use
"""
from django import template
from common.utils import (
    format_duration,
    time_since,
    is_teacher,
    is_student,
    get_user_type,
    get_user_display_name,
    get_user_avatar_url,
)

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
    return get_user_display_name(user)


@register.filter(name='user_avatar_url')
def user_avatar_url_filter(user):
    """
    Get user profile picture / avatar URL: {{ user|user_avatar_url }}
    """
    return get_user_avatar_url(user)


NAV_ITEM_GROUPS = {
    'classrooms': {
        'url_names': {
            'teacher_classrooms', 'student_classrooms', 'create_classroom', 'classroom_detail',
            'join_classroom_request', 'approve_join_request', 'approve_all_join_requests',
            'deny_join_request', 'deny_all_join_requests', 'toggle_auto_approve', 'remove_student',
            'delete_classroom', 'leave_classroom', 'start_classroom_meeting',
            'classroom_attendance_history', 'classroom_attendance_detail', 'classroom_materials',
            'upload_study_material', 'create_material_unit', 'delete_study_material',
            'toggle_material_bookmark', 'download_study_material', 'material_detail_api',
            'classroom_assignments', 'create_assignment', 'edit_assignment', 'assignment_detail',
            'submit_assignment', 'evaluate_submission', 'delete_question_file',
            'classroom_quizzes', 'create_quiz', 'edit_quiz', 'quiz_detail', 'add_question',
            'delete_question', 'take_quiz', 'quiz_time_status', 'evaluate_quiz_submission',
        },
        'path_prefixes': ('/meetings/classroom/', '/classroom/', '/classrooms/', '/assignments/'),
    },
    'meetings': {
        'url_names': {
            'teacher_meetings', 'student_meetings', 'create_meeting', 'meeting_detail',
            'join_meeting', 'end_meeting', 'leave_meeting', 'delete_meeting', 'cancel_meeting',
            'livekit_token', 'meeting_attendance_history', 'meeting_attendance_detail',
            'meeting_summary', 'toggle_sleep', 'toggle_unfreeze', 'kick_participant',
            'ban_participant', 'toggle_global_mute', 'toggle_global_cam_off',
            'admin_all_meetings', 'admin_live_meetings', 'pre_join', 'verify_face_prejoin',
            'continue_meeting', 'get_participants', 'meeting_chunked_upload',
        },
        'path_prefixes': (
            '/meetings/teacher/', '/meetings/student/', '/meetings/join/', '/meetings/create/',
            '/meetings/end/', '/meetings/leave/', '/meetings/attendance/', '/meetings/summary/',
            '/meetings/prep/', '/meetings/delete/', '/meetings/cancel/', '/admin/meetings/',
            '/admin/live-meetings/',
        ),
    },
    'user_management': {
        'url_names': {
            'user_management', 'user_list', 'user_detail', 'user_edit', 'user_delete',
            'student_list', 'teacher_list', 'admin_all_users', 'admin_all_students',
            'admin_all_teachers', 'admin_edit_user', 'delete_user', 'architecture',
        },
        'path_prefixes': ('/user-management/', '/admin/users/', '/admin/students/', '/admin/teachers/'),
    },
    'camera_fleet': {
        'url_names': {
            'admin_dashboard', 'teacher_camera_dashboard', 'student_lecture_list',
            'camera_feed_direct', 'watch_live', 'control_room', 'teacher_control_room',
            'camera_list', 'camera_detail', 'stream_camera_video', 'admin_all_cameras',
            'add_camera', 'edit_camera', 'delete_camera', 'camera_feed', 'test_camera',
            'test_feed_page', 'probe_camera', 'start_streaming', 'stop_streaming',
            'update_zoom', 'start_camera_recording', 'stop_camera_recording',
            'publish_recording', 'mobile_mic', 'live_participants', 'camera_feed_proxy',
            'clear_stream_cache',
        },
        'path_prefixes': (
            '/cameras/admin-dashboard/', '/cameras/add-camera/', '/cameras/edit-camera/',
            '/cameras/delete-camera/', '/cameras/camera-feed/', '/cameras/test-camera/',
            '/cameras/test-feed/', '/cameras/probe/', '/cameras/lectures/',
            '/cameras/teacher-camera-dashboard/', '/control-room/', '/lectures/', '/admin/cameras/',
        ),
    },
    'content_manager': {
        'url_names': {'admin_content_manager', 'delete_recording_admin', 'delete_meeting_admin'},
        'path_prefixes': ('/cameras/content-manager/', '/content-manager/'),
    },
    'recordings_library': {
        'url_names': {'recordings_folder'},
        'path_prefixes': ('/cameras/recordings-folder/', '/recordings-folder/'),
    },
    'manage_recordings': {
        'url_names': {
            'manage_recordings', 'recording_analytics', 'toggle_recording_publish',
            'delete_recording', 'edit_recording', 'watch_recording', 'update_recording_edit',
            'apply_recording_trim', 'generate_recording_thumbnail', 'like_recording',
            'stream_video', 'recording_playlist', 'stream_chunk',
        },
        'path_prefixes': ('/cameras/manage-recordings/', '/manage-recordings/'),
    },
    'upload_video': {
        'url_names': {'camera_upload_video', 'upload_video', 'camera_chunked_upload'},
        'path_prefixes': ('/cameras/upload-video/', '/upload-video/'),
    },
    'video_editor': {
        'url_names': {
            'project_list', 'project_detail', 'project_upload', 'chunked_upload',
            'proxy_status', 'project_delete', 'project_download', 'project_download_mkv',
            'project_status', 'serve_media_ranges', 'op_trim', 'op_text', 'op_bg_audio',
            'op_rotate', 'op_resize', 'op_grayscale', 'op_fade', 'op_speed', 'op_split',
            'op_reset', 'export_project', 'publish_to_lecture', 'upload_audio_temp',
            'upload_asset', 'save_timeline', 'export_timeline',
        },
        'path_prefixes': ('/video-editing/',),
    },
    'inbox': {
        'url_names': {'inbox', 'conversation_detail', 'send_message'},
        'path_prefixes': ('/inbox/', '/conversation/'),
    },
    'notifications': {
        'url_names': {'notifications_list', 'notification_detail'},
        'path_prefixes': ('/notifications/',),
    },
    'profile': {
        'url_names': {'profile_view', 'edit_profile', 'user_profile', 'directory', 'search_users'},
        'path_prefixes': ('/profile/', '/directory/'),
    },
    'settings': {
        'url_names': {'settings'},
        'path_prefixes': ('/settings/',),
    },
    'digital_library': {
        'url_names': {'digital_library'},
        'path_prefixes': ('/meetings/library/', '/library/'),
    },
    'face_setup': {
        'url_names': {'face_setup'},
        'path_prefixes': ('/attendance/face/', '/face-setup/'),
    },
    'admin_panel': {
        'url_names': {'admin_panel'},
        'path_prefixes': ('/admin-panel/',),
    },
    'teacher_dashboard': {
        'url_names': {'teacher_dashboard'},
        'path_prefixes': ('/teacher-dashboard/',),
    },
    'student_dashboard': {
        'url_names': {'student_dashboard'},
        'path_prefixes': ('/student-dashboard/',),
    },
}

TARGET_TO_GROUP = {
    'teacher_classrooms': 'classrooms',
    'student_classrooms': 'classrooms',
    'teacher_meetings': 'meetings',
    'student_meetings': 'meetings',
    'admin_dashboard': 'camera_fleet',
    'teacher_camera_dashboard': 'camera_fleet',
    'student_lecture_list': 'camera_fleet',
    'admin_content_manager': 'content_manager',
    'recordings_folder': 'recordings_library',
    'camera_upload_video': 'upload_video',
    'project_list': 'video_editor',
    'notifications_list': 'notifications',
    'profile_view': 'profile',
}


@register.simple_tag(takes_context=True)
def is_active_nav(context, *args, **kwargs):
    """
    Route-aware helper to determine if a sidebar nav item should be active.
    Usage:
        {% is_active_nav 'teacher_classrooms' %}
        or
        {% is_active_nav request 'teacher_classrooms' %}
    """
    if not args:
        return ''

    first_arg = args[0]
    if hasattr(first_arg, 'resolver_match') or hasattr(first_arg, 'path'):
        request = first_arg
        target_names = args[1:]
    else:
        request = context.get('request') if context else None
        target_names = args

    if not request:
        return ''

    resolver_match = getattr(request, 'resolver_match', None)
    current_url_name = getattr(resolver_match, 'url_name', '') if resolver_match else ''
    current_view_name = getattr(resolver_match, 'view_name', '') if resolver_match else ''
    path = getattr(request, 'path', '') or ''

    for target in target_names:
        if not target or not isinstance(target, str):
            continue

        # 1. Exact match on URL name or view name
        if current_url_name and current_url_name == target:
            return 'active'
        if current_view_name and current_view_name == target:
            return 'active'

        # 2. Check route group mapping
        group_key = TARGET_TO_GROUP.get(target, target)
        group = NAV_ITEM_GROUPS.get(group_key)

        if group:
            if current_url_name and current_url_name in group['url_names']:
                return 'active'
            if current_view_name and current_view_name in group['url_names']:
                return 'active'
            
            prefixes = group.get('path_prefixes', ())
            if isinstance(prefixes, str):
                prefixes = (prefixes,)
            for prefix in prefixes:
                if prefix and path.startswith(prefix):
                    return 'active'

    return ''




"""
camera_service/camera_api/views/headcount_views.py
Head-counting session management in the camera microservice.
"""
import logging
from django.http import JsonResponse

logger = logging.getLogger('camera_api')

# In-memory active session registry
_active_sessions = {}


def start_head_count(request, camera_type, camera_id):
    """Start a head-counting session for the specified camera."""
    session_key = f"{camera_type}_{camera_id}"
    _active_sessions[session_key] = {
        'camera_type': camera_type,
        'camera_id': camera_id,
        'status': 'running',
    }
    logger.info(f"Head count session started: {session_key}")
    return JsonResponse({'status': 'started', 'session_key': session_key})


def stop_head_count(request, camera_type, camera_id):
    """Stop a head-counting session."""
    session_key = f"{camera_type}_{camera_id}"
    if session_key in _active_sessions:
        del _active_sessions[session_key]
        logger.info(f"Head count session stopped: {session_key}")
        return JsonResponse({'status': 'stopped'})
    return JsonResponse({'status': 'not_found'}, status=404)


def active_head_count_sessions(request):
    """Return all currently active head-count sessions."""
    return JsonResponse({'sessions': list(_active_sessions.values())})

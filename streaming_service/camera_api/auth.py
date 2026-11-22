import asyncio
from functools import wraps
from django.conf import settings
from django.http import JsonResponse
from django.utils.crypto import constant_time_compare


def require_streaming_service_auth(view_func):
    """
    Decorator protecting camera service endpoints from unauthorized access.
    Supports both sync and async view functions.
    Accepts:
      1. Secret header: X-Camera-Service-Secret or Authorization Bearer matching settings.CAMERA_SERVICE_SECRET
      2. Loopback local requests from internal services (127.0.0.1 without external proxy forwarding)
      3. Authenticated Django user session with staff/admin/teacher/student privileges.
    """
    def check_auth(request, *args, **kwargs):
        expected_secret = getattr(settings, 'STREAMING_SERVICE_SECRET', getattr(settings, 'CAMERA_SERVICE_SECRET', None))

        # 1. Header-based shared secret
        auth_header = request.headers.get('X-Streaming-Service-Secret') or request.headers.get('X-Camera-Service-Secret') or request.headers.get('X-Internal-Secret')
        if not auth_header:
            bearer = request.headers.get('Authorization', '')
            if bearer.startswith('Bearer '):
                auth_header = bearer[7:].strip()

        if expected_secret and auth_header and constant_time_compare(auth_header, expected_secret):
            return True

        # 2. Local loopback internal requests from same machine
        remote_ip = request.META.get('REMOTE_ADDR')
        if remote_ip in ('127.0.0.1', '::1') and not request.headers.get('X-Forwarded-For'):
            return True

        # 3. Session-based authenticated user (teachers, staff, students)
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            return True

        return False

    if asyncio.iscoroutinefunction(view_func):
        @wraps(view_func)
        async def _wrapped_async(request, *args, **kwargs):
            if not check_auth(request, *args, **kwargs):
                return JsonResponse(
                    {'error': 'Unauthorized: Valid service token or authenticated session required.'},
                    status=401
                )
            return await view_func(request, *args, **kwargs)
        return _wrapped_async
    else:
        @wraps(view_func)
        def _wrapped_sync(request, *args, **kwargs):
            if not check_auth(request, *args, **kwargs):
                return JsonResponse(
                    {'error': 'Unauthorized: Valid service token or authenticated session required.'},
                    status=401
                )
            return view_func(request, *args, **kwargs)
        return _wrapped_sync


# Backwards-compatibility alias
require_camera_service_auth = require_streaming_service_auth

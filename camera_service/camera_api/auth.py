from functools import wraps
from django.conf import settings
from django.http import JsonResponse
from django.utils.crypto import constant_time_compare


def require_camera_service_auth(view_func):
    """
    Decorator protecting camera service endpoints from unauthorized access.
    Accepts:
      1. Secret header: X-Camera-Service-Secret or Authorization Bearer matching settings.CAMERA_SERVICE_SECRET
      2. Authenticated Django user session with staff/admin or teacher camera viewing privileges.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        expected_secret = getattr(settings, 'CAMERA_SERVICE_SECRET', None)

        # 1. Header-based shared secret
        auth_header = request.headers.get('X-Camera-Service-Secret') or request.headers.get('X-Internal-Secret')
        if not auth_header:
            bearer = request.headers.get('Authorization', '')
            if bearer.startswith('Bearer '):
                auth_header = bearer[7:].strip()

        if expected_secret and auth_header and constant_time_compare(auth_header, expected_secret):
            return view_func(request, *args, **kwargs)

        # 2. Session-based authenticated user
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            if user.is_superuser or getattr(user, 'is_staff', False):
                return view_func(request, *args, **kwargs)
            if hasattr(user, 'userprofile') and user.userprofile.user_type in ('teacher', 'admin'):
                return view_func(request, *args, **kwargs)

        return JsonResponse(
            {'error': 'Unauthorized: Valid service token or authenticated session required.'},
            status=401
        )
    return _wrapped

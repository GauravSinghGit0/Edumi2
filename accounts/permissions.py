"""
accounts/permissions.py
Granular Role-Based Access Control (RBAC) helpers and decorators for Edumi administrators.
"""
from functools import wraps
import logging
from django.shortcuts import redirect, render
from django.http import HttpResponseForbidden, JsonResponse
from django.contrib import messages
from common.utils import is_ajax_request

logger = logging.getLogger(__name__)


def has_admin_permission(user, perm):
    """
    Check if a user possesses a specific administrative permission flag.
    - Non-authenticated or non-admin users always return False.
    - Superusers (user.is_superuser) always return True.
    - If user has an AdminRole, checks the corresponding boolean flag.
    """
    if not user or not user.is_authenticated:
        return False

    # Superusers maintain full, unrestricted access
    if user.is_superuser:
        return True

    # Must have an admin user profile
    profile = getattr(user, 'userprofile', None)
    if not profile or profile.user_type != 'admin':
        return False

    admin_role = getattr(profile, 'admin_role', None)
    if not admin_role:
        return False

    return bool(getattr(admin_role, perm, False))


def admin_permission_required(perm):
    """
    Decorator requiring an administrator to possess the specified permission flag.
    Returns HTTP 403 (or JSON 403) when permission is denied.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())

            # Verify admin role or superuser
            is_admin = request.user.is_superuser or (
                hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'admin'
            )
            if not is_admin:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or is_ajax_request(request):
                    return JsonResponse({'status': 'error', 'message': 'Administrator access required.'}, status=403)
                return HttpResponseForbidden(render(request, '403.html', {
                    'required_permission': perm,
                    'user_role': None,
                    'reason': 'Administrator role required.'
                }))

            # Verify granular permission flag
            if not has_admin_permission(request.user, perm):
                logger.warning(
                    f"Access Denied: User @{request.user.username} lacks permission '{perm}' "
                    f"for path {request.path}"
                )
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or is_ajax_request(request):
                    return JsonResponse({
                        'status': 'error',
                        'message': f"Permission denied: Missing '{perm}' capability."
                    }, status=403)

                role_name = getattr(getattr(request.user.userprofile, 'admin_role', None), 'name', 'No Assigned Role')
                return HttpResponseForbidden(render(request, '403.html', {
                    'required_permission': perm,
                    'role_name': role_name,
                    'reason': f"Your assigned role ({role_name}) does not have the '{perm}' capability."
                }))

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

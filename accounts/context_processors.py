import time

def timestamp(request):
    """Add timestamp for cache busting"""
    return {
        'timestamp': int(time.time())
    }

def face_registered(request):
    """Check if current user has registered face ID (for students)"""
    if not request.user.is_authenticated:
        return {'face_registered': False}
    
    try:
        from attendance.models import StudentFaceProfile
        profile = StudentFaceProfile.objects.filter(
            student=request.user,
            is_active=True
        ).first()
        return {'face_registered': profile is not None}
    except Exception:
        return {'face_registered': False}

def user_identity(request):
    """Expose the SSOT user identity to all templates without double resolution."""
    return {
        'user_identity': getattr(request, 'identity', None)
    }


def admin_approvals_context(request):
    """Expose pending approvals count globally for the admin sidebar badge."""
    if not request.user.is_authenticated:
        return {'pending_approvals_count': 0}

    is_admin = request.user.is_superuser or (
        hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'admin'
    )
    if not is_admin:
        return {'pending_approvals_count': 0}

    try:
        from academics.models import ClassroomMembership
        from django.contrib.auth import get_user_model
        from django.core.cache import cache

        cached_count = cache.get('admin_pending_approvals_count')
        if cached_count is not None:
            return {'pending_approvals_count': cached_count}

        User = get_user_model()
        pending_enrollments = ClassroomMembership.objects.filter(status='pending').count()
        pending_teachers = User.objects.filter(
            userprofile__user_type='teacher',
            is_active=False
        ).exclude(userprofile__is_deleted=True).count()

        total = pending_enrollments + pending_teachers
        cache.set('admin_pending_approvals_count', total, timeout=15)
        return {'pending_approvals_count': total}
    except Exception:
        return {'pending_approvals_count': 0}


def admin_permissions_context(request):
    """
    Exposes granular admin permissions dictionary to all templates:
    admin_perms.manage_users, admin_perms.manage_courses, admin_perms.manage_sessions,
    admin_perms.view_audit, admin_perms.manage_settings, admin_perms.manage_cameras,
    admin_perms.export_data.
    """
    if not request.user.is_authenticated:
        return {'admin_perms': {}}

    is_admin = request.user.is_superuser or (
        hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'admin'
    )
    if not is_admin:
        return {'admin_perms': {}}

    if request.user.is_superuser:
        return {
            'admin_perms': {
                'manage_users': True,
                'manage_courses': True,
                'manage_sessions': True,
                'view_audit': True,
                'manage_settings': True,
                'manage_cameras': True,
                'export_data': True,
                'is_superuser': True,
                'role_name': 'Superuser',
            }
        }

    role = getattr(getattr(request.user, 'userprofile', None), 'admin_role', None)
    if role:
        return {
            'admin_perms': {
                'manage_users': role.manage_users,
                'manage_courses': role.manage_courses,
                'manage_sessions': role.manage_sessions,
                'view_audit': role.view_audit,
                'manage_settings': role.manage_settings,
                'manage_cameras': role.manage_cameras,
                'export_data': role.export_data,
                'is_superuser': False,
                'role_name': role.name,
            }
        }

    return {
        'admin_perms': {
            'manage_users': False,
            'manage_courses': False,
            'manage_sessions': False,
            'view_audit': False,
            'manage_settings': False,
            'manage_cameras': False,
            'export_data': False,
            'is_superuser': False,
            'role_name': 'No Assigned Role',
        }
    }



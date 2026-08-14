"""
mobile_cameras/views/permission_views.py
Grant, revoke and manage per-teacher camera permissions.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import JsonResponse

from mobile_cameras.models import MobileCamera, MobileCameraPermission
from .utils import is_admin

User = get_user_model()


@login_required
def grant_permission(request, mobile_camera_id):
    """Grant a teacher permission to view a mobile camera (admin only)."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        mobile_camera = get_object_or_404(MobileCamera, id=mobile_camera_id)
        teacher = get_object_or_404(User, id=request.POST.get('teacher_id'))
        MobileCameraPermission.objects.get_or_create(
            mobile_camera=mobile_camera, teacher=teacher,
            defaults={'granted_by': request.user},
        )
        return JsonResponse({'success': True, 'message': f'Access granted to {teacher.get_full_name() or teacher.username}'})
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def revoke_permission(request, mobile_camera_id, teacher_id):
    """Revoke a teacher's permission to view a mobile camera (admin only)."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    mobile_camera = get_object_or_404(MobileCamera, id=mobile_camera_id)
    teacher = get_object_or_404(User, id=teacher_id)
    deleted, _ = MobileCameraPermission.objects.filter(mobile_camera=mobile_camera, teacher=teacher).delete()
    if deleted:
        return JsonResponse({'success': True, 'message': f'Access revoked from {teacher.get_full_name() or teacher.username}'})
    return JsonResponse({'success': False, 'message': 'Permission not found'})


@login_required
def manage_permissions(request, mobile_camera_id):
    """Manage mobile camera permissions page (admin only)."""
    if not is_admin(request.user):
        return redirect('login')
    mobile_camera = get_object_or_404(MobileCamera, id=mobile_camera_id)
    teachers = User.objects.filter(userprofile__user_type='teacher')
    authorized = mobile_camera.get_authorized_teachers()
    auth_ids = authorized.values_list('id', flat=True)
    return render(request, 'mobile_cameras/manage_permissions.html', {
        'mobile_camera': mobile_camera,
        'teachers': teachers,
        'authorized_teachers': authorized,
        'unauthorized_teachers': teachers.exclude(id__in=auth_ids),
    })

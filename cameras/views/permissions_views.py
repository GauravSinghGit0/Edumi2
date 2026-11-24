
import os
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from django.contrib.auth import get_user_model
from ..models import Camera, CameraPermission, CameraRecording
from meetings.models import Meeting
from .utils import is_admin, is_ajax_request
from accounts.permissions import admin_permission_required

logger = logging.getLogger(__name__)
User = get_user_model()


@login_required
@admin_permission_required('manage_cameras')
def admin_content_manager(request):
    """
    Unified Media Library for Admins:
    Centralized repository for classroom camera streams, lecture captures, and instructional video uploads.
    Supports tabs:
      - 'recordings' / 'all': All video recordings
      - 'uploaded': Uploaded videos (camera is null)
      - 'camera': Camera stream recordings (camera is set)
    """
    if not is_admin(request.user):
        return redirect('home')

    tab = request.GET.get('tab', 'recordings').lower()
    search_q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all').lower()

    base_qs = CameraRecording.objects.all().select_related('teacher', 'camera', 'classroom').order_by('-created_at')

    # Accurate tab counts across dataset
    total_recordings_count = base_qs.count()
    uploaded_count = base_qs.filter(camera__isnull=True).count()
    camera_recordings_count = base_qs.filter(camera__isnull=False).count()

    # Tab filtering
    if tab == 'uploaded':
        qs = base_qs.filter(camera__isnull=True)
    elif tab in ('camera', 'cameras'):
        tab = 'camera'
        qs = base_qs.filter(camera__isnull=False)
    else:
        tab = 'recordings'
        qs = base_qs

    # Search filter
    if search_q:
        qs = qs.filter(
            Q(title__icontains=search_q) |
            Q(teacher__username__icontains=search_q) |
            Q(teacher__first_name__icontains=search_q) |
            Q(teacher__last_name__icontains=search_q) |
            Q(classroom__title__icontains=search_q)
        )

    # Status filter
    if status_filter == 'published':
        qs = qs.filter(is_published=True)
    elif status_filter == 'hidden':
        qs = qs.filter(is_published=False)

    return render(request, 'cameras/control_room/admin_content_manager.html', {
        'recordings': qs,
        'active_tab': tab,
        'total_recordings_count': total_recordings_count,
        'uploaded_count': uploaded_count,
        'camera_recordings_count': camera_recordings_count,
        'search_q': search_q,
        'status_filter': status_filter,
    })


@login_required
def delete_recording_admin(request, recording_id):
    """Admin deletes a recording with file cleanup and audit logging"""
    is_ajax = is_ajax_request(request)
    if not is_admin(request.user):
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
        messages.error(request, 'Unauthorized.')
        return redirect('admin_panel')

    recording = get_object_or_404(CameraRecording, id=recording_id)
    title = recording.title
    source = recording.camera.name if recording.camera else 'Manual Upload'

    # Delete physical files from storage
    try:
        if recording.video_file and os.path.exists(recording.video_file.path):
            os.remove(recording.video_file.path)
    except Exception as exc:
        logger.warning(f"Error deleting recording video file: {exc}")

    try:
        if recording.thumbnail and os.path.exists(recording.thumbnail.path):
            os.remove(recording.thumbnail.path)
    except Exception as exc:
        logger.warning(f"Error deleting recording thumbnail file: {exc}")

    # Log to AdminAuditTrail
    try:
        from common.activity import log_admin_action
        from common.models import AdminAuditTrail
        log_admin_action(
            request,
            action_type=AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target=recording,
            changes={
                'deleted_media': {
                    'title': title,
                    'source': source,
                    'uploader': recording.teacher.username if recording.teacher else 'Unknown'
                }
            }
        )
    except Exception as exc:
        logger.warning(f"Audit log failed for recording deletion: {exc}")

    recording.delete()
    if is_ajax:
        return JsonResponse({'status': 'success', 'message': f'Media item "{title}" deleted successfully.'})
    messages.success(request, f"Recording '{title}' deleted successfully.")
    return redirect(request.META.get('HTTP_REFERER') or 'admin_content_manager')


@login_required
def delete_meeting_admin(request, meeting_id):
    """Admin deletes a meeting (kept for backwards compatibility)"""
    is_ajax = is_ajax_request(request)
    if not is_admin(request.user):
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
        messages.error(request, 'Unauthorized.')
        return redirect('admin_panel')

    meeting = get_object_or_404(Meeting, id=meeting_id)
    title = meeting.title

    try:
        from common.activity import log_admin_action
        from common.models import AdminAuditTrail
        log_admin_action(
            request,
            action_type=AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target=meeting,
            changes={'deleted_meeting': {'title': title}}
        )
    except Exception as exc:
        logger.warning(f"Audit log failed for meeting deletion: {exc}")

    meeting.delete()
    if is_ajax:
        return JsonResponse({'status': 'success', 'message': f'Meeting "{title}" deleted successfully.'})
    messages.success(request, f"Meeting '{title}' deleted successfully.")
    return redirect(request.META.get('HTTP_REFERER') or 'admin_panel')


@login_required
def grant_permission(request, camera_id):
    """Grant a teacher permission to view a camera"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    if request.method == 'POST':
        camera = get_object_or_404(Camera, id=camera_id)
        teacher_id = request.POST.get('teacher_id')
        teacher = get_object_or_404(User, id=teacher_id)

        CameraPermission.objects.get_or_create(
            camera=camera,
            teacher=teacher,
            defaults={'granted_by': request.user}
        )

        return JsonResponse({
            'success': True,
            'message': f'Access granted to {teacher.get_full_name() or teacher.username}'
        })

    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def revoke_permission(request, camera_id, teacher_id):
    """Revoke a teacher's permission to view a camera"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    camera = get_object_or_404(Camera, id=camera_id)
    teacher = get_object_or_404(User, id=teacher_id)

    deleted_count, _ = CameraPermission.objects.filter(camera=camera, teacher=teacher).delete()

    if deleted_count > 0:
        return JsonResponse({
            'success': True,
            'message': f'Access revoked from {teacher.get_full_name() or teacher.username}'
        })
    return JsonResponse({'success': False, 'message': 'Permission not found'})


@login_required
def manage_permissions(request, camera_id):
    """Manage camera permissions"""
    if not is_admin(request.user):
        return redirect('login')

    camera = get_object_or_404(Camera, id=camera_id)
    # Get all teachers
    teachers = User.objects.filter(userprofile__user_type='teacher')

    # Get authorized teachers
    authorized_teachers = camera.get_authorized_teachers()

    # Get unauthorized teachers (teachers who don't have permission yet)
    authorized_teacher_ids = authorized_teachers.values_list('id', flat=True)
    unauthorized_teachers = teachers.exclude(id__in=authorized_teacher_ids)

    context = {
        'camera': camera,
        'teachers': teachers,
        'authorized_teachers': authorized_teachers,
        'unauthorized_teachers': unauthorized_teachers,
    }
    return render(request, 'cameras/control_room/manage_permissions.html', context)


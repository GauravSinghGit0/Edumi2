
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from ..models import Camera, CameraPermission, CameraRecording
from meetings.models import Meeting
from .utils import is_admin

User = get_user_model()


@login_required
def admin_content_manager(request):
    """Admin view to manage all videos and meetings"""
    if not request.user.is_superuser:
        return redirect('home')

    # Get all recordings
    recordings = CameraRecording.objects.all().select_related('teacher', 'camera').order_by('-created_at')

    # Get all meetings
    meetings = Meeting.objects.all().select_related('teacher', 'classroom').order_by('-scheduled_time')

    return render(request, 'cameras/control_room/admin_content_manager.html', {
        'recordings': recordings,
        'meetings': meetings
    })


@login_required
def delete_recording_admin(request, recording_id):
    """Admin deletes a recording"""
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    recording = get_object_or_404(CameraRecording, id=recording_id)

    # Delete file from storage
    if recording.video_file and os.path.exists(recording.video_file.path):
        os.remove(recording.video_file.path)
    if recording.thumbnail and os.path.exists(recording.thumbnail.path):
        os.remove(recording.thumbnail.path)

    recording.delete()
    return JsonResponse({'status': 'success', 'message': 'Recording deleted successfully'})


@login_required
def delete_meeting_admin(request, meeting_id):
    """Admin deletes a meeting"""
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    meeting = get_object_or_404(Meeting, id=meeting_id)
    meeting.delete()
    return JsonResponse({'status': 'success', 'message': 'Meeting deleted successfully'})


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


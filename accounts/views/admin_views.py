"""
Admin panel views: main dashboard, user management, delete user, architecture.
"""
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import JsonResponse, HttpResponse
from django.db import transaction

from meetings.models import Meeting, Classroom, ClassroomMembership
from cameras.models import Camera, CameraPermission, CameraRecording

User = get_user_model()

logger = logging.getLogger(__name__)


@login_required
def admin_panel(request):
    """Admin dashboard with stats and detailed lists."""
    if not request.user.is_superuser:
        return redirect('login')

    from accounts.services import get_admin_stats
    stats = get_admin_stats()

    recent_users = User.objects.all().select_related('userprofile').order_by('-date_joined')[:20]
    students = User.objects.filter(userprofile__user_type='student').select_related('userprofile').order_by('-date_joined')[:20]
    teachers = User.objects.filter(userprofile__user_type='teacher').select_related('userprofile').order_by('-date_joined')[:20]
    all_meetings = Meeting.objects.filter(classroom__isnull=True).select_related('teacher', 'classroom').order_by('-created_at')[:20]
    
    from django.db.models import Count, Q
    live_meetings = Meeting.objects.filter(
        status='live', classroom__isnull=True
    ).select_related('teacher', 'classroom').annotate(
        active_participants_count=Count('participants', filter=Q(participants__is_active=True))
    ).order_by('-created_at')[:20]

    all_cameras = Camera.objects.all().order_by('-created_at')[:20]

    return render(request, 'accounts/admin/admin_panel.html', {
        **stats,
        'all_users': recent_users, 'students': students, 'teachers': teachers,
        'all_meetings': all_meetings, 'live_meetings': live_meetings,
        'all_cameras': all_cameras, 'recent_users': recent_users,
    })


@login_required
def user_management(request):
    """List all users for admin management."""
    if not request.user.is_superuser:
        return redirect('login')
    users = User.objects.all().select_related('userprofile').order_by('-date_joined')
    return render(request, 'accounts/admin/user_management.html', {'users': users})


@login_required
def admin_edit_user(request, user_id):
    """Admin view to inspect and edit any participant's profile and assign roles."""
    if not request.user.is_superuser:
        return redirect('login')

    target_user = get_object_or_404(User, id=user_id)
    from accounts.models import UserProfile
    profile, _ = UserProfile.objects.get_or_create(
        user=target_user,
        defaults={'user_type': 'admin' if target_user.is_superuser else 'student'}
    )

    if request.method == 'POST':
        from accounts.services import update_user_identity
        from django.contrib import messages
        try:
            update_user_identity(target_user, request.user, request.POST, request.FILES)
            messages.success(request, f"User {target_user.username}'s identity and profile updated successfully.")
            return redirect('user_management')
        except Exception as e:
            messages.error(request, f"Error updating user: {e}")

    return render(request, 'accounts/admin/admin_edit_user.html', {
        'target_user': target_user,
        'profile': profile,
    })



@login_required
def delete_user(request, user_id):
    """Delete a user account and clean up related objects."""
    if not request.user.is_superuser:
        return redirect('admin_panel')
    user = get_object_or_404(User, id=user_id)
    if user == request.user:
        return redirect('admin_panel')
    try:
        with transaction.atomic():
            ClassroomMembership.objects.filter(student=user).delete()
            ClassroomMembership.objects.filter(approved_by=user).update(approved_by=None)
            CameraRecording.objects.filter(teacher=user).delete()
            CameraPermission.objects.filter(teacher=user).delete()
            Meeting.objects.filter(teacher=user).delete()
            Classroom.objects.filter(teacher=user).delete()
            user.delete()
        return JsonResponse({'status': 'success', 'message': 'User deleted successfully'})
    except Exception as e:
        logger.error(f"Failed to delete user {user_id}: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def architecture_view(request):
    """Display system architecture visualization (admin only)."""
    if not request.user.is_superuser:
        return redirect('login')
    # The full inline HTML lives in accounts/views/_architecture_html.py
    from accounts.views._architecture_html import ARCHITECTURE_HTML
    return HttpResponse(ARCHITECTURE_HTML)

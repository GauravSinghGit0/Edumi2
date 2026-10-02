"""
Admin panel views: main dashboard, user management, User 360, Teacher 360, delete user, architecture.
Powered by real database analytics from accounts.admin_services.
"""
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import JsonResponse, HttpResponse
from django.db import models, transaction
from django.db.models import Q
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.views.decorators.http import require_POST

from meetings.models import Meeting, Classroom, ClassroomMembership
from cameras.models import Camera, CameraPermission, CameraRecording
from accounts.admin_services import (
    get_admin_dashboard_stats,
    get_admin_users_list,
    get_user_360_data,
    get_teacher_360_data,
)

User = get_user_model()
logger = logging.getLogger(__name__)


def check_admin(user):
    """Enforce strict admin authorization."""
    return user.is_authenticated and (user.is_superuser or (hasattr(user, 'userprofile') and user.userprofile.user_type == 'admin'))


@login_required
def admin_panel(request):
    """Admin dashboard with comprehensive real database metrics and activity feed."""
    if not check_admin(request.user):
        return redirect('login')

    stats = get_admin_dashboard_stats()

    # Hardware & microservice health indicators
    from accounts.services import check_port_open
    from django.core.cache import cache

    livekit_online = cache.get('livekit_service_health')
    if livekit_online is None:
        livekit_online = check_port_open('127.0.0.1', 7880, timeout=0.05) or check_port_open('127.0.0.1', 8002, timeout=0.05)
        cache.set('livekit_service_health', livekit_online, 15)

    all_cameras = Camera.objects.all().order_by('-created_at')[:10]

    return render(request, 'accounts/admin/admin_panel.html', {
        **stats,
        'all_cameras': all_cameras,
        'camera_service_online': livekit_online,
    })


@login_required
def admin_activity_feed(request):
    """Full platform activity feed page."""
    if not check_admin(request.user):
        return redirect('login')

    from common.activity import get_timeline_feed
    activity_feed = get_timeline_feed(user=None, limit=200)

    paginator = Paginator(activity_feed, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/admin/admin_activity_feed.html', {
        'activity_feed': page_obj,
        'page_obj': page_obj,
        'total_events': len(activity_feed),
    })


@login_required
def user_management(request):
    """List all users for admin management with search, role, and status filters."""
    if not check_admin(request.user):
        return redirect('login')

    search_query = request.GET.get('q', '').strip()
    active_role = request.GET.get('role', 'all').lower()
    active_status = request.GET.get('status', 'all').lower()

    enriched_users = get_admin_users_list(
        search_query=search_query,
        role_filter=active_role,
        status_filter=active_status,
    )

    # Counts for header filter pills (unfiltered total counts)
    total_count = User.objects.count()
    student_count = User.objects.filter(userprofile__user_type='student').count()
    teacher_count = User.objects.filter(userprofile__user_type='teacher').count()
    admin_count = User.objects.filter(models.Q(is_superuser=True) | models.Q(userprofile__user_type='admin')).distinct().count()

    # Pagination: 10 items per page
    paginator = Paginator(enriched_users, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/admin/user_management.html', {
        'users_data': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'student_count': student_count,
        'teacher_count': teacher_count,
        'admin_count': admin_count,
        'active_role': active_role,
        'active_status': active_status,
        'search_query': search_query,
    })


@login_required
def admin_user_detail(request, user_id):
    """User 360 Detail Page: complete profile, enrolled courses, attended classes, progress, and real timeline."""
    if not check_admin(request.user):
        return redirect('login')

    target_user = get_object_or_404(User, id=user_id)
    user_dossier = get_user_360_data(target_user.id)

    return render(request, 'accounts/admin/user_detail.html', {
        **user_dossier,
    })


@login_required
@require_POST
def admin_toggle_user_active(request, user_id):
    """Quickly toggle a user's active/suspended status."""
    if not check_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    target_user = get_object_or_404(User, id=user_id)
    if target_user == request.user:
        messages.error(request, "You cannot suspend your own admin account.")
        return redirect('admin_user_detail', user_id=target_user.id)

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])

    status_str = "activated" if target_user.is_active else "suspended"
    messages.success(request, f"User @{target_user.username} has been {status_str}.")
    return redirect('admin_user_detail', user_id=target_user.id)


@login_required
def admin_teacher_detail(request, teacher_id):
    """Teacher 360 Detail Page: overview, classrooms, meetings, connected students, and activity."""
    if not check_admin(request.user):
        return redirect('login')

    target_teacher = get_object_or_404(User, id=teacher_id)
    teacher_dossier = get_teacher_360_data(target_teacher.id)

    return render(request, 'accounts/admin/teacher_detail.html', {
        **teacher_dossier,
    })


@login_required
def admin_edit_user(request, user_id):
    """Admin view to inspect and edit any participant's profile and assign roles."""
    if not check_admin(request.user):
        return redirect('login')

    target_user = get_object_or_404(User, id=user_id)
    from accounts.models import UserProfile
    profile, _ = UserProfile.objects.get_or_create(
        user=target_user,
        defaults={'user_type': 'admin' if target_user.is_superuser else 'student'}
    )

    if request.method == 'POST':
        from accounts.services import update_user_identity
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
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('accept', '')

    if not check_admin(request.user):
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    user = get_object_or_404(User, id=user_id)
    if user == request.user:
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': 'You cannot delete your own account.'}, status=400)
        messages.error(request, "You cannot delete your own account.")
        return redirect('user_management')

    try:
        username = user.username
        with transaction.atomic():
            ClassroomMembership.objects.filter(student=user).delete()
            ClassroomMembership.objects.filter(approved_by=user).update(approved_by=None)
            CameraRecording.objects.filter(teacher=user).delete()
            CameraPermission.objects.filter(teacher=user).delete()
            Meeting.objects.filter(teacher=user).delete()
            Classroom.objects.filter(teacher=user).delete()
            from accounts.messaging_models import Conversation
            Conversation.objects.filter(classroom__isnull=True, participants=user).delete()
            user.delete()

        if is_ajax:
            return JsonResponse({'status': 'success', 'message': f'User @{username} deleted successfully.'})

        messages.success(request, f"User @{username} has been permanently deleted.")
        return redirect('user_management')
    except Exception as e:
        logger.error(f"Failed to delete user {user_id}: {e}")
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        messages.error(request, f"Failed to delete user: {e}")
        return redirect('user_management')


@login_required
def architecture_view(request):
    """Display system architecture visualization (admin only)."""
    if not check_admin(request.user):
        return redirect('login')
    from accounts.views._architecture_html import ARCHITECTURE_HTML
    return HttpResponse(ARCHITECTURE_HTML)


# =========================================================
# INDUSTRY-LEVEL ADMIN QUICK ACTION & EXPORT VIEWS
# =========================================================
import csv
import uuid

@login_required
@require_POST
def admin_create_user(request):
    """Admin action to create a new student, teacher, or administrator account."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    username = request.POST.get('username', '').strip()
    email = request.POST.get('email', '').strip()
    password = request.POST.get('password', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    user_type = request.POST.get('user_type', 'student').strip().lower()
    department = request.POST.get('department', '').strip()

    if not username or not password:
        messages.error(request, "Username and password are required.")
        return redirect('user_management')

    if User.objects.filter(username=username).exists():
        messages.error(request, f"Username @{username} is already taken.")
        return redirect('user_management')

    try:
        with transaction.atomic():
            is_super = (user_type == 'admin')
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_superuser=is_super,
                is_staff=is_super
            )
            from accounts.models import UserProfile
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.user_type = user_type
            if department:
                profile.department = department
            profile.save()

            messages.success(request, f"User @{username} ({user_type.title()}) created successfully.")
    except Exception as e:
        logger.error(f"Error creating user {username}: {e}")
        messages.error(request, f"Failed to create user: {e}")

    return redirect('user_management')


@login_required
@require_POST
def admin_create_classroom(request):
    """Admin action to create a new classroom/course."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    title = request.POST.get('title', '').strip()
    class_code = (request.POST.get('class_code') or '').strip().upper() or f"CLS-{uuid.uuid4().hex[:6].upper()}"
    password = (request.POST.get('password') or '').strip() or f"class-{uuid.uuid4().hex[:8]}"
    description = request.POST.get('description', '').strip()
    teacher_id = request.POST.get('teacher_id')
    auto_approve = request.POST.get('auto_approve') == 'on' or request.POST.get('auto_approve') == 'true'

    if not title or not teacher_id:
        messages.error(request, "Classroom title and teacher selection are required.")
        return redirect('admin_all_classrooms')

    if Classroom.objects.filter(class_code=class_code).exists():
        messages.error(request, f"Class code '{class_code}' is already in use. Choose another one.")
        return redirect('admin_all_classrooms')

    teacher = get_object_or_404(User, id=teacher_id)
    try:
        cr = Classroom.objects.create(
            title=title,
            class_code=class_code,
            password=make_password(password),
            description=description,
            teacher=teacher,
            auto_approve=auto_approve,
            is_active=True,
        )
        messages.success(request, f"Classroom '{cr.title}' created successfully. Share code: {cr.class_code}")
    except Exception as e:
        logger.error(f"Error creating classroom: {e}")
        messages.error(request, f"Failed to create classroom: {e}")

    return redirect('admin_all_classrooms')


@login_required
@require_POST
def admin_schedule_meeting(request):
    """Admin action to schedule a new live meeting or class session."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    title = request.POST.get('title', '').strip()
    classroom_id = request.POST.get('classroom_id')
    teacher_id = request.POST.get('teacher_id')
    scheduled_time_str = request.POST.get('scheduled_time')
    duration_minutes = int(request.POST.get('duration_minutes', 60))

    if not title or not teacher_id:
        messages.error(request, "Meeting Title and Host Teacher selection are required.")
        return redirect('admin_all_meetings')

    teacher = get_object_or_404(User, id=teacher_id)
    classroom = Classroom.objects.filter(id=classroom_id).first() if classroom_id else None

    try:
        code = f"MEET-{uuid.uuid4().hex[:6].upper()}"
        sched_time = timezone.now()
        if scheduled_time_str:
            try:
                from django.utils.dateparse import parse_datetime
                parsed = parse_datetime(scheduled_time_str)
                if parsed:
                    sched_time = parsed
            except Exception:
                pass

        meeting = Meeting.objects.create(
            title=title,
            meeting_code=code,
            teacher=teacher,
            classroom=classroom,
            scheduled_time=sched_time,
            duration_minutes=duration_minutes,
            status='scheduled'
        )
        messages.success(request, f"Meeting '{meeting.title}' (Code: {code}) scheduled successfully.")
    except Exception as e:
        logger.error(f"Error scheduling meeting: {e}")
        messages.error(request, f"Failed to schedule meeting: {e}")

    return redirect('admin_all_meetings')


@login_required
@require_POST
def admin_approve_student(request, classroom_id, student_id):
    """Approve a student's pending membership request for a classroom."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    membership = ClassroomMembership.objects.filter(classroom_id=classroom_id, student_id=student_id).first()
    if membership:
        membership.status = 'approved'
        membership.approved_by = request.user
        membership.save(update_fields=['status', 'approved_by'])
        messages.success(request, f"Approved student @{membership.student.username} for classroom.")
    else:
        messages.error(request, "Membership request not found.")

    return redirect('admin_classroom_detail', classroom_id=classroom_id)


@login_required
@require_POST
def admin_reject_student(request, classroom_id, student_id):
    """Reject a student's pending membership request for a classroom."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    membership = ClassroomMembership.objects.filter(classroom_id=classroom_id, student_id=student_id).first()
    if membership:
        membership.status = 'rejected'
        membership.save(update_fields=['status'])
        messages.warning(request, f"Rejected membership request for student @{membership.student.username}.")
    else:
        messages.error(request, "Membership request not found.")

    return redirect('admin_classroom_detail', classroom_id=classroom_id)


@login_required
def admin_export_users_csv(request):
    """Export all registered platform users as a CSV document."""
    if not check_admin(request.user):
        return HttpResponse("Permission denied", status=403)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="edumi_users_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

    writer = csv.writer(response)
    writer.writerow(['ID', 'Username', 'Full Name', 'Email', 'Role', 'Status', 'Date Joined', 'Last Login'])

    users = User.objects.select_related('userprofile').order_by('id')
    for u in users:
        role = getattr(u, 'userprofile', None).user_type if hasattr(u, 'userprofile') else ('admin' if u.is_superuser else 'student')
        status = 'Active' if u.is_active else 'Suspended'
        joined = u.date_joined.strftime('%Y-%m-%d %H:%M:%S') if u.date_joined else ''
        last_login = u.last_login.strftime('%Y-%m-%d %H:%M:%S') if u.last_login else ''
        writer.writerow([u.id, u.username, u.get_full_name(), u.email, role, status, joined, last_login])

    return response

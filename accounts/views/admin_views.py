from django.urls import reverse
"""
Admin panel views: main dashboard, user management, User 360, Teacher 360, delete user, architecture.
Powered by real database analytics from accounts.admin_services.
"""
import logging
import json
import csv
from datetime import datetime, time

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import JsonResponse, HttpResponse
from django.db import models, transaction
from django.db.models import Count, Q
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.contrib.auth.hashers import make_password
from django.views.decorators.http import require_POST

from django.conf import settings
from meetings.models import Meeting, Classroom, ClassroomMembership, MeetingParticipant
from accounts.models import UserProfile
from cameras.models import Camera
from accounts.permissions import admin_permission_required, has_admin_permission
from accounts.admin_services import (
    get_admin_dashboard_stats,
    get_admin_users_list,
    get_admin_users_queryset,
    enrich_user_subset,
    get_user_360_data,
    get_teacher_360_data,
)
from django.core.cache import cache
from common.utils import is_ajax_request
from common.models import AdminAuditTrail, log_admin_action

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
        'streaming_service_online': stats.get('system_health', {}).get('livekit', {}).get('online', False),
    })


@login_required
def admin_dashboard_metrics_api(request):
    """
    JSON API for executive dashboard ApexCharts:
    - Attendance and session utilization (area chart)
    - Submissions vs quiz completions (stacked bar)
    Supports ?range=7|30.
    """
    if not check_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    range_param = request.GET.get('range', '7').strip()
    days = 30 if range_param == '30' else 7

    from common.telemetry_cache import get_cached_dashboard_chart_metrics
    data = get_cached_dashboard_chart_metrics(days=days)
    return JsonResponse(data)


@login_required
@admin_permission_required('manage_settings')
def admin_system_health(request):
    """
    Live Infrastructure and System Health Command Center:
    Monitors LiveKit SFU, Daphne ASGI, Redis, Celery workers, Database,
    Camera gateway, and Ollama RAG, with segmented media storage breakdown
    and recent error inspection.
    """
    if not check_admin(request.user):
        messages.error(request, 'Access restricted to administrators.')
        return redirect('admin_panel')

    from common.system_health import get_full_system_health
    force = request.GET.get('force') == '1'
    health_data = get_full_system_health(use_cache=True, force=force)

    return render(request, 'accounts/admin/system_health.html', {
        'health': health_data,
        'page_title': 'System Health',
    })


@login_required
@admin_permission_required('manage_settings')
def admin_system_health_api(request):
    """
    JSON API for 15s auto-refresh polling and live card updates.
    Supports ?force=1 to bypass cache.
    """
    if not check_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    from common.system_health import get_full_system_health
    force = request.GET.get('force') == '1'
    health_data = get_full_system_health(use_cache=True, force=force)
    return JsonResponse(health_data)


@login_required
@admin_permission_required('view_audit')
def admin_activity_feed(request):
    """
    Security & Audit Center:
    Centralized administrative governance audit trail and authentication telemetry.
    Tabs:
      1. 'admin_actions': Immutable records from AdminAuditTrail with target, changes diff, IP.
      2. 'login_activity': Real-time login/logout telemetry including failed attempts and IPs.
    Features:
      - Filter by admin user, action type, and date range.
      - Debounced search across targets, IPs, and usernames.
      - Server-side pagination.
      - CSV export with mandatory audit logging.
    """
    if not check_admin(request.user):
        return redirect('login')

    tab = request.GET.get('tab', 'admin_actions').strip().lower()
    if tab not in ['admin_actions', 'login_activity']:
        tab = 'admin_actions'

    search_query = request.GET.get('search', '').strip()
    admin_filter = request.GET.get('admin', '').strip()
    action_type_filter = request.GET.get('action_type', '').strip()
    date_from_str = request.GET.get('date_from', '').strip()
    date_to_str = request.GET.get('date_to', '').strip()
    page_number = request.GET.get('page', 1)
    is_export = request.GET.get('export') == 'csv'

    from common.models import AdminAuditTrail, UserActivityLog, log_admin_action

    date_from = None
    date_to = None
    if date_from_str:
        df = parse_date(date_from_str)
        if df:
            date_from = timezone.make_aware(datetime.combine(df, time.min))
    if date_to_str:
        dt = parse_date(date_to_str)
        if dt:
            date_to = timezone.make_aware(datetime.combine(dt, time.max))

    # All admin accounts for filter dropdown
    admins_list = User.objects.filter(
        Q(is_superuser=True) | Q(userprofile__user_type='admin')
    ).distinct().order_by('username')

    action_choices = AdminAuditTrail.ACTION_TYPE_CHOICES

    if tab == 'admin_actions':
        qs = AdminAuditTrail.objects.select_related('admin_user').all()

        if admin_filter:
            if admin_filter.isdigit():
                qs = qs.filter(admin_user_id=admin_filter)
            else:
                qs = qs.filter(admin_user__username__icontains=admin_filter)

        if action_type_filter:
            qs = qs.filter(action_type=action_type_filter)

        if date_from:
            qs = qs.filter(timestamp__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__lte=date_to)

        if search_query:
            qs = qs.filter(
                Q(target_label__icontains=search_query) |
                Q(target_type__icontains=search_query) |
                Q(target_id__icontains=search_query) |
                Q(admin_user__username__icontains=search_query) |
                Q(ip_address__icontains=search_query) |
                Q(action_type__icontains=search_query)
            )

        total_count = qs.count()

        if is_export:
            # Audit log the export itself!
            log_admin_action(
                request,
                AdminAuditTrail.ACTION_DATA_EXPORTED,
                target='AdminAuditTrail',
                changes={'format': 'csv', 'tab': 'admin_actions', 'count': total_count, 'filters': request.GET.dict()}
            )
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="security_audit_admin_actions_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
            writer = csv.writer(response)
            writer.writerow(['ID', 'Timestamp', 'Admin User', 'Action Type', 'Target Type', 'Target ID', 'Target Label', 'IP Address', 'User Agent', 'Changes JSON'])
            for row in qs:
                admin_name = row.admin_user.username if row.admin_user else 'System'
                writer.writerow([
                    row.id,
                    row.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    admin_name,
                    row.get_action_type_display(),
                    row.target_type,
                    row.target_id,
                    row.target_label,
                    row.ip_address or '',
                    row.user_agent or '',
                    json.dumps(row.changes_json or {})
                ])
            return response

        paginator = Paginator(qs, 20)
        page_obj = paginator.get_page(page_number)

    else:
        # tab == 'login_activity'
        logins_qs = UserActivityLog.objects.select_related('user').filter(
            Q(event_name__in=['LOGIN', 'LOGOUT', 'LOGIN_FAILED']) | Q(event_type='auth')
        )

        if admin_filter:
            if admin_filter.isdigit():
                logins_qs = logins_qs.filter(user_id=admin_filter)
            else:
                logins_qs = logins_qs.filter(username__icontains=admin_filter)

        if action_type_filter:
            logins_qs = logins_qs.filter(event_name=action_type_filter)

        if date_from:
            logins_qs = logins_qs.filter(created_at__gte=date_from)
        if date_to:
            logins_qs = logins_qs.filter(created_at__lte=date_to)

        if search_query:
            logins_qs = logins_qs.filter(
                Q(username__icontains=search_query) |
                Q(ip_address__icontains=search_query) |
                Q(event_name__icontains=search_query) |
                Q(user_agent__icontains=search_query)
            )

        total_count = logins_qs.count()

        if is_export:
            # Audit log the export itself!
            log_admin_action(
                request,
                AdminAuditTrail.ACTION_DATA_EXPORTED,
                target='UserActivityLog',
                changes={'format': 'csv', 'tab': 'login_activity', 'count': total_count, 'filters': request.GET.dict()}
            )
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="security_audit_logins_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
            writer = csv.writer(response)
            writer.writerow(['ID', 'Timestamp', 'Username', 'Role', 'Event', 'Status', 'IP Address', 'Browser', 'OS', 'User Agent'])
            for row in logins_qs:
                status = 'Failed' if row.event_name == 'LOGIN_FAILED' else ('Success' if row.event_name == 'LOGIN' else 'Logout')
                writer.writerow([
                    row.id,
                    row.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    row.username or (row.user.username if row.user else 'Unknown'),
                    row.user_role or 'N/A',
                    row.event_name,
                    status,
                    row.ip_address or '',
                    row.browser or '',
                    row.os or '',
                    row.user_agent or ''
                ])
            return response

        paginator = Paginator(logins_qs, 20)
        page_obj = paginator.get_page(page_number)

    # Top KPI Metrics
    total_admin_actions = AdminAuditTrail.objects.count()
    total_failed_logins = UserActivityLog.objects.filter(event_name='LOGIN_FAILED').count()
    total_logins = UserActivityLog.objects.filter(event_name='LOGIN').count()

    return render(request, 'accounts/admin/admin_activity_feed.html', {
        'tab': tab,
        'page_obj': page_obj,
        'total_count': total_count,
        'total_admin_actions': total_admin_actions,
        'total_failed_logins': total_failed_logins,
        'total_logins': total_logins,
        'admins_list': admins_list,
        'action_choices': action_choices,
        'search_query': search_query,
        'admin_filter': admin_filter,
        'action_type_filter': action_type_filter,
        'date_from': date_from_str,
        'date_to': date_to_str,
        'breadcrumb_list': [
            {'title': 'Home', 'url': 'admin_panel'},
            {'title': 'Security & Audit'},
        ],
    })


@login_required
@admin_permission_required('view_audit')
def admin_audit_changes_api(request, audit_id):
    """JSON API returning changes diff and metadata for a specific AdminAuditTrail record."""
    if not check_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    from common.models import AdminAuditTrail
    audit = get_object_or_404(AdminAuditTrail.objects.select_related('admin_user'), id=audit_id)
    return JsonResponse({
        'status': 'success',
        'audit': {
            'id': audit.id,
            'timestamp': audit.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'admin_user': audit.admin_user.username if audit.admin_user else 'System',
            'action_type': audit.action_type,
            'action_display': audit.get_action_type_display(),
            'target_type': audit.target_type,
            'target_id': audit.target_id,
            'target_label': audit.target_label,
            'ip_address': audit.ip_address or '',
            'user_agent': audit.user_agent or '',
            'changes': audit.changes_json or {},
        }
    })


@login_required
@admin_permission_required('manage_users')
def user_management(request):
    """List all users for admin management with search, tab/role, department, and status filters."""
    if not check_admin(request.user):
        return redirect('login')

    search_query = request.GET.get('q', '').strip()
    active_tab = request.GET.get('tab', request.GET.get('role', 'all')).lower()
    active_role = request.GET.get('role', active_tab).lower()
    active_status = request.GET.get('status', 'all').lower()
    active_dept = request.GET.get('dept', 'all').strip()
    sort_by = request.GET.get('sort', 'joined')
    sort_dir = request.GET.get('dir', 'desc')

    # Retrieve filtered, sorted queryset without eager in-memory loading of all users
    users_qs = get_admin_users_queryset(
        search_query=search_query,
        role_filter=active_tab,
        status_filter=active_status,
        dept_filter=active_dept,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    # Cached counts for header filter pills (TTL 60s to prevent full table scans on every tab click)
    cache_key_counts = "admin_user_directory_counts"
    cached_counts = cache.get(cache_key_counts)
    if not cached_counts:
        total_count = User.objects.exclude(username__startswith='test_').count()
        student_count = User.objects.filter(userprofile__user_type='student').exclude(username__startswith='test_').count()
        teacher_count = User.objects.filter(userprofile__user_type='teacher').exclude(username__startswith='test_').count()
        admin_count = User.objects.filter(models.Q(is_superuser=True) | models.Q(userprofile__user_type='admin')).exclude(username__startswith='test_').distinct().count()
        suspended_count = User.objects.filter(is_active=False).exclude(username__startswith='test_').count()
        cached_counts = {
            'total': total_count,
            'students': student_count,
            'teachers': teacher_count,
            'admins': admin_count,
            'suspended': suspended_count,
        }
        cache.set(cache_key_counts, cached_counts, timeout=60)
    else:
        total_count = cached_counts['total']
        student_count = cached_counts['students']
        teacher_count = cached_counts['teachers']
        admin_count = cached_counts['admins']
        suspended_count = cached_counts['suspended']

    # Pagination: Paginate FIRST (10 items per page), then enrich ONLY those 10 items
    paginator = Paginator(users_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    enriched_page_users = enrich_user_subset(page_obj.object_list)
    # Assign enriched list to page_obj.object_list for template iterators
    page_obj.object_list = enriched_page_users

    context = {
        'users_data': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'student_count': student_count,
        'teacher_count': teacher_count,
        'admin_count': admin_count,
        'suspended_count': suspended_count,
        'active_tab': active_tab,
        'active_role': active_role,
        'active_status': active_status,
        'active_dept': active_dept,
        'sort_by': sort_by,
        'sort_dir': sort_dir,
        'search_query': search_query,
    }

    # If partial request from AJAX tab switch, render only the table/cards partial
    if request.GET.get('partial') == '1' or is_ajax_request(request):
        return render(request, 'accounts/admin/partials/user_table_partial.html', context)

    return render(request, 'accounts/admin/user_management.html', context)


@login_required
@admin_permission_required('manage_users')
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
@admin_permission_required('manage_users')
def admin_toggle_user_active(request, user_id):
    """Quickly toggle a user's active/suspended status."""
    if not check_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    target_user = get_object_or_404(User, id=user_id)
    if target_user == request.user:
        messages.error(request, "You cannot suspend your own admin account.")
        return redirect('admin_user_detail', user_id=target_user.id)

    old_active = target_user.is_active
    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])

    action_type = AdminAuditTrail.ACTION_USER_ACTIVATED if target_user.is_active else AdminAuditTrail.ACTION_USER_SUSPENDED
    log_admin_action(
        request,
        action_type,
        target=target_user,
        changes={'is_active': {'before': old_active, 'after': target_user.is_active}}
    )

    status_str = "activated" if target_user.is_active else "suspended"
    messages.success(request, f"User @{target_user.username} has been {status_str}.")
    return redirect('admin_user_detail', user_id=target_user.id)


@login_required
@admin_permission_required('manage_users')
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
@admin_permission_required('manage_users')
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
            old_role = getattr(profile, 'user_type', None)
            old_email = target_user.email
            old_name = target_user.get_full_name()

            update_user_identity(target_user, request.user, request.POST, request.FILES)
            profile.refresh_from_db()
            target_user.refresh_from_db()

            changes = {
                'name': {'before': old_name, 'after': target_user.get_full_name()},
                'email': {'before': old_email, 'after': target_user.email},
            }
            if old_role != profile.user_type:
                changes['user_type'] = {'before': old_role, 'after': profile.user_type}
                action_type = AdminAuditTrail.ACTION_ROLE_CHANGED
            else:
                action_type = AdminAuditTrail.ACTION_USER_UPDATED

            log_admin_action(request, action_type, target=target_user, changes=changes)

            messages.success(request, f"User {target_user.username}'s identity and profile updated successfully.")
            return redirect('user_management')
        except Exception as e:
            messages.error(request, f"Error updating user: {e}")

    return render(request, 'accounts/admin/admin_edit_user.html', {
        'target_user': target_user,
        'profile': profile,
    })


@login_required
@admin_permission_required('manage_users')
def delete_user(request, user_id):
    """
    Safely deactivate/soft-delete a user account while preserving historical
    academic records (attendance, submissions, classroom materials, audit trails).
    """
    is_ajax = is_ajax_request(request)

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
            user.is_active = False
            user.save(update_fields=['is_active'])
            if hasattr(user, 'userprofile'):
                user.userprofile.soft_delete()

            # Invalidate session cache
            from accounts.identity import IdentityService
            IdentityService.invalidate_identity_cache(user.id)

            log_admin_action(
                request,
                AdminAuditTrail.ACTION_USER_DELETED,
                target=user,
                changes={'method': 'soft_delete', 'is_active': False, 'username': username}
            )

        if is_ajax:
            return JsonResponse({'status': 'success', 'message': f'User @{username} deactivated and archived successfully.'})

        messages.success(request, f"User @{username} has been safely deactivated and archived.")
        return redirect('user_management')
    except Exception as e:
        logger.error(f"Failed to deactivate user {user_id}: {e}")
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        messages.error(request, f"Failed to deactivate user: {e}")
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
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

@login_required
@require_POST
@admin_permission_required('manage_users')
def admin_create_user(request):
    """Admin action to create a new student, teacher, or administrator account."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    username = request.POST.get('username', '').strip()
    email = request.POST.get('email', '').strip().lower()
    password = request.POST.get('password', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    user_type = request.POST.get('user_type', 'student').strip().lower()
    department = request.POST.get('department', '').strip()

    if not username or not password:
        messages.error(request, "Username and password are required.")
        return redirect('user_management')

    if User.objects.filter(username__iexact=username).exists():
        messages.error(request, f"Username @{username} is already taken.")
        return redirect('user_management')

    if email:
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Please enter a valid email address.")
            return redirect('user_management')
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, f"An account with email '{email}' already exists.")
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

            log_admin_action(
                request,
                AdminAuditTrail.ACTION_USER_CREATED,
                target=user,
                changes={
                    'username': username,
                    'email': email,
                    'user_type': user_type,
                    'department': department,
                    'is_superuser': is_super
                }
            )

            messages.success(request, f"User @{username} ({user_type.title()}) created successfully.")
    except Exception as e:
        logger.error(f"Error creating user {username}: {e}")
        messages.error(request, f"Failed to create user: {e}")

    return redirect('user_management')


@login_required
@require_POST
@admin_permission_required('manage_courses')
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

    teacher = get_object_or_404(User, id=teacher_id)
    teacher_profile = getattr(teacher, 'userprofile', None)
    if not teacher_profile or teacher_profile.user_type != 'teacher':
        messages.error(request, f"Instructor validation failed: User @{teacher.username} must have role 'teacher' (current role: {getattr(teacher_profile, 'user_type', 'none')}).")
        return redirect('admin_all_classrooms')

    if Classroom.objects.filter(class_code=class_code).exists():
        messages.error(request, f"Class code '{class_code}' is already in use. Choose another one.")
        return redirect('admin_all_classrooms')

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
        log_admin_action(
            request,
            AdminAuditTrail.ACTION_CLASSROOM_CREATED,
            target=cr,
            changes={
                'title': cr.title,
                'class_code': cr.class_code,
                'teacher_id': teacher.id,
                'teacher_username': teacher.username,
                'auto_approve': auto_approve,
                'is_active': True
            }
        )
        messages.success(request, f"Classroom '{cr.title}' created successfully. Share code: {cr.class_code}")
    except Exception as e:
        logger.error(f"Error creating classroom: {e}")
        messages.error(request, f"Failed to create classroom: {e}")

    return redirect('admin_all_classrooms')


@login_required
@admin_permission_required('manage_courses')
def admin_edit_classroom(request, classroom_id):
    """Admin action to view or update classroom / course settings via drawer or modal."""
    if not check_admin(request.user):
        if is_ajax_request(request):
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    cr = get_object_or_404(Classroom, id=classroom_id)

    if request.method == 'GET':
        if is_ajax_request(request):
            return JsonResponse({
                'status': 'success',
                'classroom': {
                    'id': cr.id,
                    'title': cr.title,
                    'class_code': cr.class_code,
                    'description': cr.description or '',
                    'teacher_id': cr.teacher_id,
                    'teacher_name': cr.teacher.get_full_name() or cr.teacher.username,
                    'auto_approve': cr.auto_approve,
                    'enrollment_mode': 'auto' if cr.auto_approve else 'manual',
                    'is_active': cr.is_active,
                }
            })
        return redirect('admin_classroom_detail', classroom_id=cr.id)

    if request.method == 'POST':
        # Support both form encoded and JSON payloads
        data = request.POST
        if request.content_type == 'application/json' and request.body:
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = request.POST

        title = str(data.get('title') or '').strip()
        class_code = str(data.get('class_code') or '').strip().upper()
        description = str(data.get('description') or '').strip()
        teacher_id = data.get('teacher_id')

        # Enrollment mode support: 'auto' vs 'manual', or boolean checkbox 'on'/'true'
        enrollment_mode = data.get('enrollment_mode')
        if enrollment_mode:
            auto_approve = (enrollment_mode == 'auto')
        else:
            auto_approve = data.get('auto_approve') in ['on', 'true', '1', True]

        is_active = data.get('is_active') in ['on', 'true', '1', True]

        if not title or not teacher_id:
            msg = "Course title and instructor selection are required."
            if is_ajax_request(request):
                return JsonResponse({'status': 'error', 'message': msg}, status=400)
            messages.error(request, msg)
            return redirect('admin_all_classrooms')

        teacher = get_object_or_404(User, id=teacher_id)
        teacher_profile = getattr(teacher, 'userprofile', None)
        if not teacher_profile or teacher_profile.user_type != 'teacher':
            msg = f"Instructor validation failed: User @{teacher.username} must have role 'teacher' (current role: {getattr(teacher_profile, 'user_type', 'none')})."
            if is_ajax_request(request):
                return JsonResponse({'status': 'error', 'message': msg}, status=400)
            messages.error(request, msg)
            return redirect('admin_all_classrooms')

        if class_code and Classroom.objects.filter(class_code=class_code).exclude(id=cr.id).exists():
            msg = f"Class code '{class_code}' is already used by another classroom."
            if is_ajax_request(request):
                return JsonResponse({'status': 'error', 'message': msg}, status=400)
            messages.error(request, msg)
            return redirect('admin_all_classrooms')

        try:
            old_title = cr.title
            old_code = cr.class_code
            old_teacher_id = cr.teacher_id
            old_auto_approve = cr.auto_approve
            old_active = cr.is_active

            cr.title = title
            if class_code:
                cr.class_code = class_code
            cr.description = description
            cr.teacher = teacher
            cr.auto_approve = auto_approve
            cr.is_active = is_active

            new_password = str(data.get('password') or '').strip()
            if new_password:
                cr.password = make_password(new_password)

            cr.save()

            changes = {
                'title': {'before': old_title, 'after': cr.title},
                'class_code': {'before': old_code, 'after': cr.class_code},
                'teacher_id': {'before': old_teacher_id, 'after': cr.teacher_id},
                'auto_approve': {'before': old_auto_approve, 'after': cr.auto_approve},
                'is_active': {'before': old_active, 'after': cr.is_active},
                'password_updated': bool(new_password)
            }
            action_type = AdminAuditTrail.ACTION_CLASSROOM_ARCHIVED if (old_active and not cr.is_active) else AdminAuditTrail.ACTION_SETTINGS_CHANGED
            log_admin_action(request, action_type, target=cr, changes=changes)

            success_msg = f"Course '{cr.title}' settings updated successfully."
            if is_ajax_request(request):
                return JsonResponse({
                    'status': 'success',
                    'message': success_msg,
                    'classroom': {
                        'id': cr.id,
                        'title': cr.title,
                        'class_code': cr.class_code,
                        'teacher_name': cr.teacher.get_full_name() or cr.teacher.username,
                        'auto_approve': cr.auto_approve,
                        'is_active': cr.is_active,
                    }
                })
            messages.success(request, success_msg)
        except Exception as e:
            logger.error(f"Error updating classroom {classroom_id}: {e}")
            if is_ajax_request(request):
                return JsonResponse({'status': 'error', 'message': f"Failed to update course: {e}"}, status=500)
            messages.error(request, f"Failed to update course: {e}")

        return redirect('admin_all_classrooms')


@login_required
@require_POST
@admin_permission_required('manage_sessions')
def admin_force_end_meeting(request, meeting_id):
    """
    Force-ends an active live session immediately from the Live Monitor or meeting list.
    Terminates WebRTC sessions, sets status to 'ended', timestamps ended_at,
    updates participant statuses, broadcasts channel layer disconnect, and logs to AdminAuditTrail.
    """
    if not check_admin(request.user):
        if is_ajax_request(request):
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied.")
        return redirect('admin_all_meetings')

    meeting = get_object_or_404(Meeting, id=meeting_id)
    if meeting.status != 'live':
        if is_ajax_request(request):
            return JsonResponse({'status': 'error', 'message': f"Meeting is not currently live (status: {meeting.status})."}, status=400)
        messages.warning(request, f"Meeting is not currently live (status: {meeting.status}).")
        return redirect('admin_live_monitor')

    now = timezone.now()
    meeting.status = 'ended'
    meeting.ended_at = now
    meeting.save(update_fields=['status', 'ended_at'])

    # Disconnect active participants
    active_participants = list(MeetingParticipant.objects.filter(meeting=meeting, is_active=True).select_related('user'))
    for p in active_participants:
        if p.joined_at:
            session_secs = max(0, int((now - p.joined_at).total_seconds()))
            p.total_duration_seconds = (p.total_duration_seconds or 0) + session_secs
        p.is_active = False
        p.left_at = now
        p.save(update_fields=['is_active', 'left_at', 'total_duration_seconds'])

    # Broadcast websocket group termination
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'meeting_{meeting.meeting_code.upper()}',
                {'type': 'meeting_ended', 'reason': 'Force terminated by Administrator'}
            )
    except Exception as chan_err:
        logger.warning(f"Failed broadcasting meeting end: {chan_err}")

    # Audit log
    changes = {
        'action': 'force_end_session',
        'meeting_code': meeting.meeting_code,
        'disconnected_participants': len(active_participants),
        'ended_at': now.isoformat(),
    }
    log_admin_action(request, AdminAuditTrail.ACTION_SETTINGS_CHANGED, target=meeting, changes=changes)

    msg = f"Live session '{meeting.title}' ({meeting.meeting_code}) was force-terminated successfully."
    if is_ajax_request(request):
        return JsonResponse({'status': 'success', 'message': msg})
    messages.success(request, msg)
    return redirect('admin_live_monitor')


@login_required
@admin_permission_required('export_data')
def admin_export_meeting_attendance_csv(request, meeting_id):
    """
    Exports full attendance log for a meeting to RFC 4180 CSV, including join/leave times
    and biometric face-verification confidence.
    Logs action to AdminAuditTrail under ACTION_DATA_EXPORTED.
    """
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_all_meetings')

    from attendance.models import AttendanceRecord

    meeting = get_object_or_404(
        Meeting.objects.select_related('teacher', 'classroom'),
        id=meeting_id
    )

    participants = list(MeetingParticipant.objects.filter(meeting=meeting).select_related('user', 'user__userprofile').order_by('user__last_name', 'user__first_name'))
    attendance_records = {
        rec.student_id: rec
        for rec in AttendanceRecord.objects.filter(meeting=meeting).select_related('student')
    }

    import io
    output = io.StringIO()
    writer = csv.writer(output)

    # Metadata Header
    writer.writerow(['Session Title', meeting.title])
    writer.writerow(['Session Code', meeting.meeting_code])
    writer.writerow(['Host Teacher', meeting.teacher.get_full_name() or meeting.teacher.username])
    writer.writerow(['Course', meeting.classroom.title if meeting.classroom else 'Standalone'])
    writer.writerow(['Scheduled Time', meeting.scheduled_time.strftime('%Y-%m-%d %H:%M:%S') if meeting.scheduled_time else ''])
    writer.writerow(['Status', meeting.get_status_display()])
    writer.writerow([])

    # Table Header
    writer.writerow([
        'Full Name',
        'Username',
        'Email',
        'Role',
        'Joined At',
        'Left At',
        'Duration (Minutes)',
        'Attendance Status',
        'Verification Method',
        'Face Match Confidence (%)'
    ])

    for p in participants:
        u = p.user
        att = attendance_records.get(u.id)
        role_label = 'Host Teacher' if u == meeting.teacher else getattr(getattr(u, 'userprofile', None), 'user_type', 'student').capitalize()

        joined_str = p.joined_at.strftime('%Y-%m-%d %H:%M:%S') if p.joined_at else '—'
        left_str = p.left_at.strftime('%Y-%m-%d %H:%M:%S') if p.left_at else ('In Session' if p.is_active else '—')
        duration_mins = round((p.total_duration_seconds or 0) / 60, 1)

        att_status = att.get_status_display() if att else ('Present' if p.joined_at else 'Absent')
        verif_method = att.get_verification_method_display() if att else ('Manual' if u == meeting.teacher else 'Unverified')
        confidence = f"{round(att.face_match_confidence * 100, 1)}%" if (att and att.face_match_confidence) else '—'

        writer.writerow([
            u.get_full_name() or u.username,
            u.username,
            u.email,
            role_label,
            joined_str,
            left_str,
            duration_mins,
            att_status,
            verif_method,
            confidence
        ])

    # Audit log
    log_admin_action(
        request,
        AdminAuditTrail.ACTION_DATA_EXPORTED,
        target=meeting,
        changes={
            'export': 'session_attendance_csv',
            'meeting_code': meeting.meeting_code,
            'total_rows': len(participants),
        }
    )

    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
    filename = f"attendance_session_{meeting.meeting_code}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_POST
@admin_permission_required('manage_courses')
def admin_toggle_classroom_active(request, classroom_id):
    """Toggle classroom between active and archived/suspended."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    cr = get_object_or_404(Classroom, id=classroom_id)
    old_active = cr.is_active
    cr.is_active = not cr.is_active
    cr.save(update_fields=['is_active'])

    action_type = AdminAuditTrail.ACTION_CLASSROOM_ARCHIVED if not cr.is_active else AdminAuditTrail.ACTION_SETTINGS_CHANGED
    log_admin_action(
        request,
        action_type,
        target=cr,
        changes={'is_active': {'before': old_active, 'after': cr.is_active}}
    )

    state_str = "restored" if cr.is_active else "archived"
    messages.success(request, f"Classroom '{cr.title}' has been {state_str}.")
    return redirect('admin_all_classrooms')


@login_required
@require_POST
@admin_permission_required('manage_courses')
def admin_bulk_archive_classrooms(request):
    """Bulk archive selected classrooms."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    classroom_ids = request.POST.getlist('classroom_ids')
    if not classroom_ids:
        raw_ids = request.POST.get('classroom_ids', '')
        if raw_ids:
            classroom_ids = [x.strip() for x in raw_ids.split(',') if x.strip()]

    if classroom_ids:
        count = Classroom.objects.filter(id__in=classroom_ids).update(is_active=False)
        log_admin_action(
            request,
            AdminAuditTrail.ACTION_BULK_ACTION,
            target='Classroom',
            changes={'action': 'bulk_archive', 'classroom_ids': classroom_ids, 'count': count}
        )
        messages.success(request, f"Successfully archived {count} classroom(s).")
    else:
        messages.warning(request, "No classrooms were selected for archiving.")

    return redirect('admin_all_classrooms')


@login_required
@admin_permission_required('export_data')
def admin_bulk_export_classrooms(request):
    """Export selected (or all) classrooms as a CSV spreadsheet."""
    if not check_admin(request.user):
        return HttpResponse("Permission denied", status=403)

    classroom_ids = request.POST.getlist('classroom_ids') or request.GET.getlist('classroom_ids')
    if not classroom_ids:
        raw_ids = request.POST.get('classroom_ids') or request.GET.get('classroom_ids') or ''
        if raw_ids:
            classroom_ids = [x.strip() for x in raw_ids.split(',') if x.strip()]

    classrooms_qs = Classroom.objects.select_related('teacher', 'teacher__userprofile').annotate(
        approved_students=Count('memberships', filter=Q(memberships__status='approved'), distinct=True),
        pending_students=Count('memberships', filter=Q(memberships__status='pending'), distinct=True),
    ).order_by('-created_at')

    if classroom_ids:
        classrooms_qs = classrooms_qs.filter(id__in=classroom_ids)

    log_admin_action(
        request,
        AdminAuditTrail.ACTION_DATA_EXPORTED,
        target='Classroom',
        changes={'export_format': 'csv', 'count': classrooms_qs.count(), 'filter_ids': classroom_ids}
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="edumi_classrooms_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

    writer = csv.writer(response)
    writer.writerow(['ID', 'Title', 'Class Code', 'Instructor Username', 'Instructor Name', 'Instructor Role', 'Status', 'Enrolled Students', 'Pending Requests', 'Created At'])

    for cr in classrooms_qs:
        inst = cr.teacher
        inst_role = getattr(getattr(inst, 'userprofile', None), 'user_type', 'none') if inst else 'none'
        inst_name = inst.get_full_name() if inst else 'Unassigned'
        inst_user = inst.username if inst else 'N/A'
        status = 'Active' if cr.is_active else 'Archived'
        created = cr.created_at.strftime('%Y-%m-%d %H:%M:%S') if cr.created_at else ''

        writer.writerow([
            cr.id,
            cr.title,
            cr.class_code,
            inst_user,
            inst_name,
            inst_role,
            status,
            cr.approved_students,
            cr.pending_students,
            created
        ])

    return response


@login_required
@admin_permission_required('manage_users')
def admin_bulk_users_status(request):
    """Bulk activate or suspend selected user accounts."""
    if not check_admin(request.user):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    if request.content_type == 'application/json':
        try:
            body_data = json.loads(request.body.decode('utf-8'))
            user_ids = body_data.get('user_ids', [])
            status_action = body_data.get('status_action', 'suspend').strip().lower()
        except Exception:
            user_ids = []
            status_action = 'suspend'
    else:
        user_ids = request.POST.getlist('user_ids')
        if not user_ids:
            raw_ids = request.POST.get('user_ids', '')
            if raw_ids:
                user_ids = [x.strip() for x in raw_ids.split(',') if x.strip()]
        status_action = request.POST.get('status_action', 'suspend').strip().lower()

    if not user_ids:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'status': 'warning', 'message': 'No users were selected.'}, status=400)
        messages.warning(request, "No users were selected.")
        return redirect(request.META.get('HTTP_REFERER') or 'user_management')

    # Guard: prevent superuser / current admin self-modification in bulk
    safe_user_ids = [uid for uid in user_ids if str(uid) != str(request.user.id)]

    if status_action == 'activate':
        count = User.objects.filter(id__in=safe_user_ids).update(is_active=True)
        msg = f"Successfully activated {count} user account(s)."
        messages.success(request, msg)
    else:
        count = User.objects.filter(id__in=safe_user_ids).update(is_active=False)
        msg = f"Successfully suspended {count} user account(s)."
        messages.success(request, msg)

    log_admin_action(
        request,
        AdminAuditTrail.ACTION_BULK_ACTION,
        target='User',
        changes={'action': f'bulk_{status_action}', 'user_ids': safe_user_ids, 'count': count}
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'status': 'success', 'count': count, 'message': msg})

    return redirect(request.META.get('HTTP_REFERER') or 'user_management')


@login_required
@admin_permission_required('manage_users')
def admin_bulk_change_role(request):
    """Bulk change role assignment for selected user accounts."""
    if not check_admin(request.user):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    from accounts.models import UserProfile

    if request.content_type == 'application/json':
        try:
            body_data = json.loads(request.body.decode('utf-8'))
            user_ids = body_data.get('user_ids', [])
            new_role = body_data.get('new_role', '').strip().lower()
        except Exception:
            user_ids = []
            new_role = ''
    else:
        user_ids = request.POST.getlist('user_ids')
        if not user_ids:
            raw_ids = request.POST.get('user_ids', '')
            if raw_ids:
                user_ids = [x.strip() for x in raw_ids.split(',') if x.strip()]
        new_role = request.POST.get('new_role', '').strip().lower()

    if new_role not in ('student', 'teacher', 'admin'):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'status': 'error', 'message': 'Invalid role specified.'}, status=400)
        messages.error(request, "Invalid role specified.")
        return redirect(request.META.get('HTTP_REFERER') or 'user_management')

    if not user_ids:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'status': 'warning', 'message': 'No users were selected.'}, status=400)
        messages.warning(request, "No users were selected.")
        return redirect(request.META.get('HTTP_REFERER') or 'user_management')

    safe_user_ids = [uid for uid in user_ids if str(uid) != str(request.user.id)]
    updated_count = 0

    for uid in safe_user_ids:
        try:
            target = User.objects.get(id=uid)
            profile, _ = UserProfile.objects.get_or_create(user=target)
            profile.user_type = new_role
            profile.save(update_fields=['user_type'])
            if new_role == 'admin' and not target.is_staff:
                target.is_staff = True
                target.save(update_fields=['is_staff'])
            updated_count += 1
        except User.DoesNotExist:
            continue

    log_admin_action(
        request,
        AdminAuditTrail.ACTION_ROLE_CHANGED,
        target=f"{updated_count} Users",
        changes={'new_role': new_role, 'affected_user_ids': safe_user_ids, 'count': updated_count}
    )

    msg = f"Successfully updated role to {new_role.capitalize()} for {updated_count} user(s)."
    messages.success(request, msg)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'status': 'success', 'count': updated_count, 'message': msg})

    return redirect(request.META.get('HTTP_REFERER') or 'user_management')


@login_required
@admin_permission_required('manage_users')
def admin_reset_password_link(request, user_id):
    """
    Generates a secure password reset link for any user account on-demand.
    Audit logged to AdminAuditTrail with ACTION_PASSWORD_RESET.
    """
    if not check_admin(request.user):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    target_user = get_object_or_404(User, id=user_id)
    from accounts.email_tokens import generate_password_reset_token
    token = generate_password_reset_token(target_user)
    base_url = request.build_absolute_uri('/')[:-1]
    reset_url = f"{base_url}/password-reset/confirm/?token={token}"

    log_admin_action(
        request,
        AdminAuditTrail.ACTION_PASSWORD_RESET,
        target=target_user,
        changes={'action': 'password_reset_link_generated', 'target_user': target_user.username}
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json' or request.GET.get('format') == 'json':
        return JsonResponse({
            'status': 'success',
            'username': target_user.username,
            'reset_url': reset_url,
            'message': f"Password reset link generated for @{target_user.username}."
        })

    messages.success(request, f"Password reset link generated for @{target_user.username}: {reset_url}")
    return redirect(request.META.get('HTTP_REFERER') or 'user_management')


@login_required
@require_POST
@admin_permission_required('manage_sessions')
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
        log_admin_action(
            request,
            AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target=meeting,
            changes={
                'title': meeting.title,
                'meeting_code': code,
                'teacher_id': teacher.id,
                'classroom_id': classroom.id if classroom else None,
                'duration_minutes': duration_minutes,
                'status': 'scheduled'
            }
        )
        messages.success(request, f"Meeting '{meeting.title}' (Code: {code}) scheduled successfully.")
    except Exception as e:
        logger.error(f"Error scheduling meeting: {e}")
        messages.error(request, f"Failed to schedule meeting: {e}")

    return redirect('admin_all_meetings')


@login_required
@require_POST
@admin_permission_required('manage_courses')
def admin_approve_student(request, classroom_id, student_id):
    """Approve a student's pending membership request for a classroom."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    membership = ClassroomMembership.objects.filter(classroom_id=classroom_id, student_id=student_id).first()
    if membership:
        old_status = membership.status
        membership.status = 'approved'
        membership.approved_by = request.user
        membership.save(update_fields=['status', 'approved_by'])
        log_admin_action(
            request,
            AdminAuditTrail.ACTION_ENROLLMENT_APPROVED,
            target=membership,
            changes={
                'classroom_id': classroom_id,
                'student_id': student_id,
                'student_username': membership.student.username,
                'status': {'before': old_status, 'after': 'approved'}
            }
        )
        messages.success(request, f"Approved student @{membership.student.username} for classroom.")
    else:
        messages.error(request, "Membership request not found.")

    return redirect('admin_classroom_detail', classroom_id=classroom_id)


@login_required
@require_POST
@admin_permission_required('manage_courses')
def admin_reject_student(request, classroom_id, student_id):
    """Reject a student's pending membership request for a classroom."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    membership = ClassroomMembership.objects.filter(classroom_id=classroom_id, student_id=student_id).first()
    if membership:
        old_status = membership.status
        membership.status = 'rejected'
        membership.save(update_fields=['status'])
        log_admin_action(
            request,
            AdminAuditTrail.ACTION_ENROLLMENT_REJECTED,
            target=membership,
            changes={
                'classroom_id': classroom_id,
                'student_id': student_id,
                'student_username': membership.student.username,
                'status': {'before': old_status, 'after': 'rejected'}
            }
        )
        messages.warning(request, f"Rejected membership request for student @{membership.student.username}.")
    else:
        messages.error(request, "Membership request not found.")

    return redirect('admin_classroom_detail', classroom_id=classroom_id)


@login_required
@admin_permission_required('export_data')
def admin_export_users_csv(request):
    """Export all registered platform users as a CSV document, with optional user_ids filtering."""
    if not check_admin(request.user):
        return HttpResponse("Permission denied", status=403)

    user_ids = request.POST.getlist('user_ids') or request.GET.getlist('user_ids')
    if not user_ids:
        raw_ids = request.POST.get('user_ids') or request.GET.get('user_ids') or ''
        if raw_ids:
            user_ids = [x.strip() for x in raw_ids.split(',') if x.strip()]

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="edumi_users_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

    writer = csv.writer(response)
    writer.writerow(['ID', 'Username', 'Full Name', 'Email', 'Role', 'Status', 'Date Joined', 'Last Login'])

    users = User.objects.select_related('userprofile').order_by('id')
    if user_ids:
        users = users.filter(id__in=user_ids)

    log_admin_action(
        request,
        AdminAuditTrail.ACTION_DATA_EXPORTED,
        target='User',
        changes={'export_format': 'csv', 'count': users.count(), 'filter_ids': user_ids}
    )

    for u in users:
        role = getattr(u, 'userprofile', None).user_type if hasattr(u, 'userprofile') else ('admin' if u.is_superuser else 'student')
        status = 'Active' if u.is_active else 'Suspended'
        joined = u.date_joined.strftime('%Y-%m-%d %H:%M:%S') if u.date_joined else ''
        last_login = u.last_login.strftime('%Y-%m-%d %H:%M:%S') if u.last_login else ''
        writer.writerow([u.id, u.username, u.get_full_name(), u.email, role, status, joined, last_login])

    return response


# ==============================================================================
# BULK USER IMPORTER VIEWS & APIs
# ==============================================================================

@login_required
@admin_permission_required('manage_users')
def admin_user_import_sample_csv(request):
    """Downloads a compliant sample CSV template for bulk user imports."""
    if not check_admin(request.user):
        return HttpResponse("Permission denied", status=403)

    from accounts.admin_services import generate_user_import_sample_csv
    content = generate_user_import_sample_csv()

    response = HttpResponse(content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="edumi_user_import_template.csv"'
    return response


@login_required
@admin_permission_required('manage_users')
def admin_user_import_preview(request):
    """
    Parses an uploaded CSV file, validates all rows in memory, and returns
    a preview payload with per-row valid/invalid indicators and specific error reasons.
    """
    if not check_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    import uuid
    from django.core.cache import cache
    from accounts.admin_services import parse_and_validate_user_import_csv

    uploaded_file = request.FILES.get('file') or request.FILES.get('csv_file')
    if not uploaded_file:
        return JsonResponse({'status': 'error', 'message': 'No CSV file was uploaded.'}, status=400)

    try:
        validation_result = parse_and_validate_user_import_csv(uploaded_file)
        if 'error' in validation_result:
            return JsonResponse({'status': 'error', 'message': validation_result['error']}, status=400)

        # Cache parsed validation data for 30 minutes
        file_token = str(uuid.uuid4())
        cache.set(f"user_import_preview_{file_token}", {
            'validation': validation_result,
            'filename': uploaded_file.name,
        }, timeout=1800)

        return JsonResponse({
            'status': 'success',
            'file_token': file_token,
            'filename': uploaded_file.name,
            'total_rows': validation_result['total_rows'],
            'valid_count': validation_result['valid_count'],
            'invalid_count': validation_result['invalid_count'],
            'rows': validation_result['rows'],
        })
    except Exception as exc:
        logger.error(f"Error parsing user import CSV: {exc}")
        return JsonResponse({'status': 'error', 'message': f"Failed to parse CSV file: {str(exc)}"}, status=500)


@login_required
@admin_permission_required('manage_users')
def admin_user_import_execute(request):
    """
    Initiates asynchronous bulk creation of users from validated rows.
    Spawns Celery task (or threaded background worker) and returns task_id for progress polling.
    """
    if not check_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    import uuid
    import threading
    from django.core.cache import cache
    from accounts.tasks import bulk_import_users_task

    file_token = request.POST.get('file_token', '').strip()
    send_invites = request.POST.get('send_invites', 'true').lower() in ('true', '1', 'yes')

    cached_data = cache.get(f"user_import_preview_{file_token}") if file_token else None
    if not cached_data:
        # Fallback to direct raw JSON rows if passed in request body
        try:
            body = json.loads(request.body.decode('utf-8'))
            file_token = body.get('file_token')
            send_invites = body.get('send_invites', True)
            if file_token:
                cached_data = cache.get(f"user_import_preview_{file_token}")
        except Exception:
            pass

    if not cached_data:
        return JsonResponse({'status': 'error', 'message': 'Import session expired or invalid. Please re-upload the CSV file.'}, status=400)

    validation_result = cached_data['validation']
    filename = cached_data.get('filename', 'users.csv')
    valid_rows = [r for r in validation_result['rows'] if r.get('is_valid')]

    if not valid_rows:
        return JsonResponse({'status': 'error', 'message': 'No valid rows found to import.'}, status=400)

    task_id = str(uuid.uuid4())
    ip_addr = request.META.get('REMOTE_ADDR', '127.0.0.1')

    # Initialize task progress in cache immediately
    cache.set(f"user_import_progress_{task_id}", {
        'status': 'PENDING',
        'current': 0,
        'total': len(valid_rows),
        'progress_pct': 0,
        'success_count': 0,
        'failed_count': 0,
        'task_id': task_id,
    }, timeout=3600)

    # Dispatch to Celery or graceful thread fallback
    dispatched = False
    try:
        if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
            bulk_import_users_task(
                request.user.id,
                valid_rows,
                send_invites,
                filename,
                task_id,
                ip_addr
            )
            dispatched = True
        else:
            bulk_import_users_task.delay(
                request.user.id,
                valid_rows,
                send_invites,
                filename,
                task_id,
                ip_addr
            )
            dispatched = True
    except Exception as exc:
        logger.warning(f"Could not dispatch import task via Celery ({exc}). Running via daemon thread.")

    if not dispatched:
        def run_in_thread():
            from django.db import connections
            connections.close_all()
            try:
                bulk_import_users_task(request.user.id, valid_rows, send_invites, filename, task_id, ip_addr)
            finally:
                connections.close_all()

        t = threading.Thread(target=run_in_thread, daemon=True)
        t.start()

    return JsonResponse({
        'status': 'success',
        'task_id': task_id,
        'total_valid': len(valid_rows),
        'message': f"Import initiated for {len(valid_rows)} users."
    })


@login_required
@admin_permission_required('manage_users')
def admin_user_import_progress_api(request, task_id):
    """Returns real-time progress percentage and counts for an ongoing bulk import task."""
    if not check_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    from django.core.cache import cache
    progress = cache.get(f"user_import_progress_{task_id}")

    if not progress:
        return JsonResponse({
            'status': 'PENDING',
            'current': 0,
            'total': 0,
            'progress_pct': 0,
            'success_count': 0,
            'failed_count': 0,
            'task_id': task_id,
        })

    return JsonResponse(progress)


@login_required
@admin_permission_required('manage_users')
def admin_user_import_failed_csv(request, task_id):
    """Generates and downloads a CSV of failed rows with specific error reasons."""
    if not check_admin(request.user):
        return HttpResponse("Permission denied", status=403)

    from django.core.cache import cache
    failed_rows = cache.get(f"user_import_failed_{task_id}") or []

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="failed_user_import_{task_id}.csv"'

    writer = csv.writer(response)
    writer.writerow(['username', 'email', 'first_name', 'last_name', 'role', 'department', 'error_reason'])

    for r in failed_rows:
        writer.writerow([
            r.get('username', ''),
            r.get('email', ''),
            r.get('first_name', ''),
            r.get('last_name', ''),
            r.get('role', ''),
            r.get('department', ''),
            r.get('error_reason', 'Validation failed')
        ])

    return response


# ==============================================================================
# REPORTS & ANALYTICS VIEWS
# ==============================================================================

@login_required
@admin_permission_required('view_audit')
def admin_reports(request):
    """
    Centralized Governance & Executive Reporting Center:
    (a) Attendance report by course/date
    (b) Engagement & attention report
    (c) User activity & security telemetry report
    (d) Course performance & academic health report
    Each view provides filtering, KPI summary counters, CSV export, and PDF generation.
    """
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    from django.core.paginator import Paginator
    from academics.models import Classroom
    import accounts.report_services as rs

    tab = request.GET.get('tab', 'attendance').strip().lower()
    if tab not in ('attendance', 'engagement', 'user_activity', 'course_performance'):
        tab = 'attendance'

    # Dropdown choices
    courses = Classroom.objects.filter(is_active=True).values('id', 'title', 'class_code').order_by('title')
    departments = list(
        User.objects.filter(userprofile__user_type='teacher', userprofile__department__isnull=False)
        .exclude(userprofile__department='')
        .values_list('userprofile__department', flat=True)
        .distinct()
        .order_by('userprofile__department')
    )
    teachers = User.objects.filter(userprofile__user_type='teacher', is_active=True).order_by('first_name', 'username')

    context = {
        'active_tab': tab,
        'courses': courses,
        'departments': departments,
        'teachers': teachers,
        'filters': request.GET.dict(),
        'page_title': 'Reports & Analytics',
        'page_subtitle': 'Export audit-verified institutional reports across attendance, engagement, user events, and course health.',
        'crumbs': [
            {'title': 'Control Center', 'url': reverse('admin_panel')},
            {'title': 'Reports & Analytics'},
        ],
    }

    page_number = request.GET.get('page', 1)

    if tab == 'attendance':
        data = rs.get_attendance_report_data(request.GET.dict())
        paginator = Paginator(data['queryset'], 15)
        context['page_obj'] = paginator.get_page(page_number)
        context['metrics'] = data['metrics']

    elif tab == 'engagement':
        data = rs.get_engagement_report_data(request.GET.dict())
        paginator = Paginator(data['queryset'], 15)
        context['page_obj'] = paginator.get_page(page_number)
        context['metrics'] = data['metrics']

    elif tab == 'user_activity':
        data = rs.get_user_activity_report_data(request.GET.dict())
        paginator = Paginator(data['queryset'], 20)
        context['page_obj'] = paginator.get_page(page_number)
        context['metrics'] = data['metrics']

    elif tab == 'course_performance':
        data = rs.get_course_performance_report_data(request.GET.dict())
        paginator = Paginator(data['items'], 12)
        context['page_obj'] = paginator.get_page(page_number)
        context['metrics'] = data['metrics']

    return render(request, 'accounts/admin/reports.html', context)


@login_required
@admin_permission_required('export_data')
def admin_export_report_csv(request, report_type):
    """Generates a downloadable CSV document for the specified report and audit-logs it."""
    if not check_admin(request.user):
        return HttpResponse("Permission denied", status=403)

    if report_type not in ('attendance', 'engagement', 'user_activity', 'course_performance'):
        return HttpResponse("Invalid report type", status=400)

    import accounts.report_services as rs
    response = rs.export_report_csv(report_type, request.GET.dict())

    log_admin_action(
        request,
        AdminAuditTrail.ACTION_DATA_EXPORTED,
        target={'type': 'Report', 'id': report_type, 'label': f"{report_type.replace('_', ' ').title()} Report (CSV)"},
        changes={
            'report_type': report_type,
            'format': 'csv',
            'filters': request.GET.dict()
        }
    )
    return response


@login_required
@admin_permission_required('export_data')
def admin_export_report_pdf(request, report_type):
    """Renders and downloads a publication-grade PDF document via ReportLab and audit-logs it."""
    if not check_admin(request.user):
        return HttpResponse("Permission denied", status=403)

    if report_type not in ('attendance', 'engagement', 'user_activity', 'course_performance'):
        return HttpResponse("Invalid report type", status=400)

    import accounts.report_services as rs
    response = rs.export_report_pdf(report_type, request.GET.dict())

    log_admin_action(
        request,
        AdminAuditTrail.ACTION_DATA_EXPORTED,
        target={'type': 'Report', 'id': report_type, 'label': f"{report_type.replace('_', ' ').title()} Report (PDF)"},
        changes={
            'report_type': report_type,
            'format': 'pdf',
            'filters': request.GET.dict()
        }
    )
    return response


# ==============================================================================
# SETTINGS & CONFIGURATION VIEWS
# ==============================================================================

@login_required
@admin_permission_required('manage_settings')
def admin_settings(request):
    """
    Campus Configuration & Settings Center:
    Sections: Institution, Academic, Attendance, Security, Email/SMTP.
    """
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    from accounts.settings_services import get_all_settings

    active_section = request.GET.get('section', 'institution').strip().lower()
    if active_section not in ('institution', 'academic', 'attendance', 'security', 'email'):
        active_section = 'institution'

    all_settings = get_all_settings()

    return render(request, 'accounts/admin/settings.html', {
        'active_section': active_section,
        'settings': all_settings,
        'page_title': 'System Settings',
        'page_subtitle': 'Configure institutional branding, academic semesters, facial verification rules, and security policies.',
        'crumbs': [
            {'title': 'Control Center', 'url': reverse('admin_panel')},
            {'title': 'System Settings'},
        ],
    })


@login_required
@require_POST
@admin_permission_required('manage_settings')
def admin_update_settings(request, section):
    """
    Updates key-value settings for a specific section and audit-logs before/after changes.
    """
    if not check_admin(request.user):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied.")
        return redirect('admin_settings')

    from accounts.settings_services import save_section_settings
    from common.models import SiteSetting

    if request.content_type == 'application/json':
        try:
            form_data = json.loads(request.body.decode('utf-8'))
        except Exception:
            form_data = {}
    else:
        form_data = request.POST.dict()
        form_data.pop('csrfmiddlewaretoken', None)

    # Handle file upload for institution logo
    if section == 'institution' and request.FILES.get('logo_file'):
        logo_file = request.FILES['logo_file']
        import os
        from django.conf import settings
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'institution')
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, logo_file.name)
        with open(file_path, 'wb+') as destination:
            for chunk in logo_file.chunks():
                destination.write(chunk)
        form_data['logo_url'] = f"{settings.MEDIA_URL}institution/{logo_file.name}"

    before_changes, after_changes = save_section_settings(section, form_data, user=request.user)

    if before_changes:
        log_admin_action(
            request,
            AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target={'type': 'SiteSetting', 'id': section, 'label': f"Updated {section.title()} Settings"},
            changes={
                'section': section,
                'before': before_changes,
                'after': after_changes
            }
        )
        msg = f"Successfully updated {section.title()} settings."
    else:
        msg = "No changes detected."

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'status': 'success', 'message': msg, 'changes': after_changes})

    messages.success(request, msg)
    return redirect(f"{reverse('admin_settings')}?section={section}")


@login_required
@require_POST
@admin_permission_required('manage_settings')
def admin_semester_crud(request):
    """Academic Semesters CRUD operations (add, delete)."""
    if not check_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    from accounts.settings_services import add_semester, delete_semester

    action = request.POST.get('action', 'add')
    if action == 'add':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        start_date = request.POST.get('start_date', '').strip()
        end_date = request.POST.get('end_date', '').strip()
        is_current = request.POST.get('is_current') in ('true', '1', 'on')

        if not name or not code or not start_date or not end_date:
            return JsonResponse({'status': 'error', 'message': 'All semester fields are required.'}, status=400)

        new_sem = add_semester(name, code, start_date, end_date, is_current=is_current, user=request.user)

        log_admin_action(
            request,
            AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target={'type': 'SiteSetting', 'id': 'academic_semesters', 'label': f"Added Academic Semester: {name} ({code})"},
            changes={'action': 'add_semester', 'semester': new_sem}
        )
        return JsonResponse({'status': 'success', 'message': f"Added semester {name}.", 'semester': new_sem})

    elif action == 'delete':
        sem_id = request.POST.get('id')
        if not sem_id:
            return JsonResponse({'status': 'error', 'message': 'Semester ID required.'}, status=400)

        delete_semester(sem_id, user=request.user)
        log_admin_action(
            request,
            AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target={'type': 'SiteSetting', 'id': 'academic_semesters', 'label': f"Deleted Academic Semester #{sem_id}"},
            changes={'action': 'delete_semester', 'sem_id': sem_id}
        )
        return JsonResponse({'status': 'success', 'message': 'Semester removed.'})

    return JsonResponse({'status': 'error', 'message': 'Unknown action.'}, status=400)


@login_required
@require_POST
@admin_permission_required('manage_settings')
def admin_department_crud(request):
    """Academic Departments CRUD operations (add, delete)."""
    if not check_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    from accounts.settings_services import add_department, delete_department

    action = request.POST.get('action', 'add')
    if action == 'add':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        head = request.POST.get('head', '').strip()

        if not name or not code:
            return JsonResponse({'status': 'error', 'message': 'Department name and code are required.'}, status=400)

        new_dept = add_department(name, code, head=head, user=request.user)

        log_admin_action(
            request,
            AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target={'type': 'SiteSetting', 'id': 'academic_departments', 'label': f"Added Department: {name} ({code})"},
            changes={'action': 'add_department', 'department': new_dept}
        )
        return JsonResponse({'status': 'success', 'message': f"Added department {name}.", 'department': new_dept})

    elif action == 'delete':
        dept_id = request.POST.get('id')
        if not dept_id:
            return JsonResponse({'status': 'error', 'message': 'Department ID required.'}, status=400)

        delete_department(dept_id, user=request.user)
        log_admin_action(
            request,
            AdminAuditTrail.ACTION_SETTINGS_CHANGED,
            target={'type': 'SiteSetting', 'id': 'academic_departments', 'label': f"Deleted Department #{dept_id}"},
            changes={'action': 'delete_department', 'dept_id': dept_id}
        )
        return JsonResponse({'status': 'success', 'message': 'Department removed.'})

    return JsonResponse({'status': 'error', 'message': 'Unknown action.'}, status=400)


@login_required
@require_POST
@admin_permission_required('manage_settings')
def admin_test_email(request):
    """
    Dispatches a live SMTP verification email to test mail server connectivity.
    """
    if not check_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    from accounts.settings_services import send_test_smtp_email

    if request.content_type == 'application/json':
        try:
            body = json.loads(request.body.decode('utf-8'))
            recipient = body.get('recipient_email', '').strip()
        except Exception:
            recipient = ''
    else:
        recipient = request.POST.get('recipient_email', '').strip()

    if not recipient:
        return JsonResponse({'status': 'error', 'message': 'Recipient email address is required.'}, status=400)

    result = send_test_smtp_email(recipient)

    log_admin_action(
        request,
        AdminAuditTrail.ACTION_SETTINGS_CHANGED,
        target={'type': 'SiteSetting', 'id': 'smtp_test', 'label': f"SMTP Email Test to {recipient}"},
        changes={
            'recipient': recipient,
            'success': result['success'],
            'result': result.get('message') or result.get('error')
        }
    )

    if result['success']:
        return JsonResponse({'status': 'success', 'message': result['message']})
    else:
        return JsonResponse({'status': 'error', 'message': f"SMTP Delivery Failed: {result['error']}"}, status=500)


# ==============================================================================
# APPROVALS QUEUE & ANNOUNCEMENTS
# ==============================================================================

@login_required
@admin_permission_required('manage_users')
def admin_approvals(request):
    """
    Unified approval queue for pending classroom enrollments and teacher signups.
    Supports tab filtering, live search, bulk actions, and server-side pagination.
    """
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    tab = request.GET.get('tab', 'all')
    search_query = request.GET.get('search', '').strip()

    # Query pending enrollments
    enrollments_qs = ClassroomMembership.objects.filter(status='pending').select_related(
        'classroom', 'student', 'student__userprofile', 'classroom__teacher'
    ).order_by('-requested_at')

    # Query pending teacher signups
    teachers_qs = User.objects.filter(
        userprofile__user_type='teacher',
        is_active=False
    ).exclude(userprofile__is_deleted=True).select_related('userprofile').order_by('-date_joined')

    # Filter by search query
    if search_query:
        enrollments_qs = enrollments_qs.filter(
            Q(student__username__icontains=search_query) |
            Q(student__email__icontains=search_query) |
            Q(student__first_name__icontains=search_query) |
            Q(student__last_name__icontains=search_query) |
            Q(classroom__title__icontains=search_query) |
            Q(classroom__class_code__icontains=search_query)
        )
        teachers_qs = teachers_qs.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(userprofile__department__icontains=search_query)
        )

    enrollments_count = ClassroomMembership.objects.filter(status='pending').count()
    teachers_count = User.objects.filter(
        userprofile__user_type='teacher',
        is_active=False
    ).exclude(userprofile__is_deleted=True).count()
    total_pending_count = enrollments_count + teachers_count

    # Build queue list based on active tab
    if tab == 'enrollments':
        items = [
            {
                'type': 'enrollment',
                'id': e.id,
                'membership_id': e.id,
                'user': e.student,
                'title': e.classroom.title,
                'subtitle': f"Course Code: {e.classroom.class_code} • Instructor: {e.classroom.teacher.get_full_name() or e.classroom.teacher.username if e.classroom.teacher else 'N/A'}",
                'meta': e.classroom.class_code,
                'department': getattr(getattr(e.classroom.teacher, 'userprofile', None), 'department', ''),
                'date': e.requested_at,
                'raw_obj': e,
            }
            for e in enrollments_qs
        ]
    elif tab == 'teachers':
        items = [
            {
                'type': 'teacher',
                'id': t.id,
                'user_id': t.id,
                'user': t,
                'title': t.get_full_name() or t.username,
                'subtitle': f"@{t.username} • {t.email}",
                'meta': getattr(getattr(t, 'userprofile', None), 'department', 'Faculty'),
                'department': getattr(getattr(t, 'userprofile', None), 'department', ''),
                'date': t.date_joined,
                'raw_obj': t,
            }
            for t in teachers_qs
        ]
    else:  # 'all'
        unified = []
        for e in enrollments_qs:
            unified.append({
                'type': 'enrollment',
                'id': e.id,
                'membership_id': e.id,
                'user': e.student,
                'title': f"Enrollment in {e.classroom.title}",
                'subtitle': f"Student: @{e.student.username} ({e.student.email}) • Code: {e.classroom.class_code}",
                'meta': e.classroom.class_code,
                'department': getattr(getattr(e.classroom.teacher, 'userprofile', None), 'department', ''),
                'date': e.requested_at,
                'raw_obj': e,
            })
        for t in teachers_qs:
            unified.append({
                'type': 'teacher',
                'id': t.id,
                'user_id': t.id,
                'user': t,
                'title': f"Teacher Signup: {t.get_full_name() or t.username}",
                'subtitle': f"@{t.username} • {t.email}",
                'meta': getattr(getattr(t, 'userprofile', None), 'department', 'Faculty'),
                'department': getattr(getattr(t, 'userprofile', None), 'department', ''),
                'date': t.date_joined,
                'raw_obj': t,
            })
        unified.sort(key=lambda x: x['date'] if x['date'] else timezone.now(), reverse=True)
        items = unified

    page_num = request.GET.get('page', 1)
    paginator = Paginator(items, 10)
    try:
        page_obj = paginator.page(page_num)
    except Exception:
        page_obj = paginator.page(1)

    return render(request, 'accounts/admin/approvals.html', {
        'page_obj': page_obj,
        'tab': tab,
        'search_query': search_query,
        'enrollments_count': enrollments_count,
        'teachers_count': teachers_count,
        'total_pending_count': total_pending_count,
    })


@login_required
@require_POST
@admin_permission_required('manage_courses')
def admin_approval_enrollment_action(request, membership_id, action):
    """Approve or reject a classroom enrollment request."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    from django.core.cache import cache
    from accounts.notification_models import Notification

    membership = get_object_or_404(ClassroomMembership.objects.select_related('classroom', 'student'), id=membership_id)

    if action == 'approve':
        old_status = membership.status
        membership.status = 'approved'
        membership.approved_by = request.user
        membership.approved_at = timezone.now()
        membership.save(update_fields=['status', 'approved_by', 'approved_at'])

        log_admin_action(
            request,
            AdminAuditTrail.ACTION_ENROLLMENT_APPROVED,
            target=membership,
            changes={
                'status': {'before': old_status, 'after': 'approved'},
                'student_id': membership.student_id,
                'student_username': membership.student.username,
                'classroom_id': membership.classroom_id,
                'classroom_title': membership.classroom.title,
            }
        )
        try:
            Notification.objects.create(
                recipient=membership.student,
                notification_type='classroom_approved',
                title='Classroom Enrollment Approved',
                message=f"Your request to join {membership.classroom.title} has been approved.",
                link=f"/classrooms/{membership.classroom.id}/",
                related_user=request.user
            )
        except Exception as e:
            logger.warning(f"Failed sending enrollment approval notification: {e}")

        messages.success(request, f"Approved enrollment for @{membership.student.username} in {membership.classroom.title}.")
    elif action == 'reject':
        old_status = membership.status
        membership.status = 'denied'
        membership.save(update_fields=['status'])

        log_admin_action(
            request,
            AdminAuditTrail.ACTION_ENROLLMENT_REJECTED,
            target=membership,
            changes={
                'status': {'before': old_status, 'after': 'denied'},
                'student_id': membership.student_id,
                'student_username': membership.student.username,
                'classroom_id': membership.classroom_id,
                'classroom_title': membership.classroom.title,
            }
        )
        try:
            Notification.objects.create(
                recipient=membership.student,
                notification_type='classroom_denied',
                title='Classroom Enrollment Declined',
                message=f"Your request to join {membership.classroom.title} was declined.",
                related_user=request.user
            )
        except Exception as e:
            logger.warning(f"Failed sending enrollment decline notification: {e}")

        messages.warning(request, f"Declined enrollment for @{membership.student.username} in {membership.classroom.title}.")

    cache.delete('admin_pending_approvals_count')
    return redirect(request.META.get('HTTP_REFERER') or reverse('admin_approvals'))


@login_required
@require_POST
@admin_permission_required('manage_users')
def admin_approval_teacher_action(request, user_id, action):
    """Approve or reject a teacher registration request."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    from django.core.cache import cache
    from accounts.notification_models import Notification

    teacher = get_object_or_404(User.objects.select_related('userprofile'), id=user_id)

    if action == 'approve':
        teacher.is_active = True
        teacher.save(update_fields=['is_active'])

        log_admin_action(
            request,
            AdminAuditTrail.ACTION_USER_ACTIVATED,
            target=teacher,
            changes={
                'action': 'approve_teacher_signup',
                'role': 'teacher',
                'is_active': {'before': False, 'after': True}
            }
        )
        try:
            Notification.objects.create(
                recipient=teacher,
                notification_type='system',
                title='Teacher Account Approved',
                message="Your faculty account registration has been approved. Welcome to Edumi!",
                link="/dashboard/",
                related_user=request.user
            )
        except Exception as e:
            logger.warning(f"Failed sending teacher approval notification: {e}")

        messages.success(request, f"Approved faculty account for @{teacher.username}.")
    elif action == 'reject':
        prof = getattr(teacher, 'userprofile', None)
        if prof:
            prof.is_deleted = True
            prof.save(update_fields=['is_deleted'])
        teacher.is_active = False
        teacher.save(update_fields=['is_active'])

        log_admin_action(
            request,
            AdminAuditTrail.ACTION_USER_SUSPENDED,
            target=teacher,
            changes={
                'action': 'reject_teacher_signup',
                'role': 'teacher',
                'is_active': False,
                'is_deleted': True
            }
        )
        messages.warning(request, f"Rejected faculty registration request for @{teacher.username}.")

    cache.delete('admin_pending_approvals_count')
    return redirect(request.META.get('HTTP_REFERER') or reverse('admin_approvals'))


@login_required
@require_POST
@admin_permission_required('manage_users')
def admin_approvals_bulk(request):
    """
    Bulk approve or reject selected classroom enrollments and teacher signups.
    """
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    from django.core.cache import cache
    from accounts.notification_models import Notification

    bulk_action = request.POST.get('bulk_action', '').strip().lower()
    if bulk_action not in ['approve', 'reject']:
        messages.error(request, "Invalid bulk action specified.")
        return redirect('admin_approvals')

    enrollment_ids = [int(x) for x in request.POST.getlist('enrollment_ids') if x.isdigit()]
    teacher_ids = [int(x) for x in request.POST.getlist('teacher_ids') if x.isdigit()]

    approved_count = 0
    rejected_count = 0
    now = timezone.now()

    # Process enrollments
    if enrollment_ids:
        memberships = ClassroomMembership.objects.filter(id__in=enrollment_ids, status='pending').select_related('classroom', 'student')
        for m in memberships:
            if bulk_action == 'approve':
                m.status = 'approved'
                m.approved_by = request.user
                m.approved_at = now
                m.save(update_fields=['status', 'approved_by', 'approved_at'])
                approved_count += 1
            else:
                m.status = 'denied'
                m.save(update_fields=['status'])
                rejected_count += 1

    # Process teachers
    if teacher_ids:
        teachers = User.objects.filter(id__in=teacher_ids, userprofile__user_type='teacher', is_active=False).select_related('userprofile')
        for t in teachers:
            if bulk_action == 'approve':
                t.is_active = True
                t.save(update_fields=['is_active'])
                approved_count += 1
            else:
                prof = getattr(t, 'userprofile', None)
                if prof:
                    prof.is_deleted = True
                    prof.save(update_fields=['is_deleted'])
                t.is_active = False
                t.save(update_fields=['is_active'])
                rejected_count += 1

    # Log comprehensive bulk action audit entry
    log_admin_action(
        request,
        AdminAuditTrail.ACTION_BULK_ACTION,
        target={'type': 'ApprovalsQueue', 'id': 0, 'label': f"Bulk {bulk_action.title()} on Approvals Queue"},
        changes={
            'bulk_action': bulk_action,
            'enrollment_ids': enrollment_ids,
            'teacher_ids': teacher_ids,
            'approved_count': approved_count,
            'rejected_count': rejected_count,
        }
    )

    cache.delete('admin_pending_approvals_count')
    if bulk_action == 'approve':
        messages.success(request, f"Bulk approved {approved_count} pending request(s).")
    else:
        messages.warning(request, f"Bulk rejected {rejected_count} pending request(s).")

    return redirect(reverse('admin_approvals') + f"?tab={request.POST.get('tab', 'all')}")


@login_required
@admin_permission_required('manage_settings')
def admin_announcements(request):
    """
    Campus Announcements control center:
    - View history and active broadcast metrics
    - Compose and dispatch real-time targeted or campus-wide announcements
    - Schedule future broadcasts
    """
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    from common.models import Announcement
    from common.announcement_service import deliver_announcement

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        body = request.POST.get('body', '').strip()
        audience = request.POST.get('audience', Announcement.AUDIENCE_ALL)
        target_id = request.POST.get('target_id', '').strip() or None
        schedule_str = request.POST.get('scheduled_at', '').strip()

        if not title or not body:
            messages.error(request, "Both announcement title and body are required.")
            return redirect('admin_announcements')

        target_label = ''
        if audience == Announcement.AUDIENCE_COURSE and target_id:
            cr = Classroom.objects.filter(id=target_id).first()
            if cr:
                target_label = f"{cr.title} ({cr.class_code})"
        elif audience == Announcement.AUDIENCE_DEPARTMENT and target_id:
            target_label = f"Dept: {target_id}"

        scheduled_dt = None
        if schedule_str:
            try:
                scheduled_dt = datetime.fromisoformat(schedule_str)
                if timezone.is_naive(scheduled_dt):
                    scheduled_dt = timezone.make_aware(scheduled_dt, timezone.get_current_timezone())
            except Exception as e:
                logger.warning(f"Invalid scheduled_at date string '{schedule_str}': {e}")
                scheduled_dt = None

        now = timezone.now()
        is_future = scheduled_dt is not None and scheduled_dt > now

        announcement = Announcement.objects.create(
            title=title,
            body=body,
            audience=audience,
            target_id=target_id,
            target_label=target_label,
            created_by=request.user,
            scheduled_at=scheduled_dt,
            is_sent=False
        )

        if not is_future:
            delivered_count = deliver_announcement(announcement, sender=request.user)
            log_admin_action(
                request,
                AdminAuditTrail.ACTION_BULK_ACTION,
                target={'type': 'Announcement', 'id': announcement.id, 'label': announcement.title},
                changes={
                    'action': 'broadcast_announcement',
                    'title': announcement.title,
                    'audience': audience,
                    'target_label': target_label,
                    'recipient_count': delivered_count,
                    'scheduled': False,
                }
            )
            messages.success(request, f"Announcement broadcasted to {delivered_count} recipient(s) successfully.")
        else:
            log_admin_action(
                request,
                AdminAuditTrail.ACTION_SETTINGS_CHANGED,
                target={'type': 'Announcement', 'id': announcement.id, 'label': announcement.title},
                changes={
                    'action': 'schedule_announcement',
                    'title': announcement.title,
                    'audience': audience,
                    'scheduled_at': scheduled_dt.isoformat(),
                }
            )
            messages.success(request, f"Announcement scheduled for delivery on {scheduled_dt.strftime('%b %d, %Y at %H:%M')}.")

        return redirect('admin_announcements')

    # GET: List announcements and stats
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('search', '').strip()

    qs = Announcement.objects.filter(is_deleted=False).select_related('created_by').order_by('-created_at')

    if status_filter == 'sent':
        qs = qs.filter(is_sent=True)
    elif status_filter == 'scheduled':
        qs = qs.filter(is_sent=False)

    if search_query:
        qs = qs.filter(
            Q(title__icontains=search_query) |
            Q(body__icontains=search_query) |
            Q(target_label__icontains=search_query)
        )

    all_announcements = Announcement.objects.filter(is_deleted=False)
    total_announcements = all_announcements.count()
    sent_count = all_announcements.filter(is_sent=True).count()
    scheduled_count = all_announcements.filter(is_sent=False).count()
    total_recipients = all_announcements.aggregate(total=models.Sum('recipient_count'))['total'] or 0

    courses = Classroom.objects.filter(is_active=True).values('id', 'title', 'class_code').order_by('title')
    departments = list(UserProfile.objects.exclude(department='').values_list('department', flat=True).distinct())
    departments = [d for d in departments if d]

    page_num = request.GET.get('page', 1)
    paginator = Paginator(qs, 15)
    try:
        page_obj = paginator.page(page_num)
    except Exception:
        page_obj = paginator.page(1)

    return render(request, 'accounts/admin/announcements.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'total_announcements': total_announcements,
        'sent_count': sent_count,
        'scheduled_count': scheduled_count,
        'total_recipients': total_recipients,
        'courses': courses,
        'departments': departments,
    })


@login_required
@require_POST
@admin_permission_required('manage_settings')
def admin_announcement_send_now(request, announcement_id):
    """Trigger immediate delivery of a previously scheduled announcement."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    from common.models import Announcement
    from common.announcement_service import deliver_announcement

    announcement = get_object_or_404(Announcement, id=announcement_id, is_deleted=False)
    if announcement.is_sent:
        messages.info(request, "This announcement has already been delivered.")
        return redirect('admin_announcements')

    delivered_count = deliver_announcement(announcement, sender=request.user)

    log_admin_action(
        request,
        AdminAuditTrail.ACTION_BULK_ACTION,
        target={'type': 'Announcement', 'id': announcement.id, 'label': announcement.title},
        changes={
            'action': 'send_now',
            'title': announcement.title,
            'audience': announcement.audience,
            'recipient_count': delivered_count
        }
    )

    messages.success(request, f"Announcement dispatched immediately to {delivered_count} recipient(s).")
    return redirect('admin_announcements')


@login_required
@require_POST
@admin_permission_required('manage_settings')
def admin_announcement_delete(request, announcement_id):
    """Soft-delete an announcement from the archive/queue."""
    if not check_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect('admin_panel')

    from common.models import Announcement

    announcement = get_object_or_404(Announcement, id=announcement_id)
    announcement.is_deleted = True
    announcement.save(update_fields=['is_deleted'])

    log_admin_action(
        request,
        AdminAuditTrail.ACTION_USER_DELETED,
        target={'type': 'Announcement', 'id': announcement.id, 'label': announcement.title},
        changes={'action': 'delete_announcement', 'title': announcement.title}
    )

    messages.success(request, f"Announcement '{announcement.title}' deleted successfully.")
    return redirect('admin_announcements')





# ==============================================================================
# ROLES & PERMISSIONS MANAGEMENT
# ==============================================================================

@login_required
@admin_permission_required('manage_settings')
def admin_roles(request):
    """
    Roles and Permissions control page:
    - View and edit the granular permission matrix across all administrative roles
    - Create new custom administrative roles
    - Assign administrative roles to admin users with full audit trail logging
    """
    from common.models import AdminRole
    AdminRole.seed_default_roles()

    roles = list(AdminRole.objects.all().order_by('name'))
    admin_users = list(
        User.objects.filter(
            Q(userprofile__user_type='admin') | Q(is_superuser=True) | Q(is_staff=True)
        ).distinct().select_related('userprofile', 'userprofile__admin_role').order_by('username')
    )

    permission_flags = [
        ('manage_users', 'Manage Users', 'Create, edit, suspend, import, and delete platform users'),
        ('manage_courses', 'Manage Courses', 'Create, configure, archive classrooms, and review student enrollments'),
        ('manage_sessions', 'Manage Live Sessions', 'Schedule classes, monitor live rooms, and terminate sessions'),
        ('view_audit', 'View Security & Audit', 'Access audit logs, event feeds, and telemetry logs'),
        ('manage_settings', 'Manage Settings & Governance', 'Configure institution settings, policies, email diagnostics, and roles'),
        ('manage_cameras', 'Manage Cameras & Media', 'Control camera fleet, RTSP links, and media recordings library'),
        ('export_data', 'Export Data & Reports', 'Generate and download CSV and PDF reports'),
    ]

    return render(request, 'accounts/admin/admin_roles.html', {
        'roles': roles,
        'admin_users': admin_users,
        'permission_flags': permission_flags,
    })


@login_required
@require_POST
@admin_permission_required('manage_settings')
def admin_role_update(request):
    """Update permissions for an existing role or create a new custom role."""
    from common.models import AdminRole

    action = request.POST.get('action', 'update')
    flags = ['manage_users', 'manage_courses', 'manage_sessions', 'view_audit', 'manage_settings', 'manage_cameras', 'export_data']

    if action == 'create':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, 'Role name is required.')
            return redirect('admin_roles')

        if AdminRole.objects.filter(name__iexact=name).exists():
            messages.error(request, f"A role named '{name}' already exists.")
            return redirect('admin_roles')

        role_data = {flag: request.POST.get(flag) in ['on', 'true', '1'] for flag in flags}
        new_role = AdminRole.objects.create(name=name, description=description, is_system_role=False, **role_data)

        log_admin_action(
            request,
            AdminAuditTrail.ACTION_ROLE_CHANGED,
            target={'type': 'AdminRole', 'id': new_role.id, 'label': f'Created Role {new_role.name}'},
            changes={'action': 'create_role', 'role': new_role.name, 'permissions': role_data}
        )
        messages.success(request, f"Custom role '{new_role.name}' created successfully.")
        return redirect('admin_roles')

    # Update role
    role_id = request.POST.get('role_id')
    role = get_object_or_404(AdminRole, id=role_id)

    before = {flag: getattr(role, flag) for flag in flags}
    after = {flag: request.POST.get(flag) in ['on', 'true', '1'] for flag in flags}

    for flag, val in after.items():
        setattr(role, flag, val)
    role.save()

    log_admin_action(
        request,
        AdminAuditTrail.ACTION_SETTINGS_CHANGED,
        target={'type': 'AdminRole', 'id': role.id, 'label': f'Updated Role {role.name}'},
        changes={'role': role.name, 'before': before, 'after': after}
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or is_ajax_request(request):
        return JsonResponse({'status': 'success', 'message': f"Role '{role.name}' updated successfully."})

    messages.success(request, f"Permissions for role '{role.name}' updated successfully.")
    return redirect('admin_roles')


@login_required
@require_POST
@admin_permission_required('manage_users')
def admin_assign_user_role(request):
    """Assign an AdminRole to an administrator user with full audit logging."""
    from common.models import AdminRole
    user_id = request.POST.get('user_id')
    role_id = request.POST.get('role_id')

    target_user = get_object_or_404(User, id=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    old_role_name = profile.admin_role.name if profile.admin_role else 'None'
    new_role = AdminRole.objects.filter(id=role_id).first() if role_id else None
    new_role_name = new_role.name if new_role else 'None'

    profile.admin_role = new_role
    if profile.user_type != 'admin':
        profile.user_type = 'admin'
    profile.save(update_fields=['admin_role', 'user_type'])

    log_admin_action(
        request,
        AdminAuditTrail.ACTION_ROLE_CHANGED,
        target=target_user,
        changes={
            'action': 'assign_admin_role',
            'user': target_user.username,
            'role': {'before': old_role_name, 'after': new_role_name}
        }
    )

    msg = f"Assigned role '{new_role_name}' to @{target_user.username}."
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or is_ajax_request(request):
        return JsonResponse({'status': 'success', 'message': msg})

    messages.success(request, msg)
    return redirect('admin_roles')


# =========================================================
# GLOBAL COMMAND PALETTE (CTRL+K) API ENDPOINT
# =========================================================
@login_required
def admin_command_palette_api(request):
    """
    Search endpoint powering the enterprise Command Palette (Ctrl+K).
    Returns instant matching Quick Actions, Users, Courses, and Live Sessions.
    """
    if not check_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Administrator access required.'}, status=403)

    q = request.GET.get('q', '').strip()

    # Pre-defined high-frequency administrative quick actions
    all_actions = [
        {
            'id': 'action_add_user',
            'title': 'Add New User',
            'subtitle': 'Create a new student, teacher, or administrator account',
            'url': '/admin/users/?action=new',
            'icon': 'user-plus',
            'category': 'Quick Actions',
            'badge': 'Action',
        },
        {
            'id': 'action_import_users',
            'title': 'Import Users (CSV)',
            'subtitle': 'Launch the 3-step bulk CSV user onboarding wizard',
            'url': '/admin/users/?open_import=1',
            'icon': 'upload-cloud',
            'category': 'Quick Actions',
            'badge': 'Wizard',
        },
        {
            'id': 'action_export_users',
            'title': 'Export Users (CSV)',
            'subtitle': 'Download platform user roster with enrollment and attendance',
            'url': '/admin/export/users/',
            'icon': 'download',
            'category': 'Quick Actions',
            'badge': 'Export',
        },
        {
            'id': 'action_create_course',
            'title': 'Create New Course',
            'subtitle': 'Add a new classroom subject, syllabus, and instructor',
            'url': '/admin/classrooms/?action=new',
            'icon': 'book-plus',
            'category': 'Quick Actions',
            'badge': 'Course',
        },
        {
            'id': 'action_schedule_session',
            'title': 'Schedule Live Session',
            'subtitle': 'Schedule a WebRTC/LiveKit online class or conference',
            'url': '/admin/meetings/?action=schedule',
            'icon': 'video',
            'category': 'Quick Actions',
            'badge': 'Session',
        },
        {
            'id': 'action_live_monitor',
            'title': 'Live Monitor Control Room',
            'subtitle': 'Real-time telemetry of live classrooms & force-end controls',
            'url': '/admin/live-monitor/',
            'icon': 'activity',
            'category': 'Quick Actions',
            'badge': 'Control Room',
        },
        {
            'id': 'action_security_audit',
            'title': 'Security & Audit Trail',
            'subtitle': 'Immutable administrative action log with before/after diffs',
            'url': '/admin/security-audit/',
            'icon': 'shield-check',
            'category': 'Quick Actions',
            'badge': 'Security',
        },
        {
            'id': 'action_system_health',
            'title': 'System Health & Infrastructure',
            'subtitle': 'Telemetry for LiveKit SFU, Redis, Celery, DB, and Storage',
            'url': '/admin/system-health/',
            'icon': 'cpu',
            'category': 'Quick Actions',
            'badge': 'Infra',
        },
        {
            'id': 'action_reports',
            'title': 'Reports & Analytics',
            'subtitle': 'Generate and export Attendance, Engagement, and Course PDFs',
            'url': '/admin/reports/',
            'icon': 'bar-chart-3',
            'category': 'Quick Actions',
            'badge': 'Analytics',
        },
        {
            'id': 'action_approvals',
            'title': 'Pending Approvals Queue',
            'subtitle': 'Review course enrollment and teacher signup requests',
            'url': '/admin/approvals/',
            'icon': 'check-circle-2',
            'category': 'Quick Actions',
            'badge': 'Queue',
        },
        {
            'id': 'action_announcements',
            'title': 'Campus Announcements',
            'subtitle': 'Compose and dispatch real-time cohort broadcast notifications',
            'url': '/admin/announcements/',
            'icon': 'bell-ring',
            'category': 'Quick Actions',
            'badge': 'Broadcast',
        },
        {
            'id': 'action_roles',
            'title': 'Roles & Permissions Matrix',
            'subtitle': 'Manage granular RBAC capabilities and role assignments',
            'url': '/admin/roles/',
            'icon': 'key',
            'category': 'Quick Actions',
            'badge': 'RBAC',
        },
        {
            'id': 'action_settings',
            'title': 'Platform Settings',
            'subtitle': 'Configure Institution, Academic, Attendance & Security settings',
            'url': '/admin/settings/',
            'icon': 'settings',
            'category': 'Quick Actions',
            'badge': 'Governance',
        },
    ]

    items = []

    # 1. Filter Quick Actions
    if q:
        q_lower = q.lower()
        matched_actions = [
            a for a in all_actions
            if q_lower in a['title'].lower() or q_lower in a['subtitle'].lower()
        ]
        items.extend(matched_actions[:5])
    else:
        # Default top actions when search is empty
        items.extend(all_actions[:5])

    # 2. Search Users
    from django.db.models import Q
    users_qs = User.objects.select_related('userprofile').exclude(username__startswith='test_')
    if q:
        users_qs = users_qs.filter(
            Q(username__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q)
        )
    else:
        users_qs = users_qs.filter(is_active=True)

    for u in users_qs.order_by('-date_joined')[:5]:
        profile = getattr(u, 'userprofile', None)
        role = getattr(profile, 'user_type', 'user').capitalize() if profile else 'User'
        dept = getattr(profile, 'department', '') if profile else ''
        display_name = u.get_full_name() or u.username
        items.append({
            'id': f'user_{u.id}',
            'title': f"{display_name} (@{u.username})",
            'subtitle': f"{role}" + (f" • {dept}" if dept else "") + f" • {u.email}",
            'url': f'/admin/users/{u.id}/',
            'icon': 'user',
            'category': 'Users',
            'badge': role,
        })

    # 3. Search Courses / Classrooms
    from academics.models import Classroom
    courses_qs = Classroom.objects.select_related('teacher')
    if q:
        courses_qs = courses_qs.filter(
            Q(title__icontains=q) |
            Q(class_code__icontains=q) |
            Q(description__icontains=q)
        )
    else:
        courses_qs = courses_qs.filter(is_active=True)

    for c in courses_qs.order_by('-created_at')[:5]:
        teacher_name = c.teacher.get_full_name() or c.teacher.username if c.teacher else 'Unassigned'
        items.append({
            'id': f'course_{c.id}',
            'title': f"{c.title} ({c.class_code})",
            'subtitle': f"Instructor: {teacher_name} • Status: {'Active' if c.is_active else 'Archived'}",
            'url': f'/admin/classrooms/{c.id}/',
            'icon': 'book-open',
            'category': 'Courses',
            'badge': 'Course',
        })

    # 4. Search Live Sessions / Meetings
    from meetings.models import Meeting
    meetings_qs = Meeting.objects.select_related('classroom', 'teacher')
    if q:
        meetings_qs = meetings_qs.filter(
            Q(title__icontains=q) |
            Q(meeting_code__icontains=q)
        )

    for m in meetings_qs.order_by('-scheduled_time')[:5]:
        course_name = m.classroom.title if m.classroom else 'General Session'
        status_label = m.status.capitalize() if hasattr(m, 'status') else 'Session'
        items.append({
            'id': f'meeting_{m.id}',
            'title': m.title,
            'subtitle': f"#{m.meeting_code} • {course_name} • {status_label}",
            'url': f'/admin/meetings/{m.id}/',
            'icon': 'video',
            'category': 'Live Sessions',
            'badge': status_label,
        })

    return JsonResponse({'status': 'success', 'query': q, 'count': len(items), 'results': items})


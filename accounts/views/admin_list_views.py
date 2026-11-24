"""
accounts/admin_list_views.py
Admin list and 360 management views for Teachers, Courses/Classrooms, and Classes/Meetings.
All views rely strictly on real database statistics without placeholders.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from meetings.models import Meeting, Classroom, ClassroomMembership, MeetingParticipant
from accounts.models import UserProfile
from accounts.admin_services import (
    get_teachers_management_list,
    get_classroom_360_data,
    get_meeting_360_data,
)
from accounts.views.admin_views import check_admin
from accounts.permissions import admin_permission_required

User = get_user_model()


@login_required
@admin_permission_required('manage_users')
def admin_all_users(request):
    """Show all users with details - redirects to the enhanced user management interface."""
    return redirect('user_management')


@login_required
@admin_permission_required('manage_users')
def admin_all_students(request):
    """Filter user management to students only."""
    return redirect('/admin/users/?role=student')


@login_required
@admin_permission_required('manage_users')
def admin_all_teachers(request):
    """
    Teacher Management page:
    Displays all registered teachers, their department, managed classrooms,
    hosted meetings, and enrolled student counts.
    """
    if not check_admin(request.user):
        return redirect('login')

    search_query = request.GET.get('q', '').strip()
    dept_filter = request.GET.get('dept', 'all').strip()

    teachers_data = get_teachers_management_list(search_query=search_query, dept_filter=dept_filter)

    # Distinct departments for filter dropdown
    departments = list(
        User.objects.filter(userprofile__user_type='teacher', userprofile__department__isnull=False)
        .exclude(userprofile__department='')
        .values_list('userprofile__department', flat=True)
        .distinct()
    )

    total_count = User.objects.filter(userprofile__user_type='teacher').count()
    active_count = User.objects.filter(userprofile__user_type='teacher', is_active=True).count()
    total_classrooms = Classroom.objects.filter(teacher__userprofile__user_type='teacher').count()
    total_meetings = Meeting.objects.filter(teacher__userprofile__user_type='teacher').count()

    # Pagination: 12 teachers per page (grid layout)
    from django.core.paginator import Paginator
    paginator = Paginator(teachers_data, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/admin/admin_all_teachers.html', {
        'teachers_data': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'active_count': active_count,
        'total_classrooms': total_classrooms,
        'total_meetings': total_meetings,
        'departments': departments,
        'selected_dept': dept_filter,
        'search_query': search_query,
        'breadcrumb_list': [
            {'title': 'Home', 'url': 'admin_panel'},
            {'title': 'Teacher Roster'},
        ],
    })


@login_required
@admin_permission_required('manage_courses')
def admin_all_classrooms(request):
    """
    Courses & Classroom Catalog page:
    Displays all courses/classrooms, teacher, enrolled count, pending requests,
    calculated attendance %, last session date, and status.
    Supports card view vs table view, and filtering by status, instructor, and department.
    """
    if not check_admin(request.user):
        return redirect('login')

    from django.db.models import Max
    from attendance.models import AttendanceRecord

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all').lower()
    teacher_filter = request.GET.get('teacher', 'all').strip()
    dept_filter = request.GET.get('dept', 'all').strip()
    view_mode = request.GET.get('view', 'cards').lower()

    classrooms_qs = Classroom.objects.select_related('teacher', 'teacher__userprofile').annotate(
        approved_students=Count('memberships', filter=Q(memberships__status='approved'), distinct=True),
        pending_students=Count('memberships', filter=Q(memberships__status='pending'), distinct=True),
        meetings_count=Count('meetings', distinct=True),
        assignments_count=Count('assignments', distinct=True),
        quizzes_count=Count('quizzes', distinct=True),
        materials_count=Count('study_materials', distinct=True),
    ).order_by('-created_at')

    # Status filter
    if status_filter == 'active':
        classrooms_qs = classrooms_qs.filter(is_active=True)
    elif status_filter in ['archived', 'inactive']:
        classrooms_qs = classrooms_qs.filter(is_active=False)

    # Teacher filter
    if teacher_filter and teacher_filter != 'all':
        if teacher_filter.isdigit():
            classrooms_qs = classrooms_qs.filter(teacher_id=int(teacher_filter))
        else:
            classrooms_qs = classrooms_qs.filter(teacher__username=teacher_filter)

    # Department filter
    if dept_filter and dept_filter != 'all':
        classrooms_qs = classrooms_qs.filter(teacher__userprofile__department=dept_filter)

    # Search query
    if search_query:
        classrooms_qs = classrooms_qs.filter(
            Q(title__icontains=search_query) |
            Q(class_code__icontains=search_query) |
            Q(teacher__username__icontains=search_query) |
            Q(teacher__first_name__icontains=search_query) |
            Q(teacher__last_name__icontains=search_query)
        )

    total_classrooms = Classroom.objects.count()
    active_classrooms = Classroom.objects.filter(is_active=True).count()
    archived_classrooms = Classroom.objects.filter(is_active=False).count()
    total_enrollments = ClassroomMembership.objects.filter(status='approved').count()

    teachers = User.objects.filter(userprofile__user_type='teacher').order_by('first_name', 'last_name', 'username')
    departments = list(
        UserProfile.objects.filter(user_type='teacher')
        .exclude(department__isnull=True)
        .exclude(department='')
        .values_list('department', flat=True)
        .distinct()
        .order_by('department')
    )

    # Pagination: 12 classrooms per page
    from django.core.paginator import Paginator
    paginator = Paginator(classrooms_qs, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Compute genuine per-course metrics for items on the current page
    classroom_ids = [c.id for c in page_obj]
    latest_meetings = (
        Meeting.objects.filter(classroom_id__in=classroom_ids)
        .values('classroom_id')
        .annotate(latest_time=Max('scheduled_time'))
    )
    latest_map = {item['classroom_id']: item['latest_time'] for item in latest_meetings}

    att_stats = (
        AttendanceRecord.objects.filter(classroom_id__in=classroom_ids)
        .values('classroom_id')
        .annotate(
            total=Count('id'),
            present=Count('id', filter=Q(status='present'))
        )
    )
    att_map = {
        item['classroom_id']: round((item['present'] / item['total'] * 100)) if item['total'] > 0 else None
        for item in att_stats
    }

    part_stats = (
        MeetingParticipant.objects.filter(meeting__classroom_id__in=classroom_ids)
        .values('meeting__classroom_id')
        .annotate(total_participants=Count('id', distinct=True))
    )
    part_map = {item['meeting__classroom_id']: item['total_participants'] for item in part_stats}

    for cr in page_obj:
        cr.last_session_date = latest_map.get(cr.id)
        att_pct = att_map.get(cr.id)
        if att_pct is not None:
            cr.attendance_rate = f"{att_pct}%"
            cr.attendance_pct_val = att_pct
        elif cr.approved_students > 0 and cr.meetings_count > 0:
            participants = part_map.get(cr.id, 0)
            expected = cr.approved_students * cr.meetings_count
            calc_val = min(100, round(participants / expected * 100)) if expected else 0
            cr.attendance_rate = f"{calc_val}%"
            cr.attendance_pct_val = calc_val
        else:
            cr.attendance_rate = "—"
            cr.attendance_pct_val = 0

    return render(request, 'accounts/admin/admin_all_classrooms.html', {
        'classrooms': page_obj,
        'page_obj': page_obj,
        'teachers': teachers,
        'departments': departments,
        'total_classrooms': total_classrooms,
        'active_classrooms': active_classrooms,
        'archived_classrooms': archived_classrooms,
        'total_enrollments': total_enrollments,
        'search_query': search_query,
        'status_filter': status_filter,
        'teacher_filter': teacher_filter,
        'dept_filter': dept_filter,
        'view_mode': view_mode,
        'breadcrumb_list': [
            {'title': 'Home', 'url': 'admin_panel'},
            {'title': 'Courses'},
        ],
    })


@login_required
@admin_permission_required('manage_courses')
def admin_classroom_detail(request, classroom_id):
    """Classroom 360 Detail View: teacher, students, meetings, study materials, and assignments."""
    if not check_admin(request.user):
        return redirect('login')

    classroom_data = get_classroom_360_data(classroom_id)
    return render(request, 'accounts/admin/classroom_detail.html', {
        **classroom_data,
        'breadcrumb_list': [
            {'title': 'Home', 'url': 'admin_panel'},
            {'title': 'Courses', 'url': 'admin_all_classrooms'},
            {'title': classroom_data['classroom'].title},
        ],
    })


@login_required
@admin_permission_required('manage_sessions')
def admin_all_meetings(request):
    """
    Live Sessions Management page:
    Displays all live and scheduled video sessions, host teacher, classroom, duration,
    attendee counts, and attendance %.
    Supports tabs: Live now / Upcoming / Past / All.
    """
    if not check_admin(request.user):
        return redirect('login')

    from attendance.models import AttendanceRecord

    search_query = request.GET.get('q', '').strip()
    tab = request.GET.get('tab', 'all').lower()
    status_filter = request.GET.get('status', '').lower()

    now = timezone.now()

    # Auto-clean any stale live meetings
    for m in Meeting.objects.filter(status='live'):
        if m.is_expired():
            m.status = 'ended'
            m.ended_at = now
            m.save(update_fields=['status', 'ended_at'])

    meetings_qs = Meeting.objects.select_related(
        'teacher', 'teacher__userprofile', 'classroom'
    ).annotate(
        attendees_count=Count('participants', distinct=True)
    ).order_by('-scheduled_time')

    # Tab filtering
    if tab == 'live' or status_filter == 'live':
        meetings_qs = meetings_qs.filter(status='live')
        tab = 'live'
    elif tab == 'upcoming' or status_filter == 'scheduled':
        meetings_qs = meetings_qs.filter(status='scheduled', scheduled_time__gte=now)
        tab = 'upcoming'
    elif tab == 'past' or status_filter in ['ended', 'cancelled']:
        meetings_qs = meetings_qs.filter(Q(status='ended') | Q(status='cancelled') | Q(scheduled_time__lt=now, status='scheduled'))
        tab = 'past'
    else:
        tab = 'all'

    if search_query:
        meetings_qs = meetings_qs.filter(
            Q(title__icontains=search_query) |
            Q(meeting_code__icontains=search_query) |
            Q(teacher__username__icontains=search_query) |
            Q(classroom__title__icontains=search_query)
        )

    total_count = Meeting.objects.count()
    live_count = Meeting.objects.filter(status='live').count()
    scheduled_count = Meeting.objects.filter(status='scheduled', scheduled_time__gte=now).count()
    ended_count = Meeting.objects.filter(Q(status='ended') | Q(status='cancelled') | Q(scheduled_time__lt=now, status='scheduled')).count()

    # Pagination: 15 meetings per page
    from django.core.paginator import Paginator
    paginator = Paginator(meetings_qs, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Compute duration and attendance % for current page
    meeting_ids = [m.id for m in page_obj]
    meeting_att_counts = {
        item['meeting_id']: item['present_count']
        for item in AttendanceRecord.objects.filter(meeting_id__in=meeting_ids, status='present')
        .values('meeting_id')
        .annotate(present_count=Count('id'))
    }

    for m in page_obj:
        # Formatted duration
        if m.started_at and m.ended_at:
            total_sec = max(0, int((m.ended_at - m.started_at).total_seconds()))
            hrs = total_sec // 3600
            mins = (total_sec % 3600) // 60
            secs = total_sec % 60
            if hrs > 0:
                m.duration_formatted = f"{hrs}h {mins}m"
            elif mins > 0:
                m.duration_formatted = f"{mins}m {secs}s"
            else:
                m.duration_formatted = f"{secs}s"
        elif m.duration_minutes:
            m.duration_formatted = f"{m.duration_minutes}m"
        else:
            m.duration_formatted = "—"

        # Attendance %
        enrolled = 0
        if m.classroom:
            enrolled = m.classroom.memberships.filter(status='approved').count()

        if enrolled > 0:
            present_records = meeting_att_counts.get(m.id, 0)
            if present_records > 0:
                pct = round((present_records / enrolled) * 100)
            else:
                pct = round((m.attendees_count / enrolled) * 100) if m.attendees_count else 0
            m.attendance_pct = f"{min(100, pct)}%"
        elif m.attendees_count > 0:
            m.attendance_pct = "100%"
        else:
            m.attendance_pct = "—"

    teachers = User.objects.filter(userprofile__user_type='teacher').order_by('first_name', 'last_name', 'username')
    classrooms = Classroom.objects.filter(is_active=True).order_by('title')

    return render(request, 'accounts/admin/admin_all_meetings.html', {
        'meetings': page_obj,
        'page_obj': page_obj,
        'teachers': teachers,
        'classrooms': classrooms,
        'total_count': total_count,
        'live_count': live_count,
        'scheduled_count': scheduled_count,
        'ended_count': ended_count,
        'active_tab': tab,
        'status_filter': status_filter,
        'search_query': search_query,
        'breadcrumb_list': [
            {'title': 'Home', 'url': 'admin_panel'},
            {'title': 'Live Sessions'},
        ],
    })


@login_required
@admin_permission_required('manage_sessions')
def admin_live_monitor(request):
    """
    Live Sessions Monitor Page:
    Real-time command center showing all currently active live sessions, connected participants,
    camera status, and force-end termination capabilities.
    """
    if not check_admin(request.user):
        return redirect('login')

    now = timezone.now()
    # Auto-clean expired sessions first
    for m in Meeting.objects.filter(status='live'):
        if m.is_expired():
            m.status = 'ended'
            m.ended_at = now
            m.save(update_fields=['status', 'ended_at'])

    live_rooms = list(Meeting.objects.filter(status='live').select_related(
        'teacher', 'teacher__userprofile', 'classroom'
    ).order_by('-started_at', '-scheduled_time'))

    # Load active participants for each room
    for room in live_rooms:
        room.active_participants = list(MeetingParticipant.objects.filter(
            meeting=room, is_active=True
        ).select_related('user', 'user__userprofile').order_by('user__first_name', 'user__username'))

        if room.started_at:
            elapsed_sec = max(0, int((now - room.started_at).total_seconds()))
            hrs = elapsed_sec // 3600
            mins = (elapsed_sec % 3600) // 60
            secs = elapsed_sec % 60
            room.elapsed_duration = f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m {secs}s"
        else:
            room.elapsed_duration = "Just started"

    return render(request, 'accounts/admin/admin_live_monitor.html', {
        'live_rooms': live_rooms,
        'live_count': len(live_rooms),
        'now': now,
        'breadcrumb_list': [
            {'title': 'Home', 'url': 'admin_panel'},
            {'title': 'Live Sessions', 'url': 'admin_all_meetings'},
            {'title': 'Live Monitor'},
        ],
    })


@login_required
@admin_permission_required('manage_sessions')
def admin_meeting_detail(request, meeting_id):
    """Meeting Detail & Attendance View: participant attendance log and verification details."""
    if not check_admin(request.user):
        return redirect('login')

    meeting_data = get_meeting_360_data(meeting_id)
    return render(request, 'accounts/admin/meeting_detail.html', {
        **meeting_data,
        'breadcrumb_list': [
            {'title': 'Home', 'url': 'admin_panel'},
            {'title': 'Meetings', 'url': 'admin_all_meetings'},
            {'title': meeting_data['meeting'].title},
        ],
    })


@login_required
@admin_permission_required('manage_sessions')
def admin_live_meetings(request):
    """Filter meeting management to live meetings only."""
    return redirect('/admin/meetings/?status=live')


@login_required
@admin_permission_required('manage_cameras')
def admin_all_cameras(request):
    """Redirect to the unified camera fleet dashboard."""
    return redirect('admin_dashboard')

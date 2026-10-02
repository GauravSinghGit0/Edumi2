"""
accounts/admin_list_views.py
Admin list and 360 management views for Teachers, Courses/Classrooms, and Classes/Meetings.
All views rely strictly on real database statistics without placeholders.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from meetings.models import Meeting, Classroom, ClassroomMembership
from accounts.admin_services import (
    get_teachers_management_list,
    get_classroom_360_data,
    get_meeting_360_data,
)

User = get_user_model()


def check_admin(user):
    """Enforce strict admin authorization."""
    return user.is_authenticated and (user.is_superuser or (hasattr(user, 'userprofile') and user.userprofile.user_type == 'admin'))


@login_required
def admin_all_users(request):
    """Show all users with details - redirects to the enhanced user management interface."""
    return redirect('user_management')


@login_required
def admin_all_students(request):
    """Filter user management to students only."""
    return redirect('/admin/users/?role=student')


@login_required
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
    total_classrooms = Classroom.objects.count()
    total_meetings = Meeting.objects.count()

    return render(request, 'accounts/admin/admin_all_teachers.html', {
        'teachers_data': teachers_data,
        'total_count': total_count,
        'active_count': active_count,
        'total_classrooms': total_classrooms,
        'total_meetings': total_meetings,
        'departments': departments,
        'selected_dept': dept_filter,
        'search_query': search_query,
    })


@login_required
def admin_all_classrooms(request):
    """
    Course / Classroom Management page:
    Displays all classrooms, teacher, enrolled students count, pending requests,
    meetings count, assignments count, and status.
    """
    if not check_admin(request.user):
        return redirect('login')

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all').lower()

    classrooms_qs = Classroom.objects.select_related('teacher', 'teacher__userprofile').annotate(
        approved_students=Count('memberships', filter=Q(memberships__status='approved')),
        pending_students=Count('memberships', filter=Q(memberships__status='pending')),
        meetings_count=Count('meetings'),
        assignments_count=Count('assignments'),
        quizzes_count=Count('quizzes'),
        materials_count=Count('study_materials'),
    ).order_by('-created_at')

    if status_filter == 'active':
        classrooms_qs = classrooms_qs.filter(is_active=True)
    elif status_filter == 'inactive':
        classrooms_qs = classrooms_qs.filter(is_active=False)

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
    total_enrollments = ClassroomMembership.objects.filter(status='approved').count()
    teachers = User.objects.filter(userprofile__user_type='teacher').order_by('first_name', 'last_name', 'username')

    return render(request, 'accounts/admin/admin_all_classrooms.html', {
        'classrooms': classrooms_qs,
        'teachers': teachers,
        'total_classrooms': total_classrooms,
        'active_classrooms': active_classrooms,
        'total_enrollments': total_enrollments,
        'search_query': search_query,
        'status_filter': status_filter,
    })


@login_required
def admin_classroom_detail(request, classroom_id):
    """Classroom 360 Detail View: teacher, students, meetings, study materials, and assignments."""
    if not check_admin(request.user):
        return redirect('login')

    classroom_data = get_classroom_360_data(classroom_id)
    return render(request, 'accounts/admin/classroom_detail.html', {
        **classroom_data,
    })


@login_required
def admin_all_meetings(request):
    """
    Classes / Meetings Management page:
    Displays all meetings (classroom sessions and standalone meetings),
    scheduled time, status, teacher, duration, and attendee counts.
    """
    if not check_admin(request.user):
        return redirect('login')

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all').lower()

    meetings_qs = Meeting.objects.select_related('teacher', 'teacher__userprofile', 'classroom').annotate(
        attendees_count=Count('participants')
    ).order_by('-scheduled_time')

    if status_filter in ['scheduled', 'live', 'ended', 'cancelled']:
        meetings_qs = meetings_qs.filter(status=status_filter)

    if search_query:
        meetings_qs = meetings_qs.filter(
            Q(title__icontains=search_query) |
            Q(meeting_code__icontains=search_query) |
            Q(teacher__username__icontains=search_query) |
            Q(classroom__title__icontains=search_query)
        )

    now = timezone.now()
    total_count = Meeting.objects.count()
    live_count = Meeting.objects.filter(status='live').count()
    scheduled_count = Meeting.objects.filter(status='scheduled', scheduled_time__gte=now).count()
    ended_count = Meeting.objects.filter(status='ended').count()

    return render(request, 'accounts/admin/admin_all_meetings.html', {
        'meetings': meetings_qs,
        'total_count': total_count,
        'live_count': live_count,
        'scheduled_count': scheduled_count,
        'ended_count': ended_count,
        'status_filter': status_filter,
        'search_query': search_query,
    })


@login_required
def admin_meeting_detail(request, meeting_id):
    """Meeting Detail & Attendance View: participant attendance log and verification details."""
    if not check_admin(request.user):
        return redirect('login')

    meeting_data = get_meeting_360_data(meeting_id)
    return render(request, 'accounts/admin/meeting_detail.html', {
        **meeting_data,
    })


@login_required
def admin_live_meetings(request):
    """Filter meeting management to live meetings only."""
    return redirect('/admin/meetings/?status=live')


@login_required
def admin_all_cameras(request):
    """Redirect to the unified camera fleet dashboard."""
    return redirect('admin_dashboard')

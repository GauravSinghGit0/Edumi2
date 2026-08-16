"""
Classroom-level attendance history views for teachers.
"""
from collections import defaultdict

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from meetings.models import Classroom, Meeting


@login_required
def classroom_attendance_history(request):
    """Day-wise and class-wise list of all meetings held across teacher's classrooms."""
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher':
        return redirect('student_dashboard' if hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'student' else 'home')

    classrooms = Classroom.objects.filter(teacher=request.user)
    meetings = Meeting.objects.filter(classroom__in=classrooms).order_by('-scheduled_time')

    history = defaultdict(list)
    for meeting in meetings:
        date_str = meeting.scheduled_time.strftime('%Y-%m-%d')
        history[date_str].append(meeting)

    return render(request, 'meetings/attendance/attendance_history.html', {
        'history': dict(history),
        'classrooms': classrooms,
    })


@login_required
def classroom_attendance_detail(request, classroom_id):
    """Attendance summary for a specific classroom grouped by day."""
    classroom = get_object_or_404(Classroom, id=classroom_id)
    if classroom.teacher != request.user and not request.user.is_superuser:
        return redirect('student_classrooms' if hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'student' else 'home')

    meetings = Meeting.objects.filter(classroom=classroom).order_by('-scheduled_time')
    meetings_by_day = defaultdict(list)
    for meeting in meetings:
        day = meeting.scheduled_time.date()
        meetings_by_day[day].append(meeting)

    grouped_meetings = [
        {'date': day, 'meetings': meetings_by_day[day]}
        for day in sorted(meetings_by_day.keys(), reverse=True)
    ]

    return render(request, 'meetings/attendance/classroom_attendance_detail.html', {
        'classroom': classroom,
        'grouped_meetings': grouped_meetings,
        'page_title': f'Meeting History — {classroom.title}',
    })

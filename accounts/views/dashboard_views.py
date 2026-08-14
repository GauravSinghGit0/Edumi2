"""
Dashboard views for teachers and students.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from accounts.models import UserProfile


@login_required
def teacher_dashboard(request):
    """Main dashboard for teachers — stats, classrooms, meetings."""
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher':
        return redirect('login')
    from accounts.services import get_teacher_stats
    context = get_teacher_stats(request.user)
    return render(request, 'accounts/teacher_dashboard.html', context)


@login_required
def student_dashboard(request):
    """Main dashboard for students — enrolled courses, attendance, meetings."""
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'student':
        return redirect('login')
    profile = request.user.userprofile
    from accounts.services import get_student_stats, get_profile_completion
    context = get_student_stats(request.user)
    context['profile_completion'] = get_profile_completion(request.user)
    context['profile'] = profile
    return render(request, 'accounts/student_dashboard.html', context)

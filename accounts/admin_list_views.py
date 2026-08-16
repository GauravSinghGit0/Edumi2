"""Admin list views for detailed statistics"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from meetings.models import Meeting

User = get_user_model()

def check_admin(user):
    """Check if user is admin"""
    return user.is_superuser

@login_required
def admin_all_users(request):
    """Show all users with details"""
    if not check_admin(request.user):
        return redirect('login')
    
    users = User.objects.all().select_related('userprofile').order_by('-date_joined')
    
    return render(request, 'accounts/admin/admin_all_users.html', {
        'users': users,
        'total_count': users.count()
    })

@login_required
def admin_all_students(request):
    """Show all students"""
    if not check_admin(request.user):
        return redirect('login')
    
    students = User.objects.filter(userprofile__user_type='student').select_related('userprofile').order_by('-date_joined')
    
    return render(request, 'accounts/admin/admin_all_students.html', {
        'students': students,
        'total_count': students.count()
    })

@login_required
def admin_all_teachers(request):
    """Show all teachers"""
    if not check_admin(request.user):
        return redirect('login')
    
    teachers = User.objects.filter(userprofile__user_type='teacher').select_related('userprofile').order_by('-date_joined')
    
    return render(request, 'accounts/admin/admin_all_teachers.html', {
        'teachers': teachers,
        'total_count': teachers.count()
    })

@login_required
def admin_all_meetings(request):
    """Show all non-classroom meetings"""
    if not check_admin(request.user):
        return redirect('login')
    
    meetings = Meeting.objects.filter(classroom__isnull=True).select_related('teacher', 'classroom').order_by('-created_at')
    
    return render(request, 'accounts/admin/admin_all_meetings.html', {
        'meetings': meetings,
        'total_count': meetings.count()
    })

@login_required
def admin_live_meetings(request):
    """Show live non-classroom meetings only"""
    if not check_admin(request.user):
        return redirect('login')
    
    meetings = Meeting.objects.filter(status='live', classroom__isnull=True).select_related('teacher', 'classroom').order_by('-created_at')
    
    return render(request, 'accounts/admin/admin_live_meetings.html', {
        'meetings': meetings,
        'total_count': meetings.count()
    })

@login_required
def admin_all_cameras(request):
    """Redirect to the new unified camera dashboard"""
    return redirect('admin_dashboard')

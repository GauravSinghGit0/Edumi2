"""
Authentication views: login, register, logout helpers, welcome dismiss,
emoji avatar save, error handlers, settings page.
"""
import base64
import uuid

from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import IntegrityError, transaction
from django.core.files.base import ContentFile

from accounts.models import UserProfile

User = get_user_model()


def login_view(request):
    """Login page — redirects to appropriate dashboard on success."""
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect('admin_panel')
        if hasattr(request.user, 'userprofile'):
            if request.user.userprofile.user_type == 'teacher':
                return redirect('teacher_dashboard')
            elif request.user.userprofile.user_type == 'student':
                return redirect('student_dashboard')
        return redirect('home')

    if request.method == 'POST':
        username_or_email = request.POST.get('username')
        password = request.POST.get('password')
        
        # Try to authenticate with username first
        user = authenticate(request, username=username_or_email, password=password)
        
        # If that fails, try to find user by email
        if user is None:
            try:
                user_qs = User.objects.filter(email=username_or_email)
                if user_qs.count() == 1:
                    user_obj = user_qs.first()
                    user = authenticate(request, username=user_obj.username, password=password)
            except Exception:
                pass
        
        if user is not None:
            login(request, user)
            if user.is_superuser:
                if not hasattr(user, 'userprofile'):
                    UserProfile.objects.create(user=user, user_type='admin', display_name=f"Admin {user.username}")
                if not user.is_staff:
                    user.is_staff = True
                    user.save()
            messages.success(request, f"Welcome back, {user.username}!")
            if user.is_superuser:
                return redirect('admin_panel')
            if hasattr(user, 'userprofile'):
                if user.userprofile.user_type == 'teacher':
                    return redirect('teacher_dashboard')
                elif user.userprofile.user_type == 'student':
                    return redirect('student_dashboard')
            return redirect('home')
        return render(request, 'accounts/login.html', {'error': 'Invalid username or password'}, status=422)

    return render(request, 'accounts/login.html')


def register(request):
    """Registration page — creates user + profile, then redirects to dashboard."""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        user_type = request.POST.get('user_type')

        if not username:
            return render(request, 'accounts/register.html', {'error': 'Username is required'}, status=422)
        if not password1:
            return render(request, 'accounts/register.html', {'error': 'Password is required'}, status=422)
        if not user_type:
            return render(request, 'accounts/register.html', {'error': 'Please select your role'}, status=422)

        if password1 == password2:
            try:
                with transaction.atomic():
                    if User.objects.filter(username=username).exists():
                        return render(request, 'accounts/register.html', {'error': f'Username "{username}" is already taken'}, status=422)
                    user = User.objects.create_user(username=username, password=password1)
                    UserProfile.objects.create(user=user, user_type=user_type)
                login(request, user)
                request.session['show_welcome'] = True
                if user_type == 'teacher':
                    return redirect('teacher_dashboard')
                elif user_type == 'student':
                    return redirect('student_dashboard')
                return redirect('home')
            except IntegrityError:
                return render(request, 'accounts/register.html', {'error': 'Database error during registration'}, status=422)
            except Exception as e:
                return render(request, 'accounts/register.html', {'error': f'Registration failed: {str(e)}'}, status=422)
        return render(request, 'accounts/register.html', {'error': 'Passwords do not match'}, status=422)

    return render(request, 'accounts/register.html')


def home(request):
    """Public home/landing page."""
    return render(request, 'accounts/home.html')


@login_required
def settings_view(request):
    """Settings page (under development)."""
    return render(request, 'accounts/settings.html')


def error_404(request, exception):
    return render(request, '404.html', status=404)


def error_500(request):
    return render(request, '500.html', status=500)


@require_POST
def dismiss_welcome(request):
    """Dismiss the post-registration welcome banner."""
    request.session.pop('show_welcome', None)
    return JsonResponse({'ok': True})


@require_POST
@login_required
def save_emoji_avatar(request):
    """Save a canvas-rendered emoji as a profile picture PNG."""
    data_url = request.POST.get('data_url', '')
    if not data_url.startswith('data:image/png;base64,'):
        return JsonResponse({'ok': False, 'error': 'Invalid data'}, status=400)
    img_data = base64.b64decode(data_url.split(',')[1])
    profile = request.user.userprofile
    filename = f"emoji_{request.user.id}_{uuid.uuid4().hex[:8]}.png"
    profile.profile_picture.save(filename, ContentFile(img_data), save=True)
    profile.avatar_url = ''
    profile.save()
    return JsonResponse({'ok': True, 'url': profile.profile_picture.url})

"""
Authentication views: login, register, email verification, resend verification,
live uniqueness check, logout helpers, welcome dismiss, emoji avatar save, settings.
"""
import json
import base64
import uuid
import logging

from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.core.files.base import ContentFile
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from accounts.models import UserProfile
from accounts.serializers import RegistrationSerializer, USERNAME_REGEX
from accounts.email_tokens import (
    send_verification_email,
    verify_email_token,
    verify_email_otp,
)
from accounts.ratelimit import ratelimit

User = get_user_model()
logger = logging.getLogger('accounts')


def login_view(request):
    """
    Login page — authenticates user, enforces email verification for non-superusers,
    and redirects to appropriate dashboard on success.
    """
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
        username_or_email = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username_or_email or not password:
            return render(request, 'accounts/auth/login.html', {
                'error': 'Please enter both username/email and password.',
                'entered_username': username_or_email,
            }, status=422)

        # 1. Try to authenticate with username first
        user = authenticate(request, username=username_or_email, password=password)

        # 2. If that fails, try looking up user by email
        if user is None:
            try:
                user_qs = User.objects.filter(email__iexact=username_or_email)
                if user_qs.count() == 1:
                    user_obj = user_qs.first()
                    user = authenticate(request, username=user_obj.username, password=password)
            except Exception as e:
                logger.error(f"Error checking email login: {e}")

        if user is not None:
            # Superusers always bypass email verification and are guaranteed verified status
            if user.is_superuser:
                profile, _ = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={'user_type': 'admin', 'display_name': f"Admin {user.username}", 'is_verified': True}
                )
                if not profile.is_verified:
                    profile.verify_email()
                if not user.is_staff:
                    user.is_staff = True
                    user.save(update_fields=['is_staff'])

                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")
                return redirect('admin_panel')

            # Ensure profile exists
            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={'user_type': 'student', 'is_verified': False}
            )

            # Block login if user email is not yet verified
            if not profile.is_verified:
                request.session['unverified_email'] = user.email
                request.session['unverified_username'] = user.username
                return render(request, 'accounts/auth/login.html', {
                    'error': 'Your email address has not been verified yet.',
                    'unverified_error': True,
                    'unverified_email': user.email,
                    'entered_username': username_or_email,
                }, status=403)

            # Check if user is active
            if not user.is_active:
                return render(request, 'accounts/auth/login.html', {
                    'error': 'This account has been disabled. Please contact support.',
                    'entered_username': username_or_email,
                }, status=403)

            # Validated & Verified -> Log in
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")

            if profile.user_type == 'teacher':
                return redirect('teacher_dashboard')
            elif profile.user_type == 'student':
                return redirect('student_dashboard')
            return redirect('home')

        return render(request, 'accounts/auth/login.html', {
            'error': 'Invalid username/email or password.',
            'entered_username': username_or_email,
        }, status=422)

    return render(request, 'accounts/auth/login.html')


@ratelimit(action='register')
def register(request):
    """
    Registration view — validates inputs via RegistrationSerializer,
    dispatches verification email with signed link + OTP, and guides user to verification.
    """
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        # Support both form POST and JSON payload
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = {}
        else:
            data = request.POST.dict()

        serializer = RegistrationSerializer(data=data)

        if not serializer.is_valid():
            is_ajax = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                'application/json' in request.headers.get('Accept', '') or
                request.content_type == 'application/json'
            )
            if is_ajax:
                return JsonResponse({
                    'status': 'error',
                    'errors': serializer.errors,
                    'message': 'Please fix the errors below.'
                }, status=422)

            return render(request, 'accounts/auth/register.html', {
                'errors': serializer.errors,
                'form_data': data,
            }, status=422)

        # Valid registration data -> create user and profile (is_verified=False)
        try:
            user = serializer.save()
            # Send verification email via SMTP
            send_verification_email(request, user)

            request.session['unverified_email'] = user.email
            request.session['unverified_username'] = user.username

            is_ajax = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                'application/json' in request.headers.get('Accept', '') or
                request.content_type == 'application/json'
            )
            if is_ajax:
                return JsonResponse({
                    'status': 'success',
                    'message': 'Account created! Please check your email to verify your account.',
                    'email': user.email,
                    'redirect_url': '/verify-email-sent/'
                })

            return redirect('verify_email_sent')

        except Exception as e:
            logger.error(f"Registration exception for user data {data.get('username')}: {e}")
            error_dict = {'non_field_errors': [f'Registration failed: {str(e)}']}
            return render(request, 'accounts/auth/register.html', {
                'errors': error_dict,
                'form_data': data,
            }, status=422)

    return render(request, 'accounts/auth/register.html')


def verify_email_sent_view(request):
    """Informational page showing that a verification email was dispatched."""
    if request.user.is_authenticated and hasattr(request.user, 'userprofile') and request.user.userprofile.is_verified:
        return redirect(request.user.userprofile.get_dashboard_url())

    email = request.session.get('unverified_email', '')
    username = request.session.get('unverified_username', '')

    # If the user associated with this email is already verified, auto-login & redirect
    if email:
        try:
            user_obj = User.objects.filter(email__iexact=email).first()
            if user_obj and hasattr(user_obj, 'userprofile') and user_obj.userprofile.is_verified:
                login(request, user_obj, backend='django.contrib.auth.backends.ModelBackend')
                return redirect(user_obj.userprofile.get_dashboard_url())
        except Exception:
            pass

    return render(request, 'accounts/auth/verify_email_sent.html', {
        'email': email,
        'username': username,
    })


@require_http_methods(["GET", "POST"])
def verify_email(request):
    """
    Handles email verification either via signed link query token (?token=...)
    or via 6-digit OTP code form submission.
    Automatically provisions session (auto-login) and redirects directly to dashboard upon verification.
    """
    token = request.GET.get('token') or request.POST.get('token', '').strip()
    otp_code = request.POST.get('otp_code', '').strip()
    email = request.POST.get('email', '').strip() or request.session.get('unverified_email', '')

    user = None
    error_message = None
    is_already_verified = False

    # Option A: Verifying via 6-digit OTP code
    if request.method == 'POST' and otp_code:
        if not email:
            error_message = "Please provide the email address associated with your account."
        else:
            user, error_message, is_already_verified = verify_email_otp(email, otp_code)

    # Option B: Verifying via signed cryptographic token
    elif token:
        user, error_message, is_already_verified = verify_email_token(token)

    else:
        if request.method == 'GET':
            return render(request, 'accounts/auth/verify_email_sent.html', {
                'email': email,
            })
        error_message = "Please enter the 6-digit verification code sent to your email."

    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        'application/json' in request.headers.get('Accept', '')
    )

    if user and not error_message:
        # Mark profile as verified
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'user_type': 'student'})
        if not profile.is_verified:
            profile.verify_email()

        # Clear unverified session markers
        request.session.pop('unverified_email', None)
        request.session.pop('unverified_username', None)

        # Automatic Session Provisioning (Auto-Login — Zoom/Meet Standard)
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')

        dashboard_url = profile.get_dashboard_url()
        msg = f"Welcome to EduMi, {profile.get_display_name()}! Your account is active."
        messages.success(request, msg)

        if is_ajax:
            return JsonResponse({
                'status': 'success',
                'message': msg,
                'redirect_url': dashboard_url,
                'already_verified': is_already_verified
            })

        return redirect(dashboard_url)

    # Verification Failed
    if is_ajax:
        return JsonResponse({
            'status': 'error',
            'error': error_message or 'Verification failed. Please try again.',
        }, status=400)

    # Keep user on the interactive OTP verification page with error feedback and OTP inputs intact
    return render(request, 'accounts/auth/verify_email_sent.html', {
        'error': error_message,
        'email': email,
    }, status=400)


@require_POST
@ratelimit(action='resend_verification', limit=5, period=900)
def resend_verification_email(request):
    """
    Resend verification email (link + new OTP) to an unverified user.
    Rate limited to prevent email bombing.
    """
    email_or_username = request.POST.get('email', '').strip() or request.session.get('unverified_email', '')

    if not email_or_username:
        return JsonResponse({
            'ok': False,
            'error': 'Please provide an email address or username.'
        }, status=400)

    # Lookup user
    user = User.objects.filter(email__iexact=email_or_username).first()
    if not user:
        user = User.objects.filter(username__iexact=email_or_username).first()

    if user:
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'user_type': 'student'})
        if profile.is_verified:
            dashboard_url = profile.get_dashboard_url()
            # Auto-login already verified user
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return JsonResponse({
                'ok': True,
                'message': 'This account is already verified! Redirecting to your dashboard...',
                'already_verified': True,
                'redirect_url': dashboard_url
            })
        
        send_verification_email(request, user)
        request.session['unverified_email'] = user.email

    # Always return success message to avoid account enumeration
    return JsonResponse({
        'ok': True,
        'message': 'A fresh verification link and code have been sent to your email.'
    })


def check_availability(request):
    """
    Real-time endpoint for debounced username and email availability checks on blur/type.
    GET /accounts/check-availability/?field=username&value=alice
    Returns JSON: {"available": bool, "valid_format": bool, "message": str}
    """
    field = request.GET.get('field') or request.POST.get('field', '')
    value = (request.GET.get('value') or request.POST.get('value', '')).strip()

    if field not in ('username', 'email'):
        return JsonResponse({'error': 'Invalid field parameter. Must be "username" or "email".'}, status=400)

    if not value:
        return JsonResponse({'available': False, 'valid_format': False, 'message': f'{field.capitalize()} is required.'})

    if field == 'username':
        if len(value) < 3:
            return JsonResponse({'available': False, 'valid_format': False, 'message': 'Username must be at least 3 characters long.'})
        if len(value) > 30:
            return JsonResponse({'available': False, 'valid_format': False, 'message': 'Username cannot exceed 30 characters.'})
        if ' ' in value:
            return JsonResponse({'available': False, 'valid_format': False, 'message': 'Username cannot contain spaces.'})
        if not USERNAME_REGEX.match(value):
            return JsonResponse({'available': False, 'valid_format': False, 'message': 'Username can only contain letters, numbers, and underscores.'})

        exists = User.objects.filter(username__iexact=value).exists()
        if exists:
            return JsonResponse({'available': False, 'valid_format': True, 'message': f'Username "{value}" is already taken.'})
        return JsonResponse({'available': True, 'valid_format': True, 'message': 'Username is available!'})

    elif field == 'email':
        clean_email = value.lower()
        try:
            validate_email(clean_email)
        except ValidationError:
            return JsonResponse({'available': False, 'valid_format': False, 'message': 'Please enter a valid email address.'})

        exists = User.objects.filter(email__iexact=clean_email).exists()
        if exists:
            return JsonResponse({'available': False, 'valid_format': True, 'message': 'An account with this email address already exists.'})
        return JsonResponse({'available': True, 'valid_format': True, 'message': 'Email address is available!'})


def home(request):
    """Public home/landing page."""
    return render(request, 'accounts/dashboard/home.html')


@login_required
def settings_view(request):
    """Settings page."""
    return render(request, 'accounts/profile/settings.html')


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
    try:
        profile = request.user.userprofile
    except Exception:
        profile = UserProfile.objects.create(user=request.user, user_type='student')
    
    header, encoded = data_url.split(';base64,', 1)
    img_data = base64.b64decode(encoded)
    filename = f"emoji_{request.user.id}_{uuid.uuid4().hex[:8]}.png"
    profile.profile_picture.save(filename, ContentFile(img_data), save=True)
    profile.avatar_url = ''
    profile.save()
    return JsonResponse({'ok': True, 'url': profile.profile_picture.url})

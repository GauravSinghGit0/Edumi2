"""
Email Verification & OTP Services for Edumi2 LMS.
Handles signed URL tokens, cryptographically secure 6-digit OTP codes,
SHA-256 hashed persistence with database fallback, brute-force protection,
and SMTP email dispatch.
"""
import secrets
import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger('accounts')

SIGNER_SALT = 'edumi-email-verification-v1'


def generate_email_token(user):
    """Generate a tamper-proof timestamped signature string containing user.id and email."""
    signer = TimestampSigner(salt=SIGNER_SALT)
    payload = f"{user.id}:{user.email}"
    return signer.sign(payload)


def verify_email_token(token, max_age=None):
    """
    Verify a signed email token.
    Returns (user, None, is_already_verified) on success or (None, error_string, False) on failure.
    """
    if not token:
        return None, "Missing verification token.", False

    if max_age is None:
        max_age = getattr(settings, 'EMAIL_VERIFICATION_TOKEN_LIFETIME', 86400)

    signer = TimestampSigner(salt=SIGNER_SALT)
    try:
        unsigned = signer.unsign(token, max_age=max_age)
        user_id_str, email = unsigned.split(':', 1)
        user = User.objects.get(id=int(user_id_str), email__iexact=email)
        is_already_verified = bool(hasattr(user, 'userprofile') and user.userprofile.is_verified)
        return user, None, is_already_verified
    except SignatureExpired:
        return None, "Verification link has expired. Please request a new one.", False
    except (BadSignature, ValueError, User.DoesNotExist):
        return None, "Invalid verification link or token signature.", False
    except Exception as e:
        logger.error(f"Unexpected error verifying email token: {e}")
        return None, "Verification failed due to an unexpected error.", False


def generate_and_store_otp(user):
    """
    Generate a cryptographically secure 6-digit numeric OTP.
    Stores SHA-256 hash in database (EmailVerificationOTP) and cache for maximum reliability.
    Returns the raw 6-digit OTP string for email dispatch.
    """
    from accounts.models import EmailVerificationOTP

    # 1. Generate secure random 6-digit code (100000 - 999999)
    otp = f"{secrets.randbelow(900000) + 100000}"
    otp_hash = hashlib.sha256(otp.encode('utf-8')).hexdigest()
    ttl = getattr(settings, 'EMAIL_OTP_LIFETIME', 900)  # 15 minutes default
    expires_at = timezone.now() + timedelta(seconds=ttl)

    try:
        # Invalidate any existing unused OTPs for this user
        EmailVerificationOTP.objects.filter(user=user, is_used=False).update(is_used=True)

        # Persist new hashed OTP in database
        EmailVerificationOTP.objects.create(
            user=user,
            otp_hash=otp_hash,
            expires_at=expires_at,
            is_used=False,
            attempts=0
        )
    except Exception as e:
        logger.error(f"Error persisting EmailVerificationOTP to database for {user.username}: {e}")

    # Also store in cache for sub-millisecond lookups
    try:
        cache_key = f"email_otp_{user.id}"
        cache.set(cache_key, {'otp': otp, 'otp_hash': otp_hash, 'email': user.email}, ttl)
    except Exception as e:
        logger.warning(f"Failed to write OTP to cache for {user.username}: {e}")

    return otp


def verify_email_otp(user_or_email, otp_code):
    """
    Verify a 6-digit OTP for a given user or email with brute-force protection
    and idempotent already-verified handling.
    Returns (user, error_message, is_already_verified).
    """
    from accounts.models import EmailVerificationOTP

    if not otp_code or not str(otp_code).strip().isdigit():
        return None, "Please enter a valid 6-digit verification code.", False

    clean_otp = str(otp_code).strip()

    # 1. Resolve user
    if isinstance(user_or_email, User):
        user = user_or_email
    else:
        email_str = str(user_or_email or '').strip().lower()
        if not email_str:
            return None, "Please provide the email address associated with your account.", False
        try:
            user = User.objects.get(email__iexact=email_str)
        except User.DoesNotExist:
            return None, "No account associated with that email address.", False

    # 2. Idempotent check: If account is ALREADY verified, return success immediately
    if hasattr(user, 'userprofile') and user.userprofile.is_verified:
        return user, None, True

    # 3. Check Database-backed OTP first
    now = timezone.now()
    input_hash = hashlib.sha256(clean_otp.encode('utf-8')).hexdigest()

    otp_record = EmailVerificationOTP.objects.filter(
        user=user,
        is_used=False,
        expires_at__gte=now
    ).order_by('-created_at').first()

    if otp_record:
        # Check brute force limit (max 5 failed attempts)
        if otp_record.attempts >= 5:
            otp_record.is_used = True
            otp_record.save(update_fields=['is_used'])
            return None, "Too many failed attempts. This code has been invalidated. Please request a new one.", False

        # Constant-time comparison to prevent timing attacks
        if constant_time_compare(input_hash, otp_record.otp_hash):
            otp_record.is_used = True
            otp_record.save(update_fields=['is_used'])
            cache.delete(f"email_otp_{user.id}")
            return user, None, False
        else:
            otp_record.attempts += 1
            otp_record.save(update_fields=['attempts'])
            remaining = max(0, 5 - otp_record.attempts)
            if remaining == 0:
                otp_record.is_used = True
                otp_record.save(update_fields=['is_used'])
                return None, "Incorrect verification code. Maximum attempts exceeded. Please request a new one.", False
            return None, f"Incorrect verification code. ({remaining} attempt{'s' if remaining != 1 else ''} remaining)", False

    # 4. Fallback to Cache lookup if database record wasn't found
    cache_key = f"email_otp_{user.id}"
    cached_data = cache.get(cache_key)

    if cached_data:
        expected_otp = str(cached_data.get('otp', '')).strip()
        expected_hash = cached_data.get('otp_hash', '')
        
        matches = False
        if expected_hash:
            matches = constant_time_compare(input_hash, expected_hash)
        elif expected_otp:
            matches = constant_time_compare(clean_otp, expected_otp)

        if matches:
            cache.delete(cache_key)
            return user, None, False
        else:
            return None, "Incorrect verification code. Please check and try again.", False

    # 5. Code not found or expired
    return None, "Verification code has expired or is invalid. Please request a new one.", False


def send_verification_email(request, user):
    """
    Generate signed token + 6-digit OTP and send email to user using SMTP configured in settings.
    """
    token = generate_email_token(user)
    otp = generate_and_store_otp(user)

    # Build absolute verification URL
    if request:
        base_url = request.build_absolute_uri('/')[:-1]
    else:
        base_url = getattr(settings, 'DEFAULT_DOMAIN', 'http://localhost:8002')

    verification_url = f"{base_url}/verify-email/?token={token}"

    context = {
        'user': user,
        'verification_url': verification_url,
        'otp_code': otp,
        'token': token,
        'otp_expiry_minutes': int(getattr(settings, 'EMAIL_OTP_LIFETIME', 900) / 60),
        'support_email': getattr(settings, 'DEFAULT_FROM_EMAIL', 'support@edumi.com'),
    }

    subject = "Verify your EduMi account"

    # Try loading custom HTML template; fallback to clean inline HTML if not found
    try:
        html_content = render_to_string('accounts/emails/verification_email.html', context)
    except Exception as e:
        logger.warning(f"Could not load verification_email.html: {e}. Falling back to default layout.")
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <h2 style="color: #4f46e5;">Welcome to EduMi, {user.username}!</h2>
            <p>Thank you for signing up. Please verify your email address to activate your account.</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{verification_url}" style="background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Verify Email Address</a>
            </div>
            <p style="text-align: center; color: #666;">Or enter this 6-digit verification code:</p>
            <div style="text-align: center; margin: 15px 0;">
                <span style="font-size: 28px; letter-spacing: 6px; font-weight: bold; background: #f3f4f6; padding: 8px 16px; border-radius: 6px; color: #111;">{otp}</span>
            </div>
            <p style="font-size: 12px; color: #888; margin-top: 30px;">If you didn't create an EduMi account, you can safely ignore this email.</p>
        </div>
        """

    text_content = f"""
Hello {user.username},

Thank you for registering on EduMi!

Please verify your email address by visiting this link:
{verification_url}

Or use your 6-digit verification code: {otp}
(This code expires in {context['otp_expiry_minutes']} minutes).

If you did not sign up for an EduMi account, please ignore this email.

Best regards,
The EduMi Team
"""

    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [user.email]

    try:
        send_mail(
            subject=subject,
            message=text_content.strip(),
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_content,
            fail_silently=False,
        )
        logger.info(f"Verification email sent successfully to {user.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {e}")
        # Return True in debug/local if mail server is offline to prevent crashing signup flow
        if settings.DEBUG:
            return True
        return False

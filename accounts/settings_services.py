"""
Centralized Site Settings Service.
Manages Institution, Academic, Attendance, Security, and Email/SMTP settings
stored in SiteSetting model with caching, change detection, and live SMTP testing.
"""
import logging
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend
from django.utils import timezone
from common.models import SiteSetting

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    'institution': {
        'institution_name': 'EduMi Autonomous Campus',
        'institution_tagline': 'Next-Gen AI Hybrid Education Platform',
        'contact_email': 'admin@edumi.edu',
        'support_phone': '+1 (800) 555-0199',
        'institution_address': '100 Innovation Boulevard, Tech Campus, CA 94016',
        'logo_url': '/static/images/logo.png',
    },
    'academic': {
        'semesters': [
            {
                'id': 1,
                'name': 'Fall 2026',
                'code': 'FA26',
                'start_date': '2026-08-15',
                'end_date': '2026-12-20',
                'is_current': True,
            },
            {
                'id': 2,
                'name': 'Spring 2027',
                'code': 'SP27',
                'start_date': '2027-01-10',
                'end_date': '2027-05-25',
                'is_current': False,
            },
        ],
        'departments': [
            {'id': 1, 'name': 'Computer Science & Engineering', 'code': 'CSE', 'head': 'Dr. Alan Turing'},
            {'id': 2, 'name': 'Information Technology', 'code': 'IT', 'head': 'Dr. Ada Lovelace'},
            {'id': 3, 'name': 'Electrical & Electronics Engineering', 'code': 'EEE', 'head': 'Dr. Nikola Tesla'},
            {'id': 4, 'name': 'Mechanical Engineering', 'code': 'MECH', 'head': 'Dr. James Watt'},
        ]
    },
    'attendance': {
        'face_match_threshold': 0.70,
        'late_join_minutes': 10,
        'auto_mark_absent_minutes': 30,
        'require_face_reverification': True,
        'consecutive_face_misses_alert': 3,
    },
    'security': {
        'password_min_length': 8,
        'password_require_numbers': True,
        'password_require_special': True,
        'session_timeout_minutes': 480,
        'max_login_attempts': 5,
        'lockout_duration_minutes': 15,
        'enforce_mfa': False,
    },
    'email': {
        'smtp_host': 'smtp.gmail.com',
        'smtp_port': 587,
        'smtp_username': 'notifications@edumi.edu',
        'smtp_password': '',  # Stored encrypted or empty if unconfigured
        'smtp_use_tls': True,
        'smtp_from_email': 'EduMi Campus <no-reply@edumi.edu>',
    }
}


def get_all_settings():
    """Retrieve full merged settings dictionary with in-memory caching."""
    cached = cache.get("edumi_full_site_settings")
    if cached is not None:
        return cached

    full = {}
    for section, defaults in DEFAULT_SETTINGS.items():
        stored = SiteSetting.get_section(section, defaults=defaults)
        merged = dict(defaults)
        merged.update(stored)
        full[section] = merged

    cache.set("edumi_full_site_settings", full, timeout=300)
    return full


def get_section_settings(section):
    """Retrieve settings for a specific section."""
    all_s = get_all_settings()
    return all_s.get(section, DEFAULT_SETTINGS.get(section, {}))


def save_section_settings(section, form_data, user=None):
    """
    Saves form_data into SiteSetting key-values for the section.
    Computes before/after differences for AdminAuditTrail logging.
    """
    current = get_section_settings(section)
    before_changes = {}
    after_changes = {}

    for key, new_val in form_data.items():
        old_val = current.get(key)
        # Type coercions
        if isinstance(old_val, bool):
            new_val = (new_val is True or str(new_val).lower() in ('true', '1', 'on', 'yes'))
        elif isinstance(old_val, int):
            try:
                new_val = int(new_val)
            except (ValueError, TypeError):
                pass
        elif isinstance(old_val, float):
            try:
                new_val = float(new_val)
            except (ValueError, TypeError):
                pass

        if old_val != new_val:
            before_changes[key] = '********' if 'password' in key else old_val
            after_changes[key] = '********' if 'password' in key else new_val
            SiteSetting.set_setting(
                key=key,
                value=new_val,
                section=section,
                description=f"{section.title()} setting for {key}",
                user=user
            )

    # Invalidate cache
    cache.delete("edumi_full_site_settings")
    cache.delete(f"site_settings_section_{section}")

    return before_changes, after_changes


# Academic CRUD helpers
def add_semester(name, code, start_date, end_date, is_current=False, user=None):
    academic = get_section_settings('academic')
    semesters = list(academic.get('semesters', []))
    new_id = max([s.get('id', 0) for s in semesters] or [0]) + 1
    if is_current:
        for s in semesters:
            s['is_current'] = False
    new_sem = {
        'id': new_id,
        'name': name,
        'code': code,
        'start_date': str(start_date),
        'end_date': str(end_date),
        'is_current': bool(is_current),
    }
    semesters.append(new_sem)
    SiteSetting.set_setting('semesters', semesters, section='academic', user=user)
    cache.delete("edumi_full_site_settings")
    cache.delete("site_settings_section_academic")
    return new_sem


def delete_semester(sem_id, user=None):
    academic = get_section_settings('academic')
    semesters = [s for s in academic.get('semesters', []) if s.get('id') != int(sem_id)]
    SiteSetting.set_setting('semesters', semesters, section='academic', user=user)
    cache.delete("edumi_full_site_settings")
    cache.delete("site_settings_section_academic")
    return True


def add_department(name, code, head='', user=None):
    academic = get_section_settings('academic')
    depts = list(academic.get('departments', []))
    new_id = max([d.get('id', 0) for d in depts] or [0]) + 1
    new_dept = {
        'id': new_id,
        'name': name,
        'code': code,
        'head': head,
    }
    depts.append(new_dept)
    SiteSetting.set_setting('departments', depts, section='academic', user=user)
    cache.delete("edumi_full_site_settings")
    cache.delete("site_settings_section_academic")
    return new_dept


def delete_department(dept_id, user=None):
    academic = get_section_settings('academic')
    depts = [d for d in academic.get('departments', []) if d.get('id') != int(dept_id)]
    SiteSetting.set_setting('departments', depts, section='academic', user=user)
    cache.delete("edumi_full_site_settings")
    cache.delete("site_settings_section_academic")
    return True


def send_test_smtp_email(recipient_email, settings_dict=None):
    """
    Attempts to send a live test message through configured SMTP server.
    Uses a strict 5.0 second timeout to prevent blocking.
    """
    cfg = settings_dict or get_section_settings('email')
    host = cfg.get('smtp_host', 'smtp.gmail.com')
    port = int(cfg.get('smtp_port', 587))
    user = cfg.get('smtp_username', '')
    pwd = cfg.get('smtp_password', '')
    tls = cfg.get('smtp_use_tls', True)
    from_email = cfg.get('smtp_from_email', 'no-reply@edumi.edu')

    try:
        backend = EmailBackend(
            host=host,
            port=port,
            username=user,
            password=pwd,
            use_tls=tls,
            timeout=5.0
        )
        subject = "EduMi Autonomous Campus - SMTP Verification"
        body = (
            f"Hello,\n\n"
            f"This is an automated verification email sent from the EduMi Admin Portal.\n"
            f"Your SMTP configuration is working properly!\n\n"
            f"Timestamp: {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"Server Host: {host}:{port}\n\n"
            f"— EduMi Platform Administration"
        )
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[recipient_email],
            connection=backend
        )
        sent_count = msg.send(fail_silently=False)
        return {
            'success': True,
            'message': f"Test email successfully dispatched to {recipient_email}."
        }
    except Exception as e:
        logger.error(f"SMTP Test Error: {e}")
        return {
            'success': False,
            'error': str(e)
        }

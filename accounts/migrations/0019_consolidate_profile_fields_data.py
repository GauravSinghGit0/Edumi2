"""
accounts/migrations/0019_consolidate_profile_fields_data.py

Data migration that safely consolidates:
- contact_number -> phone
- roll_number -> student_id
Verifies that no duplicates exist before allowing schema constraints to be applied.
Reversible: in reverse, copies phone -> contact_number and student_id -> roll_number.
"""

from django.db import migrations
from django.db.models import Count
from django.db.models.functions import Lower


def consolidate_profile_fields(apps, schema_editor):
    UserProfile = apps.get_model('accounts', 'UserProfile')
    User = apps.get_model('auth', 'User')

    # 1. Check duplicate emails
    dup_emails = (
        User.objects.annotate(email_lower=Lower('email'))
        .exclude(email_lower='')
        .values('email_lower')
        .annotate(cnt=Count('id'))
        .filter(cnt__gt=1)
    )
    if dup_emails.exists():
        dups = list(dup_emails)
        raise RuntimeError(
            f"Cannot apply identity consolidation migration: duplicate emails detected: {dups}. "
            "Please resolve duplicate accounts manually using 'python manage.py audit_identity_duplicates'."
        )

    # 2. Check duplicate student IDs
    dup_sids = (
        UserProfile.objects.exclude(student_id__isnull=True)
        .exclude(student_id='')
        .values('student_id')
        .annotate(cnt=Count('id'))
        .filter(cnt__gt=1)
    )
    if dup_sids.exists():
        dups = list(dup_sids)
        raise RuntimeError(
            f"Cannot apply identity consolidation migration: duplicate student_id detected: {dups}. "
            "Please resolve duplicate student IDs manually."
        )

    # 3. Consolidate contact_number -> phone and roll_number -> student_id
    updated_profiles = []
    for profile in UserProfile.objects.all():
        modified = False
        contact = getattr(profile, 'contact_number', None)
        phone = getattr(profile, 'phone', None)
        roll = getattr(profile, 'roll_number', None)
        sid = getattr(profile, 'student_id', None)

        if contact and not phone:
            profile.phone = contact.strip()
            modified = True
        elif phone and not contact:
            # Keep both aligned while contact_number column still exists
            profile.contact_number = phone.strip()
            modified = True

        if roll and not sid:
            profile.student_id = roll.strip()
            modified = True
        elif sid and not roll:
            # Keep both aligned while roll_number column still exists
            profile.roll_number = sid.strip()
            modified = True

        if modified:
            profile.save(update_fields=['phone', 'contact_number', 'student_id', 'roll_number'])


def reverse_consolidate_profile_fields(apps, schema_editor):
    UserProfile = apps.get_model('accounts', 'UserProfile')
    for profile in UserProfile.objects.all():
        phone = getattr(profile, 'phone', None)
        sid = getattr(profile, 'student_id', None)
        modified = False
        if phone and not getattr(profile, 'contact_number', None):
            profile.contact_number = phone
            modified = True
        if sid and not getattr(profile, 'roll_number', None):
            profile.roll_number = sid
            modified = True
        if modified:
            profile.save(update_fields=['contact_number', 'roll_number'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_alter_notification_notification_type'),
    ]

    operations = [
        migrations.RunPython(
            consolidate_profile_fields,
            reverse_code=reverse_consolidate_profile_fields
        ),
    ]

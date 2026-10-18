"""
accounts/management/commands/audit_identity_duplicates.py

Command to audit the database for duplicate user accounts, duplicate emails,
duplicate student/employee IDs, and conflicting profile fields BEFORE applying migrations.
Complies with EduMi 2 SSOT Safety Requirements:
- Does NOT automatically merge accounts.
- Outputs detailed diagnostics and anomaly tables.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models.functions import Lower

from accounts.models import UserProfile

User = get_user_model()


class Command(BaseCommand):
    help = "Audit accounts for duplicate emails, usernames, identification numbers, and conflicting fields."

    def add_arguments(self, parser):
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Exit with non-zero status if any duplicates or conflicts are found.',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=== EduMi 2 Identity & Profile Audit ==="))
        issues_found = 0

        # 1. Duplicate Case-Insensitive Emails
        self.stdout.write("Checking for duplicate email addresses (case-insensitive)...")
        dup_emails = (
            User.objects.annotate(email_lower=Lower('email'))
            .exclude(email_lower='')
            .values('email_lower')
            .annotate(cnt=Count('id'))
            .filter(cnt__gt=1)
        )
        if dup_emails.exists():
            issues_found += dup_emails.count()
            self.stdout.write(self.style.ERROR(f"Found {dup_emails.count()} duplicate email group(s):"))
            for item in dup_emails:
                em = item['email_lower']
                users = list(User.objects.filter(email__iexact=em).values('id', 'username', 'email', 'date_joined'))
                self.stdout.write(self.style.WARNING(f"  - Email '{em}' is shared by {len(users)} users: {users}"))
        else:
            self.stdout.write(self.style.SUCCESS("  [PASS] No duplicate emails found."))

        # 2. Duplicate Case-Insensitive Usernames
        self.stdout.write("Checking for duplicate usernames (case-insensitive)...")
        dup_usernames = (
            User.objects.annotate(uname_lower=Lower('username'))
            .values('uname_lower')
            .annotate(cnt=Count('id'))
            .filter(cnt__gt=1)
        )
        if dup_usernames.exists():
            issues_found += dup_usernames.count()
            self.stdout.write(self.style.ERROR(f"Found {dup_usernames.count()} duplicate username group(s):"))
            for item in dup_usernames:
                un = item['uname_lower']
                users = list(User.objects.filter(username__iexact=un).values('id', 'username', 'email'))
                self.stdout.write(self.style.WARNING(f"  - Username '{un}' is shared by {len(users)} users: {users}"))
        else:
            self.stdout.write(self.style.SUCCESS("  [PASS] No duplicate usernames found."))

        # 3. Duplicate student_id / roll_number in UserProfile
        self.stdout.write("Checking for duplicate student IDs...")
        dup_student_ids = (
            UserProfile.objects.exclude(student_id__isnull=True)
            .exclude(student_id='')
            .values('student_id')
            .annotate(cnt=Count('id'))
            .filter(cnt__gt=1)
        )
        if dup_student_ids.exists():
            issues_found += dup_student_ids.count()
            self.stdout.write(self.style.ERROR(f"Found {dup_student_ids.count()} duplicate student_id group(s):"))
            for item in dup_student_ids:
                sid = item['student_id']
                profs = list(UserProfile.objects.filter(student_id=sid).values('user_id', 'student_id'))
                self.stdout.write(self.style.WARNING(f"  - student_id '{sid}' used by users: {profs}"))
        else:
            self.stdout.write(self.style.SUCCESS("  [PASS] No duplicate student_ids found."))

        # 4. Duplicate employee_id in UserProfile
        self.stdout.write("Checking for duplicate employee IDs...")
        dup_emp_ids = (
            UserProfile.objects.exclude(employee_id__isnull=True)
            .exclude(employee_id='')
            .values('employee_id')
            .annotate(cnt=Count('id'))
            .filter(cnt__gt=1)
        )
        if dup_emp_ids.exists():
            issues_found += dup_emp_ids.count()
            self.stdout.write(self.style.ERROR(f"Found {dup_emp_ids.count()} duplicate employee_id group(s):"))
            for item in dup_emp_ids:
                eid = item['employee_id']
                profs = list(UserProfile.objects.filter(employee_id=eid).values('user_id', 'employee_id'))
                self.stdout.write(self.style.WARNING(f"  - employee_id '{eid}' used by users: {profs}"))
        else:
            self.stdout.write(self.style.SUCCESS("  [PASS] No duplicate employee_ids found."))

        # 5. Field Conflicts within UserProfile (phone vs contact_number, student_id vs roll_number)
        self.stdout.write("Checking for internal field divergence within UserProfile...")
        # Check if roll_number and contact_number still exist as DB columns
        db_cols = [f.name for f in UserProfile._meta.get_fields()]
        has_roll_col = 'roll_number' in db_cols
        has_contact_col = 'contact_number' in db_cols

        conflict_count = 0
        if has_contact_col:
            for p in UserProfile.objects.all():
                p_phone = getattr(p, 'phone', '') or ''
                p_contact = getattr(p, 'contact_number', '') or ''
                if p_phone and p_contact and p_phone != p_contact:
                    conflict_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"  - User {p.user_id}: phone='{p_phone}' != contact_number='{p_contact}'"
                        )
                    )
        if has_roll_col:
            for p in UserProfile.objects.all():
                p_sid = getattr(p, 'student_id', '') or ''
                p_roll = getattr(p, 'roll_number', '') or ''
                if p_sid and p_roll and p_sid != p_roll:
                    conflict_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"  - User {p.user_id}: student_id='{p_sid}' != roll_number='{p_roll}'"
                        )
                    )

        if conflict_count > 0:
            issues_found += conflict_count
            self.stdout.write(self.style.ERROR(f"Found {conflict_count} internal field conflict(s)."))
        else:
            self.stdout.write(self.style.SUCCESS("  [PASS] No field divergence detected within existing profiles."))

        self.stdout.write(self.style.MIGRATE_HEADING("=== Audit Summary ==="))
        if issues_found == 0:
            self.stdout.write(self.style.SUCCESS("All identity checks PASSED. Safe to apply constraints and SSOT refactor."))
        else:
            self.stdout.write(self.style.ERROR(f"Total anomalies detected: {issues_found}."))
            self.stdout.write(self.style.NOTICE("Manual administrator review required. Do NOT auto-merge accounts."))
            if options.get('strict'):
                raise SystemExit(1)

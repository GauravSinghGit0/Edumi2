"""
accounts/management/commands/check_classroom_instructors.py

Audit command to inspect all classrooms in the database and verify that their assigned
instructors possess the 'teacher' user_type role.
Identifies anomalies such as students or unconfigured accounts teaching courses.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from meetings.models import Classroom

User = get_user_model()


class Command(BaseCommand):
    help = "Audit all classrooms to verify instructors have user_type == 'teacher'."

    def add_arguments(self, parser):
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Exit with status code 1 if any invalid instructors are found.',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=== EduMi 2 Classroom Instructor Audit ==="))

        classrooms = Classroom.objects.select_related('teacher', 'teacher__userprofile').order_by('id')
        total_count = classrooms.count()

        invalid_classrooms = []
        valid_count = 0

        for cr in classrooms:
            instructor = cr.teacher
            if not instructor:
                invalid_classrooms.append((cr, None, "No instructor assigned"))
                continue

            profile = getattr(instructor, 'userprofile', None)
            user_type = getattr(profile, 'user_type', None)

            if user_type != 'teacher':
                invalid_classrooms.append((cr, instructor, user_type or 'No Profile / None'))
            else:
                valid_count += 1

        self.stdout.write(f"Audited {total_count} classroom(s). Valid instructors: {valid_count}.")

        if invalid_classrooms:
            self.stdout.write(self.style.ERROR(
                f"\nFound {len(invalid_classrooms)} classroom(s) whose instructor is NOT a registered teacher:"
            ))
            for cr, inst, actual_role in invalid_classrooms:
                if inst:
                    self.stdout.write(self.style.WARNING(
                        f"  - Classroom #{cr.id} '{cr.title}' (Code: {cr.class_code}): "
                        f"Instructor @{inst.username} (ID: {inst.id}, Email: {inst.email or 'N/A'}) "
                        f"has role '{actual_role}' (Expected: 'teacher')"
                    ))
                else:
                    self.stdout.write(self.style.ERROR(
                        f"  - Classroom #{cr.id} '{cr.title}' (Code: {cr.class_code}): No instructor assigned!"
                    ))

            if options['strict']:
                raise SystemExit(1)
        else:
            self.stdout.write(self.style.SUCCESS("\nAll classrooms have valid instructors with role 'teacher'."))

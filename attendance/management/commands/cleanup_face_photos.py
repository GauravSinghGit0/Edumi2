import os
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from attendance.models import StudentFaceProfile

logger = logging.getLogger('attendance')


class Command(BaseCommand):
    help = "Permanently deletes raw student face photos from disk and nulls the face_photo column for biometric privacy."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report files that would be deleted without actually deleting them.',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        profiles = StudentFaceProfile.objects.exclude(face_photo='').exclude(face_photo__isnull=True)
        count = profiles.count()

        self.stdout.write(self.style.NOTICE(f"Found {count} student face profile(s) with saved photos."))

        deleted_files = 0
        updated_profiles = 0

        for profile in profiles:
            photo = profile.face_photo
            username = profile.student.username if profile.student else f"id={profile.id}"
            if photo:
                try:
                    file_path = photo.path
                    if os.path.exists(file_path):
                        if not dry_run:
                            os.remove(file_path)
                        deleted_files += 1
                        self.stdout.write(f"  [{'DRY-RUN' if dry_run else 'DELETED'}] Photo for {username}: {file_path}")
                except Exception as exc:
                    self.stderr.write(f"  [ERROR] Could not remove photo file for {username}: {exc}")

                if not dry_run:
                    profile.face_photo = None
                    profile.save(update_fields=['face_photo'])
                    updated_profiles += 1

        # Also purge any orphaned files in media/face_photos
        media_photos_dir = os.path.join(settings.MEDIA_ROOT, 'face_photos')
        orphaned_deleted = 0
        if os.path.exists(media_photos_dir):
            for fname in os.listdir(media_photos_dir):
                fpath = os.path.join(media_photos_dir, fname)
                if os.path.isfile(fpath):
                    if not dry_run:
                        try:
                            os.remove(fpath)
                            orphaned_deleted += 1
                        except Exception as e:
                            self.stderr.write(f"  [ERROR] Could not remove orphaned file {fpath}: {e}")
                    else:
                        orphaned_deleted += 1
                        self.stdout.write(f"  [DRY-RUN] Orphaned photo: {fpath}")

        action_word = "Would delete" if dry_run else "Successfully deleted"
        self.stdout.write(self.style.SUCCESS(
            f"\n{action_word} {deleted_files} profile photo(s) and {orphaned_deleted} orphaned file(s). "
            f"Updated {updated_profiles} profile record(s) to null face_photo."
        ))

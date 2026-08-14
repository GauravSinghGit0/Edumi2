import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from attendance.models import StudentEngagementSnapshot
import datetime

class Command(BaseCommand):
    help = 'Deletes engagement snapshots and log files older than 24 hours'

    def handle(self, *args, **options):
        cutoff = timezone.now() - datetime.timedelta(hours=24)
        
        # 1. Delete DB snapshots
        snaps = StudentEngagementSnapshot.objects.filter(timestamp__lt=cutoff)
        count = snaps.count()
        snaps.delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {count} old engagement snapshots from database.'))

        # 2. Delete physical CSV logs
        log_dir = os.path.join(settings.MEDIA_ROOT, 'meeting_logs')
        if os.path.exists(log_dir):
            files_deleted = 0
            for filename in os.listdir(log_dir):
                if filename.endswith('.csv'):
                    file_path = os.path.join(log_dir, filename)
                    file_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                    # Convert to timezone aware if necessary
                    if timezone.is_aware(cutoff):
                        file_time = timezone.make_aware(file_time)
                    
                    if file_time < cutoff:
                        os.remove(file_path)
                        files_deleted += 1
            
            self.stdout.write(self.style.SUCCESS(f'Deleted {files_deleted} old physical log files.'))
        else:
            self.stdout.write('No log directory found.')

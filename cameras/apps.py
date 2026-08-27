from django.apps import AppConfig


class CamerasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cameras'

    def ready(self):
        # Run orphaned recording cleanup in a thread to not block startup
        import threading
        import sys
        import os
        
        # Don't run cleanup during migrations, management commands, or in camera service
        if 'manage.py' in sys.argv or os.path.basename(sys.argv[0]) == 'manage.py' and 'camera_service' in os.getcwd():
            return

        def _deferred_cleanup():
            import time
            time.sleep(2)
            try:
                from .recording_engine import cleanup_orphaned_recordings
                cleanup_orphaned_recordings()
            except Exception:
                pass

        threading.Thread(target=_deferred_cleanup, daemon=True).start()

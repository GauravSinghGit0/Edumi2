from django.apps import AppConfig
from django.db.backends.signals import connection_created


def enable_sqlite_wal(sender, connection, **kwargs):
    """Enable WAL mode, 60s busy timeout, NORMAL synchronous, and memory cache for SQLite to prevent database lock contention during rapid navigation."""
    if connection.vendor == 'sqlite':
        try:
            with connection.cursor() as cursor:
                cursor.execute('PRAGMA journal_mode=WAL;')
                cursor.execute('PRAGMA busy_timeout=60000;')
                cursor.execute('PRAGMA synchronous=NORMAL;')
                cursor.execute('PRAGMA cache_size=-64000;')
                cursor.execute('PRAGMA temp_store=MEMORY;')
        except Exception:
            pass


class CommonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'common'

    def ready(self):
        connection_created.connect(enable_sqlite_wal)

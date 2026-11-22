"""
Resilient session backend for EduMi 2.
Extends django.contrib.sessions.backends.cached_db to prevent SessionInterrupted
and UpdateError 500 crashes during concurrent operations, data resets, or orphaned cache entries.
"""
import logging
from django.contrib.sessions.backends.cached_db import SessionStore as CachedDBSessionStore
from django.contrib.sessions.backends.base import UpdateError, CreateError

logger = logging.getLogger('common')


class SessionStore(CachedDBSessionStore):
    """
    Enterprise-resilient cached_db session backend.
    
    Prevents django.contrib.sessions.exceptions.SessionInterrupted (HTTP 500) when:
    1. A session exists in Redis cache but its database record was wiped or deleted.
    2. Concurrent logout/session flush occurs during asynchronous polling (telemetry, WebSockets).
    """

    def save(self, must_create=False):
        try:
            super().save(must_create=must_create)
        except UpdateError:
            # Row missing in DB but exists in cache — auto-recover by recreating in DB
            try:
                super().save(must_create=True)
            except (CreateError, Exception) as e:
                # If cannot create (e.g. duplicate or DB error), flush stale cache entry
                try:
                    self._cache.delete(self.cache_key)
                except Exception:
                    pass
                logger.warning(
                    f"[SESSION] Purged stale/orphaned session from cache: {self.session_key} ({e})"
                )

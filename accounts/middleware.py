import threading
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

class LastSeenMiddleware(MiddlewareMixin):
    """Update the authenticated user's `last_seen` timestamp on each request.
    This runs early in the request/response cycle and saves the timestamp
    without blocking the response. A tiny lock guards concurrent saves.
    """
    _lock = threading.Lock()

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.user.is_authenticated:
            try:
                profile = request.user.userprofile
                with self._lock:
                    profile.last_seen = timezone.now()
                    profile.save(update_fields=["last_seen"])
            except Exception:
                # Silently ignore if profile does not exist
                pass
        return None

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from django.http import JsonResponse
from django.db import connection
from cameras.views_logic.streaming_views import camera_feed_proxy

def health_check(request):
    """Health check endpoint for watchdog, load balancers and monitoring."""
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False
    status = 200 if db_ok else 503
    return JsonResponse({
        'status': 'ok' if db_ok else 'degraded',
        'db': db_ok,
        'version': '2.0',
    }, status=status)

# Override admin logout to redirect to login page
admin.site.logout_template = None

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('favicon.ico', RedirectView.as_view(url='/static/images/favicon.svg', permanent=True)),
    path('admin/logout/', auth_views.LogoutView.as_view(next_page='/'), name='admin-logout'),
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    # Put the most specific route first: /cameras/<int:camera_id>/feed/
    path('cameras/<int:camera_id>/feed/', camera_feed_proxy, name='camera_feed_direct'),  # <-- New streamer view!
    path('cameras/', include('cameras.urls')),
    path('mobile-cameras/', include('mobile_cameras.urls')),
    path('meetings/', include('meetings.urls')),
    path('attendance/', include('attendance.urls')),
    path('videos/', include('videos.urls')),  # <-- Video URLs
    path('video-editing/', include('video_editing.urls')),  # <-- Video editing URLs
    path('assignments/', include('assignments.urls')),  # <-- Assignments URLs
]

# Error handlers
handler404 = 'accounts.views.error_404'
handler500 = 'accounts.views.error_500'

# Static and media files are served by WhiteNoise middleware (always on,
# regardless of DEBUG). Do NOT add Django's debug static handler here —
# it bypasses WhiteNoise, uses the wrong directory, and breaks MIME types
# on Windows.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

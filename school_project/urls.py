from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from django.http import JsonResponse
from django.db import connection
from django.views.static import serve
from meetings.livekit_http_proxy import livekit_http_proxy
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
    # LiveKit HTTP proxy — handles /livekit-proxy/ HTTP validation when running without Nginx
    re_path(r'^livekit-proxy(?P<lk_path>/.*)$', livekit_http_proxy),
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

# Serve uploaded media files (profile pictures, cover photos, recorded videos, etc.)
# WhiteNoise handles static files from STATIC_ROOT, but django.views.static.serve
# is required to serve uploaded media files from MEDIA_ROOT regardless of DEBUG setting.
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]


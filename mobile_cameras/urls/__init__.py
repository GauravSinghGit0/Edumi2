# mobile_cameras/urls/__init__.py
# This is the file Django actually loads for include('mobile_cameras.urls')
# app_name lives here (single authoritative location).
#
# Sub-files:
#   camera_urls.py     — dashboard, add, delete, feed, headcount, view, monitor, test
#   permission_urls.py — grant, revoke, manage permissions

from django.urls import path, include

app_name = 'mobile_cameras'

urlpatterns = [
    path('', include('mobile_cameras.urls.camera_urls')),
    path('', include('mobile_cameras.urls.permission_urls')),
]

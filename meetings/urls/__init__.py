# meetings/urls/__init__.py
# This is the file Django loads for include('meetings.urls')
#
# Sub-files:
#   classroom_urls.py — classroom CRUD, membership approve/deny/remove, leave, start meeting
#   meeting_urls.py   — create/join/end/leave/delete/cancel, livekit token, attendance, summary
#   control_urls.py   — sleep/unfreeze, kick/ban, global mute/cam-off controls

from django.urls import path, include

urlpatterns = [
    path('', include('meetings.urls.classroom_urls')),
    path('', include('meetings.urls.meeting_urls')),
    path('', include('meetings.urls.control_urls')),
]

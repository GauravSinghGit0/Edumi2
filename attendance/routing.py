from django.urls import re_path
from . import consumers
from .face_tracking_consumer import FaceTrackingConsumer

websocket_urlpatterns = [
    re_path(r'ws/attendance/(?P<meeting_code>\w+)/$', consumers.FaceAttendanceConsumer.as_asgi()),
    re_path(r'ws/face-tracking/(?P<meeting_code>\w+)/$', FaceTrackingConsumer.as_asgi()),
]

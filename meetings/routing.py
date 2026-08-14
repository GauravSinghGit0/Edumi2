from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/meeting/(?P<meeting_code>\w+)/$', consumers.MeetingConsumer.as_asgi()),
]

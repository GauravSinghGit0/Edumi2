from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/audio/(?P<camera_id>\w+)/$', consumers.AudioConsumer.as_asgi()),
]

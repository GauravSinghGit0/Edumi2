"""
ASGI config for school_project project.
"""

import os
import sys
import asyncio

# Set the event loop policy for Windows to support subprocesses in asyncio
if sys.platform == 'win32':
    try:
        if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_project.settings')

from django.core.asgi import get_asgi_application
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import re_path
from meetings.routing import websocket_urlpatterns as meeting_ws
from attendance.routing import websocket_urlpatterns as attendance_ws
from accounts.routing import websocket_urlpatterns as account_ws
from cameras.routing import websocket_urlpatterns as camera_ws
from meetings.livekit_proxy import LiveKitProxyConsumer

livekit_patterns = [
    re_path(r'^livekit-proxy(?P<lk_path>/.+)$', LiveKitProxyConsumer.as_asgi()),
    re_path(r'^livekit-proxy/?$', LiveKitProxyConsumer.as_asgi()),
]

websocket_urlpatterns = meeting_ws + attendance_ws + account_ws + camera_ws

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            livekit_patterns + websocket_urlpatterns
        )
    ),
})


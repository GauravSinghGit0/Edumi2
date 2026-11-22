'''Compatibility shim for meetings.livekit_http_proxy -> meetings.livekit_api_client'''
from .livekit_api_client import livekit_http_proxy, logger  # noqa: F401

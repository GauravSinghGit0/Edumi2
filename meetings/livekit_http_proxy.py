"""
HTTP proxy for LiveKit REST endpoints (e.g. /rtc/validate)

The LiveKit JS SDK makes HTTP GET requests to validate tokens before connecting.
This view proxies those requests to the local LiveKit server.
"""
from django.conf import settings
import requests
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import logging

logger = logging.getLogger(__name__)

LIVEKIT_INTERNAL = getattr(settings, 'LIVEKIT_INTERNAL_HTTP_URL', "http://localhost:7880")


@csrf_exempt
def livekit_http_proxy(request, lk_path):
    """Proxy HTTP requests to LiveKit server."""
    base_url = LIVEKIT_INTERNAL.rstrip('/')
    clean_path = lk_path.lstrip('/')
    target = f"{base_url}/{clean_path}"
    if request.META.get("QUERY_STRING"):
        target += f"?{request.META['QUERY_STRING']}"

    logger.info(f"LiveKit HTTP proxy -> {target}")

    try:
        # Forward the request
        resp = requests.request(
            method=request.method,
            url=target,
            headers={k: v for k, v in request.headers.items() if k.lower() not in ['host', 'connection']},
            data=request.body if request.method in ['POST', 'PUT', 'PATCH'] else None,
            timeout=10,
            allow_redirects=False,
        )

        # Return the response
        response = HttpResponse(
            content=resp.content,
            status=resp.status_code,
            content_type=resp.headers.get('Content-Type', 'application/json'),
        )
        for key, value in resp.headers.items():
            if key.lower() not in ['content-encoding', 'content-length', 'transfer-encoding', 'connection']:
                response[key] = value

        return response

    except Exception as e:
        logger.error(f"LiveKit HTTP proxy error: {e}")
        return JsonResponse({'error': str(e)}, status=502)

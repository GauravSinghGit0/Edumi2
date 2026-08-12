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
        forwarded_headers = {}
        for k, v in request.headers.items():
            k_lower = k.lower()
            if k_lower in ['host', 'connection', 'content-length']:
                continue
            forwarded_headers[k] = v

        if 'X-Forwarded-For' not in forwarded_headers:
            client_ip = request.META.get('REMOTE_ADDR', '')
            if client_ip:
                forwarded_headers['X-Forwarded-For'] = client_ip

        resp = requests.request(
            method=request.method,
            url=target,
            headers=forwarded_headers,
            data=request.body if request.method in ['POST', 'PUT', 'PATCH'] else None,
            timeout=10,
            allow_redirects=False,
        )

        response = HttpResponse(
            content=resp.content,
            status=resp.status_code,
            content_type=resp.headers.get('Content-Type', 'application/json'),
        )
        for key, value in resp.headers.items():
            key_lower = key.lower()
            if key_lower in ['content-encoding', 'content-length', 'transfer-encoding',
                             'connection', 'keep-alive', 'upgrade']:
                continue
            response[key] = value

        return response

    except requests.ConnectionError as e:
        msg = (
            f"LiveKit server is NOT RUNNING or UNREACHABLE at {LIVEKIT_INTERNAL}. "
            f"Windows: check start_app.ps1 'LiveKit SFU Server' line & logs/livekit.log. "
            f"Ubuntu : run 'systemctl status edumi-livekit' and 'journalctl -u edumi-livekit -n 50'. "
            f"Details: {e!r}"
        )
        logger.error(f"LiveKit HTTP proxy ConnectionError: {msg}")
        return JsonResponse(
            {'error': 'livekit_down', 'detail': msg},
            status=503,
        )

    except requests.Timeout:
        logger.error(f"LiveKit HTTP proxy TIMEOUT -> {target}")
        return JsonResponse({'error': 'livekit_timeout'}, status=504)

    except Exception as e:
        logger.error(f"LiveKit HTTP proxy error: {e!r}")
        return JsonResponse(
            {'error': 'livekit_proxy_error', 'detail': str(e)},
            status=502,
        )

"""
Cache-based IP rate limiter for Edumi2 LMS.
Prevents brute-force, credential stuffing, and bot registration attacks.
"""
import time
import functools
from django.core.cache import cache
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.conf import settings


def get_client_ip(request):
    """Safely extract client IP address handling proxies and load balancers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('REMOTE_ADDR') or '127.0.0.1'
    return ip


def is_rate_limited(request, action='default', limit=10, period=3600):
    """
    Check if a client IP has exceeded the allowed number of requests in the given period.
    Returns: (is_limited: bool, remaining_seconds: int, current_attempts: int)
    """
    ip = get_client_ip(request)
    cache_key = f"rl:{action}:{ip}"
    
    current_data = cache.get(cache_key)
    now = time.time()
    
    if current_data is None:
        # First request in the time window
        cache.set(cache_key, {'count': 1, 'start_time': now}, period)
        return False, period, 1
    
    count = current_data.get('count', 0)
    start_time = current_data.get('start_time', now)
    elapsed = now - start_time
    remaining_seconds = max(1, int(period - elapsed))
    
    if count >= limit:
        return True, remaining_seconds, count
    
    # Increment count while keeping original TTL window
    new_count = count + 1
    cache.set(cache_key, {'count': new_count, 'start_time': start_time}, remaining_seconds)
    return False, remaining_seconds, new_count


def ratelimit(action='default', limit=None, period=None, template_name=None):
    """
    Decorator for Django view functions enforcing rate limits.
    Returns HTTP 429 Too Many Requests when limit is exceeded.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Only rate-limit POST/mutating methods by default
            if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                effective_limit = limit
                if effective_limit is None:
                    if action == 'register':
                        effective_limit = getattr(settings, 'REGISTRATION_RATE_LIMIT', 10)
                    elif action == 'resend_verification':
                        effective_limit = 5
                    else:
                        effective_limit = 10

                effective_period = period
                if effective_period is None:
                    if action == 'register':
                        effective_period = getattr(settings, 'REGISTRATION_RATE_PERIOD', 3600)
                    elif action == 'resend_verification':
                        effective_period = 900
                    else:
                        effective_period = 3600

                limited, retry_after, attempts = is_rate_limited(
                    request,
                    action=action,
                    limit=effective_limit,
                    period=effective_period
                )
                if limited:
                    minutes = max(1, int(retry_after / 60))
                    msg = f"Too many attempts. You have exceeded the rate limit. Please try again in {minutes} minute(s)."
                    
                    is_ajax = (
                        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                        'application/json' in request.headers.get('Accept', '') or
                        'application/json' in (request.content_type or '')
                    )
                    
                    if is_ajax:
                        response = JsonResponse({
                            'ok': False,
                            'status': 'error',
                            'error': msg,
                            'retry_after': retry_after
                        }, status=429)
                        response['Retry-After'] = str(retry_after)
                        return response
                    
                    if template_name:
                        target_template = template_name
                    elif 'login' in request.path or request.path == '/':
                        target_template = 'accounts/auth/login.html'
                    elif 'password' in request.path or 'forgot' in request.path:
                        target_template = 'accounts/auth/password_reset_request.html'
                    else:
                        target_template = 'accounts/auth/register.html'

                    try:
                        response = render(request, target_template, {
                            'error': msg,
                            'rate_limited': True,
                            'retry_after': retry_after
                        }, status=429)
                        response['Retry-After'] = str(retry_after)
                        return response
                    except Exception:
                        response = HttpResponse(
                            f"<h1>429 Too Many Requests</h1><p>{msg}</p>",
                            status=429
                        )
                        response['Retry-After'] = str(retry_after)
                        return response
                        
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

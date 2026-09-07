"""
Custom middleware for error handling and system performance logging.
"""
import time
import os
import logging
import traceback
from django.http import JsonResponse
from django.db import OperationalError
from django.shortcuts import render

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)
perf_logger = logging.getLogger('performance')
error_logger = logging.getLogger('django.request')


class DatabaseErrorMiddleware:
    """
    Middleware to catch database locked errors and return a proper response
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        """Handle database exceptions"""
        if isinstance(exception, OperationalError):
            error_message = str(exception)
            
            if 'database is locked' in error_message:
                logger.warning(f"Database locked error for {request.path}")
                
                # Return appropriate response based on request type
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'error': 'Database is temporarily locked. Please try again in a moment.',
                        'retry': True
                    }, status=503)
                
                try:
                    return render(request, 'error.html', {
                        'error_title': 'Database Temporarily Locked',
                        'error_message': 'The database is currently busy. Please wait a moment and try again.',
                        'retry': True
                    }, status=503)
                except Exception:
                    return JsonResponse({
                        'error': 'Database is temporarily locked. Please try again in a moment.',
                        'retry': True
                    }, status=503)


class SystemPerformanceLoggingMiddleware:
    """
    Middleware to log system performance metrics, RAM usage, request durations,
    and process exceptions to rotating log files in the logs/ directory.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        try:
            self.process = psutil.Process(os.getpid()) if psutil else None
        except Exception:
            self.process = None

    def __call__(self, request):
        start_time = time.time()
        
        response = self.get_response(request)
        
        duration_ms = (time.time() - start_time) * 1000.0

        # Gather system resource telemetry
        mem_mb = 0
        if self.process:
            try:
                mem_mb = self.process.memory_info().rss / (1024 * 1024)
            except Exception:
                pass

        # Log performance metrics for requests
        try:
            user_info = getattr(request.user, 'username', 'anonymous') if hasattr(request, 'user') else 'anonymous'
        except Exception:
            user_info = 'anonymous'

        if duration_ms >= 50 or any(p in request.path for p in ('/meetings/', '/cameras/', '/api/')):
            perf_logger.info(
                f"[PERF] path={request.path} method={request.method} status={response.status_code} "
                f"duration={duration_ms:.1f}ms memory={mem_mb:.1f}MB user={user_info}"
            )

        return response

    def process_exception(self, request, exception):
        tb = traceback.format_exc()
        try:
            user_info = getattr(request.user, 'username', 'anonymous') if hasattr(request, 'user') else 'anonymous'
        except Exception:
            user_info = 'anonymous'

        error_logger.error(
            f"[CRASH_LOG] path={request.path} method={request.method} user={user_info} "
            f"exception={type(exception).__name__}: {str(exception)}\nTraceback:\n{tb}"
        )
        return None

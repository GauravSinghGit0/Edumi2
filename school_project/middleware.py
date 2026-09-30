"""
Custom enterprise middleware for database resilience, telemetry, audit logging, attack detection, and crash forensics.
Captures full client context (IP, timestamp, user identity, device, session) organized in date-based log folders.
"""
import time
import os
import uuid
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from django.http import JsonResponse
from django.db import OperationalError
from django.shortcuts import render
from django.conf import settings

try:
    import psutil
except ImportError:
    psutil = None

from common.telemetry import (
    get_client_ip,
    parse_user_agent,
    get_request_context,
    detect_attack_signatures,
    write_security_alert,
    write_access_log,
    write_json_audit_log,
    log_crash_forensics,
    get_dated_log_dir
)

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
    Enterprise telemetry, security attack detection, and crash forensic middleware.
    Captures:
      - Attack Detection (SQLi, XSS, Path Traversal, Scanners) -> logs/<date>/security_audit.log
      - Request ID (UUID for distributed tracing in X-Request-ID)
      - Client IP (handles proxies/Cloudflare/Nginx)
      - Timestamp (ISO 8601 UTC)
      - User identity (ID, username, role)
      - Session ID
      - Device telemetry (OS, Browser, Device Type)
      - Latency & Memory metrics
    Writes logs to date-partitioned folders:
      logs/<YYYY-MM-DD>/
        ├── access.log
        ├── activity_audit.jsonl
        ├── security_audit.log
        ├── crash_reports.log
        └── performance.log
    """
    def __init__(self, get_response):
        self.get_response = get_response
        try:
            self.process = psutil.Process(os.getpid()) if psutil else None
        except Exception:
            self.process = None

    def __call__(self, request):
        start_perf = time.perf_counter()
        
        # Attach unique request ID for end-to-end tracing
        if not hasattr(request, 'request_id'):
            request.request_id = uuid.uuid4().hex[:16]

        # Proactive Security: detect attack attempts & malicious payloads
        try:
            threats = detect_attack_signatures(request)
            if threats:
                write_security_alert(request, threats)
        except Exception:
            pass

        response = self.get_response(request)
        
        duration_ms = (time.perf_counter() - start_perf) * 1000.0

        # Inject X-Request-ID header into response
        try:
            response['X-Request-ID'] = request.request_id
        except Exception:
            pass

        # Skip high-frequency static asset noise if any reaches here
        if request.path.startswith(('/static/', '/favicon.ico')):
            return response

        # Extract comprehensive telemetry context
        try:
            ctx = get_request_context(request)
        except Exception:
            ctx = {
                'request_id': getattr(request, 'request_id', 'unknown'),
                'ip_address': get_client_ip(request),
                'username': getattr(getattr(request, 'user', None), 'username', 'anonymous'),
                'user_role': 'unknown',
                'device_type': 'Unknown',
                'browser': 'Unknown',
                'os': 'Unknown',
                'session_key': '',
                'referrer': ''
            }

        # Gather system resource telemetry (RAM)
        mem_mb = 0.0
        if self.process:
            try:
                mem_mb = self.process.memory_info().rss / (1024 * 1024)
            except Exception:
                pass

        iso_ts = datetime.now(timezone.utc).isoformat()
        status_code = getattr(response, 'status_code', 0)

        # 1. Write to logs/<date>/access.log
        access_entry = (
            f"[{iso_ts}] ip={ctx['ip_address']} user={ctx['username']} ({ctx['user_role']}) "
            f"req_id={ctx['request_id']} method={request.method} path={request.get_full_path()} "
            f"status={status_code} duration={duration_ms:.1f}ms memory={mem_mb:.1f}MB "
            f"device={ctx['device_type']} browser={ctx['browser']} os={ctx['os']}"
        )
        write_access_log(access_entry)

        # 2. Performance log for slow endpoints or key paths
        if duration_ms >= 50 or any(p in request.path for p in ('/meetings/', '/cameras/', '/api/')):
            perf_logger.info(
                f"[PERF] path={request.path} method={request.method} status={status_code} "
                f"duration={duration_ms:.1f}ms memory={mem_mb:.1f}MB ip={ctx['ip_address']} user={ctx['username']}"
            )

        # 3. Write structured JSON line to logs/<date>/activity_audit.jsonl
        audit_record = {
            'timestamp': iso_ts,
            'event_type': 'http_request',
            'event_name': f"{request.method} {request.path}",
            'path': request.path,
            'full_url': request.get_full_path(),
            'method': request.method,
            'status_code': status_code,
            'duration_ms': round(duration_ms, 2),
            'memory_mb': round(mem_mb, 2),
            **ctx
        }
        write_json_audit_log(audit_record)

        return response

    def process_exception(self, request, exception):
        """
        Deep Crash Forensics: Record exactly who, what they were doing,
        where the crash happened, and the system state into logs/<date>/crash_reports.log
        """
        tb = traceback.format_exc()
        try:
            log_crash_forensics(request, exception, tb_str=tb)
        except Exception as e:
            logger.error(f"Failed to record crash forensics: {e}")

        return None


# Backwards compatibility alias
EnterpriseAuditLoggingMiddleware = SystemPerformanceLoggingMiddleware

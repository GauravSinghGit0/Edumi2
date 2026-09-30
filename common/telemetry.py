"""
Enterprise Telemetry, Attack Detection & Forensic Logging Engine.
Inspired by Google, Meta / Instagram observability and cyber-forensic pipelines.

Directory Tree Architecture:
  logs/
    └── <YYYY-MM-DD>/
          ├── access.log               (Every HTTP request: IP, User, Role, Session, RequestID, Latency, RAM, Device)
          ├── user_interactions.log    (Human-readable clickstream: Buttons, Links, Coordinates, Text, Pages)
          ├── user_interactions.jsonl  (Machine-readable JSON clickstream)
          ├── activity_audit.jsonl     (Master JSON Lines audit trail)
          ├── security_audit.log       (Attacks, SQLi, XSS, Path Traversal, Scanners, Suspicious Payloads)
          ├── crash_reports.log        (Deep crash forensics: exact point of crash, user, what they were doing, payload, stack trace)
          ├── performance.log          (Slow queries, slow endpoints, resource telemetry)
          └── meetings_quiz.log        (Meetings, live classroom & quiz events)
"""
import os
import re
import sys
import json
import time
import uuid
import logging
import traceback
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone
from django.conf import settings
from django.utils import timezone as django_timezone

try:
    import psutil
except ImportError:
    psutil = None

BASE_LOG_DIR = Path(getattr(settings, 'BASE_DIR', '.')) / 'logs'
BASE_LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_current_date_str():
    """Get current date string in local timezone (e.g. '2026-09-30')."""
    try:
        now = django_timezone.localtime()
    except Exception:
        now = datetime.now()
    return now.strftime('%Y-%m-%d')


def get_dated_log_dir(date_str=None):
    """
    Get or create the folder_log -> <date_folder> directory path.
    Example: d:/Edumi2/logs/2026-09-30/
    """
    d_str = date_str or get_current_date_str()
    target_dir = BASE_LOG_DIR / d_str
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return target_dir


class DatedFolderRotatingFileHandler(logging.Handler):
    """
    Enterprise logging handler that automatically routes log records to:
    logs/<YYYY-MM-DD>/<filename>
    Handles midnight rollover dynamically without requiring server restart.
    """
    def __init__(self, filename, encoding='utf-8', max_bytes=20 * 1024 * 1024, backup_count=5):
        super().__init__()
        self.filename = filename
        self.encoding = encoding
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._current_date = None
        self._current_file = None
        self._current_stream = None

    def _get_stream(self):
        today = get_current_date_str()
        if today != self._current_date or self._current_stream is None:
            if self._current_stream:
                try:
                    self._current_stream.close()
                except Exception:
                    pass
            self._current_date = today
            folder = get_dated_log_dir(today)
            self._current_file = folder / self.filename
            self._current_stream = open(self._current_file, 'a', encoding=self.encoding)
        return self._current_stream

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self._get_stream()
            stream.write(msg + '\n')
            stream.flush()
        except Exception:
            self.handleError(record)

    def close(self):
        if self._current_stream:
            try:
                self._current_stream.close()
            except Exception:
                pass
            self._current_stream = None
        super().close()


# Attack signatures database (Regex patterns for proactive threat detection)
ATTACK_SIGNATURES = [
    # SQL Injection
    (r"(?i)(\bunion\b.*\bselect\b|\bselect\b.*\bfrom\b.*information_schema|\bexec\b.*\bxp_cmdshell|\bdrop\b\s+\btable\b|;\s*shutdown|\binsert\b\s+\binto\b.*values|'\s*or\s*'1'='1|--|\bbenchmark\s*\(|\bsleep\s*\(\d+\))", "SQL_INJECTION"),
    # Path Traversal & LFI
    (r"(\.\./|\.\.\\|/etc/passwd|/etc/shadow|/etc/hosts|c:\\windows|win\.ini|boot\.ini|\.env|\.git/config)", "PATH_TRAVERSAL"),
    # Cross-Site Scripting (XSS)
    (r"(?i)(<script[\s>]|javascript:|onerror\s*=|onload\s*=|onclick\s*=|document\.cookie|<iframe|<svg[\s/].*onload)", "XSS_ATTACK"),
    # Remote Code Execution / Shell Injection
    (r"(?i)(;\s*(cat|ls|rm|nc|curl|wget|id|whoami|bash|sh|powershell|cmd\.exe)\s+|\|\s*(cat|ls|rm|nc|curl|wget|id|whoami|bash|sh|powershell|cmd\.exe))", "COMMAND_INJECTION"),
    # Scanner / Reconnaissance Probes
    (r"(?i)(\bwp-admin\b|\bwp-login\b|\bphpmyadmin\b|\bactuator/gateway\b|\b.aws/credentials\b|\bconsole/\b|\bautodiscover\b|\bxmlrpc\.php\b)", "RECON_SCANNER"),
]


def detect_attack_signatures(request):
    """
    Inspect HTTP request for malicious attack patterns:
    - Path and Query String
    - Request Body (POST/JSON)
    - Sensitive Headers (User-Agent, Referrer)
    Returns: list of detected threats [{ 'type': ..., 'pattern': ..., 'source': ... }]
    """
    threats = []
    if not request:
        return threats

    # Check path & query string (both raw and URL-decoded)
    full_path = request.get_full_path()
    try:
        decoded_path = urllib.parse.unquote(full_path)
    except Exception:
        decoded_path = full_path

    for test_target in set([full_path, decoded_path]):
        for pattern, attack_type in ATTACK_SIGNATURES:
            match = re.search(pattern, test_target)
            if match and not any(t['type'] == attack_type and t['matched'] == match.group(0) for t in threats):
                threats.append({
                    'type': attack_type,
                    'source': 'URL_OR_QUERY_PARAM',
                    'matched': match.group(0),
                    'location': decoded_path[:200]
                })

    # Check User-Agent for known scanners
    ua = request.META.get('HTTP_USER_AGENT', '')
    scanner_patterns = r"(?i)(sqlmap|nikto|acunetix|masscan|nmap|dirbuster|gobuster|wpscan|hydra)"
    if re.search(scanner_patterns, ua):
        threats.append({
            'type': 'MALICIOUS_SCANNER_USER_AGENT',
            'source': 'HTTP_USER_AGENT',
            'matched': ua[:100],
            'location': 'Header'
        })

    # Check request body if available without exhausting stream
    try:
        if request.method in ('POST', 'PUT', 'PATCH'):
            body_sample = ''
            if hasattr(request, '_body') and request._body:
                body_sample = request._body.decode('utf-8', errors='ignore')
            elif request.POST:
                body_sample = str(request.POST.dict())

            if body_sample:
                try:
                    decoded_body = urllib.parse.unquote(body_sample)
                except Exception:
                    decoded_body = body_sample

                for test_body in set([body_sample, decoded_body]):
                    for pattern, attack_type in ATTACK_SIGNATURES:
                        match = re.search(pattern, test_body)
                        if match and not any(t['type'] == attack_type and t['matched'] == match.group(0) for t in threats):
                            threats.append({
                                'type': attack_type,
                                'source': 'REQUEST_BODY',
                                'matched': match.group(0),
                                'location': 'Body Payload'
                            })
    except Exception:
        pass

    return threats



def get_client_ip(request):
    """
    Extract accurate client IP address handling reverse proxies,
    Cloudflare, Nginx, and direct connections.
    """
    if not request:
        return '127.0.0.1'

    cf_ip = request.META.get('HTTP_CF_CONNECTING_IP')
    if cf_ip:
        return cf_ip.strip()

    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        parts = [p.strip() for p in x_forwarded.split(',') if p.strip()]
        if parts:
            return parts[0]

    x_real = request.META.get('HTTP_X_REAL_IP')
    if x_real:
        return x_real.strip()

    return request.META.get('REMOTE_ADDR') or '127.0.0.1'


def parse_user_agent(user_agent_str):
    """
    Parse User-Agent string to extract browser, operating system, and device type.
    """
    if not user_agent_str:
        return {
            'browser': 'Unknown',
            'os': 'Unknown',
            'device_type': 'Unknown',
            'is_bot': False
        }

    ua = user_agent_str.lower()
    is_bot = any(bot in ua for bot in ['bot', 'crawl', 'spider', 'slurp', 'mediapartners', 'lighthouse', 'curl', 'wget', 'python-requests'])

    if 'tablet' in ua or 'ipad' in ua:
        device_type = 'Tablet'
    elif 'mobile' in ua or 'android' in ua or 'iphone' in ua:
        device_type = 'Mobile'
    elif is_bot:
        device_type = 'Bot'
    else:
        device_type = 'Desktop'

    os_name = 'Unknown OS'
    if 'windows nt 10.0' in ua:
        os_name = 'Windows 10/11'
    elif 'windows' in ua:
        os_name = 'Windows'
    elif 'iphone' in ua or 'ipad' in ua or 'ipod' in ua:
        os_name = 'iOS'
    elif 'macintosh' in ua or 'mac os x' in ua:
        os_name = 'macOS'
    elif 'android' in ua:
        os_name = 'Android'
    elif 'linux' in ua:
        os_name = 'Linux'

    browser = 'Unknown Browser'
    if 'edg/' in ua or 'edge/' in ua:
        browser = 'Microsoft Edge'
    elif 'chrome/' in ua and 'chromium/' not in ua and 'edg/' not in ua:
        browser = 'Chrome'
    elif 'firefox/' in ua:
        browser = 'Firefox'
    elif 'safari/' in ua and 'chrome/' not in ua:
        browser = 'Safari'
    elif 'opera' in ua or 'opr/' in ua:
        browser = 'Opera'
    elif is_bot:
        browser = 'Bot/Crawler'

    return {
        'browser': browser,
        'os': os_name,
        'device_type': device_type,
        'is_bot': is_bot
    }


def sanitize_data(data):
    """
    Recursively sanitize sensitive fields like passwords, tokens, API keys, secrets.
    """
    if not isinstance(data, dict):
        return data

    sensitive_keys = {'password', 'passwd', 'secret', 'token', 'csrfmiddlewaretoken', 'key', 'auth', 'credit_card'}
    sanitized = {}
    for k, v in data.items():
        if any(sk in k.lower() for sk in sensitive_keys):
            sanitized[k] = '***REDACTED***'
        elif isinstance(v, dict):
            sanitized[k] = sanitize_data(v)
        elif isinstance(v, list):
            sanitized[k] = [sanitize_data(i) if isinstance(i, dict) else i for i in v]
        else:
            sanitized[k] = v
    return sanitized


def get_request_context(request):
    """
    Extract comprehensive client & identity context from an HTTP request.
    """
    if not request:
        return {}

    ip = get_client_ip(request)
    ua_string = request.META.get('HTTP_USER_AGENT', '')
    parsed_ua = parse_user_agent(ua_string)

    user = getattr(request, 'user', None)
    is_authenticated = bool(user and user.is_authenticated)

    username = user.username if is_authenticated else 'anonymous'
    user_id = user.id if is_authenticated else None
    
    user_role = 'anonymous'
    if is_authenticated:
        if getattr(user, 'is_superuser', False):
            user_role = 'admin'
        elif hasattr(user, 'userprofile') and getattr(user.userprofile, 'user_type', None):
            user_role = user.userprofile.user_type
        elif getattr(user, 'is_staff', False):
            user_role = 'staff'
        else:
            user_role = 'student'

    session_key = ''
    if hasattr(request, 'session') and request.session:
        session_key = request.session.session_key or ''

    request_id = getattr(request, 'request_id', None)
    if not request_id:
        request_id = str(uuid.uuid4()).replace('-', '')[:16]
        request.request_id = request_id

    return {
        'request_id': request_id,
        'ip_address': ip,
        'user_id': user_id,
        'username': username,
        'user_role': user_role,
        'is_authenticated': is_authenticated,
        'session_key': session_key,
        'user_agent': ua_string,
        'device_type': parsed_ua['device_type'],
        'browser': parsed_ua['browser'],
        'os': parsed_ua['os'],
        'is_bot': parsed_ua['is_bot'],
        'referrer': request.META.get('HTTP_REFERER', ''),
        'accept_language': request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    }


def write_access_log(entry_str, date_str=None):
    """Append formatted HTTP access entry to logs/<date>/access.log."""
    try:
        log_file = get_dated_log_dir(date_str) / 'access.log'
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(entry_str + '\n')
    except Exception:
        pass


def write_json_audit_log(event_dict, date_str=None):
    """Write structured event dictionary as a JSON Line to logs/<date>/activity_audit.jsonl."""
    try:
        audit_file = get_dated_log_dir(date_str) / 'activity_audit.jsonl'
        with open(audit_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event_dict, ensure_ascii=False) + '\n')
    except Exception:
        pass


def write_interaction_log(event_dict, date_str=None):
    """Write interaction event to logs/<date>/user_interactions.log and .jsonl."""
    try:
        folder = get_dated_log_dir(date_str)

        # 1. JSON lines version
        jsonl_file = folder / 'user_interactions.jsonl'
        with open(jsonl_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event_dict, ensure_ascii=False) + '\n')

        # 2. Human readable format
        human_file = folder / 'user_interactions.log'
        ts = event_dict.get('timestamp') or datetime.now(timezone.utc).isoformat()
        evt_type = (event_dict.get('event_type') or 'EVENT').upper()
        evt_name = event_dict.get('event_name') or ''
        user = event_dict.get('username') or 'anonymous'
        role = event_dict.get('user_role') or 'anon'
        ip = event_dict.get('ip_address') or '127.0.0.1'
        page = event_dict.get('page_url') or ''
        target = event_dict.get('target_element') or ''
        text = event_dict.get('target_text') or ''
        coords = event_dict.get('coordinates', {})

        coord_str = f" coords=({coords.get('x')},{coords.get('y')})" if coords else ""
        text_str = f' text="{text[:50]}"' if text else ""
        target_str = f' target="{target}"' if target else ""

        line = f"[{ts}] [{evt_type}] user={user} ({role}) ip={ip} page={page} event={evt_name}{target_str}{text_str}{coord_str}\n"
        with open(human_file, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass


def write_security_alert(request, threats, date_str=None):
    """
    Log detected cyber-attacks / intrusion attempts to logs/<date>/security_audit.log
    and master activity_audit.jsonl.
    """
    try:
        ctx = get_request_context(request)
        ts = datetime.now(timezone.utc).isoformat()
        folder = get_dated_log_dir(date_str)
        sec_log = folder / 'security_audit.log'

        threat_types = ", ".join(t['type'] for t in threats)
        details_list = "\n".join(f"  - [{t['type']}] Matched: {t['matched']!r} in {t['source']} ({t['location']})" for t in threats)

        banner = "=" * 80
        report = (
            f"\n{banner}\n"
            f"[{ts}] [SECURITY_THREAT_DETECTED] [SEVERITY: HIGH]\n"
            f"Threats Detected : {threat_types}\n"
            f"Client IP        : {ctx['ip_address']}\n"
            f"User Identity    : {ctx['username']} (Role: {ctx['user_role']}, ID: {ctx['user_id']})\n"
            f"Session Key      : {ctx['session_key']}\n"
            f"Request ID       : {ctx['request_id']}\n"
            f"Target Endpoint  : {request.method} {request.get_full_path()}\n"
            f"Referrer         : {ctx['referrer']}\n"
            f"User-Agent       : {ctx['user_agent']}\n"
            f"Device Telemetry : {ctx['device_type']} ({ctx['browser']} on {ctx['os']})\n"
            f"Threat Breakdown :\n{details_list}\n"
            f"Action Taken     : FLAGGED & RECORDED FOR SECURITY FORENSICS\n"
            f"{banner}\n"
        )

        with open(sec_log, 'a', encoding='utf-8') as f:
            f.write(report)

        # Also write structured JSON to activity_audit.jsonl
        audit_entry = {
            'timestamp': ts,
            'event_type': 'security_threat',
            'event_name': 'attack_detected',
            'threats': threats,
            'path': request.path,
            'full_url': request.get_full_path(),
            'method': request.method,
            **ctx
        }
        write_json_audit_log(audit_entry, date_str)
    except Exception:
        pass


def log_crash_forensics(request, exception, tb_str=None, date_str=None):
    """
    Deep Crash Forensics & Post-Mortem.
    Records EXACTLY:
      - Point of crash (File, Function, Line)
      - Who was involved (User, Role, ID, Email, IP)
      - What they were doing (URL, Method, Inputs, Query params, sanitized body)
      - System resources (RAM MB, CPU %)
      - Full Exception stack trace
    Writes to logs/<date>/crash_reports.log and logs/<date>/activity_audit.jsonl.
    """
    try:
        ts = datetime.now(timezone.utc).isoformat()
        ctx = get_request_context(request)
        crash_id = f"crash_{uuid.uuid4().hex[:8]}"

        # Extract code crash point from traceback
        exc_type = type(exception).__name__
        exc_msg = str(exception)
        tb = tb_str or traceback.format_exc()

        # Find the last application frame in traceback
        last_frame_info = "Unknown Location"
        try:
            tb_obj = sys.exc_info()[2]
            if tb_obj:
                frames = traceback.extract_tb(tb_obj)
                if frames:
                    last_frame = frames[-1]
                    last_frame_info = f"File \"{last_frame.filename}\", line {last_frame.lineno}, in {last_frame.name}\n    Code: {last_frame.line}"
        except Exception:
            pass

        # Extract sanitized request parameters
        query_params = {}
        post_params = {}
        if request:
            try:
                query_params = sanitize_data(request.GET.dict())
            except Exception:
                pass
            try:
                if request.POST:
                    post_params = sanitize_data(request.POST.dict())
            except Exception:
                pass

        # Memory telemetry
        mem_mb = 0.0
        if psutil:
            try:
                proc = psutil.Process(os.getpid())
                mem_mb = proc.memory_info().rss / (1024 * 1024)
            except Exception:
                pass

        folder = get_dated_log_dir(date_str)
        crash_log_file = folder / 'crash_reports.log'

        banner = "=" * 80
        report = (
            f"\n{banner}\n"
            f"[{ts}] [CRASH_POST_MORTEM] CrashID: {crash_id}\n"
            f"Request ID       : {ctx.get('request_id')}\n"
            f"\n[WHO WAS INVOLVED]\n"
            f"User             : {ctx.get('username')} (ID: {ctx.get('user_id')}, Role: {ctx.get('user_role')})\n"
            f"Client IP        : {ctx.get('ip_address')}\n"
            f"Session Key      : {ctx.get('session_key')}\n"
            f"Device Telemetry : {ctx.get('device_type')} ({ctx.get('browser')} on {ctx.get('os')})\n"
            f"User-Agent       : {ctx.get('user_agent')}\n"
            f"\n[WHAT THEY WERE DOING WHEN CRASH OCCURRED]\n"
            f"Action           : {request.method} {request.get_full_path() if request else 'N/A'}\n"
            f"Referrer         : {ctx.get('referrer') or 'Direct'}\n"
            f"Query Parameters : {json.dumps(query_params, ensure_ascii=False)}\n"
            f"Request Payload  : {json.dumps(post_params, ensure_ascii=False)}\n"
            f"\n[EXACT POINT OF CRASH & BUG DETAILS]\n"
            f"Exception Type   : {exc_type}\n"
            f"Exception Message: {exc_msg}\n"
            f"Crash Location   :\n  {last_frame_info}\n"
            f"\n[SYSTEM RESOURCES AT CRASH]\n"
            f"Process Memory   : {mem_mb:.1f} MB (PID: {os.getpid()})\n"
            f"\n[FULL STACK TRACE]\n{tb}\n"
            f"{banner}\n"
        )

        with open(crash_log_file, 'a', encoding='utf-8') as f:
            f.write(report)

        # Master JSON audit log
        audit_entry = {
            'timestamp': ts,
            'event_type': 'system_crash',
            'event_name': f"Crash: {exc_type}",
            'crash_id': crash_id,
            'exception_type': exc_type,
            'exception_message': exc_msg,
            'path': request.path if request else '',
            'method': request.method if request else '',
            'query_params': query_params,
            'payload': post_params,
            'memory_mb': round(mem_mb, 2),
            **ctx
        }
        write_json_audit_log(audit_entry, date_str)
    except Exception:
        pass

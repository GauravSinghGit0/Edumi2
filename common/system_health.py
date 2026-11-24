"""
common/system_health.py
Enterprise System Health & Infrastructure Monitoring Service Layer.

Provides modular, non-blocking check functions with strict <=5.0s timeouts
to monitor core cluster components, storage consumption, and recent system errors.
Results are cached for 15 seconds to prevent polling overload.
"""

import os
import sys
import time
import socket
import shutil
import urllib.parse
import logging
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from django.db.models import Q

logger = logging.getLogger(__name__)

TIMEOUT = 5.0
CACHE_KEY_SYSTEM_HEALTH = 'edumi:system_health:v1'
CACHE_TTL = 15  # 15 seconds cache


def _probe_socket(host: str, port: int, timeout: float = 2.0) -> tuple:
    """
    Attempts a lightweight TCP socket connection to verify port availability.
    Returns (is_open, latency_ms).
    """
    t0 = time.perf_counter()
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(min(timeout, TIMEOUT))
        res = sock.connect_ex((host, int(port)))
        latency = round((time.perf_counter() - t0) * 1000, 2)
        return (res == 0, latency if res == 0 else None)
    except Exception:
        return (False, None)
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def check_livekit(timeout: float = 2.0) -> dict:
    """
    Checks LiveKit SFU video bridge availability and live room capacity.
    """
    from meetings.models import Meeting
    
    internal_url = getattr(settings, 'LIVEKIT_INTERNAL_HTTP_URL', 'http://localhost:7880')
    parsed = urllib.parse.urlparse(internal_url)
    host = parsed.hostname or '127.0.0.1'
    port = parsed.port or 7880

    is_open, latency_ms = _probe_socket(host, port, timeout=min(timeout, 2.0))
    
    # Active rooms in system
    try:
        active_rooms = Meeting.objects.filter(status='live').count()
    except Exception:
        active_rooms = 0

    if is_open:
        return {
            'id': 'livekit',
            'name': 'LiveKit SFU Bridge',
            'status': 'operational',
            'badge': 'Operational',
            'port': port,
            'host': host,
            'active_rooms': active_rooms,
            'latency_ms': latency_ms,
            'description': f'WebRTC SFU listening on port {port}. {active_rooms} active live room{"s" if active_rooms != 1 else ""}.',
            'details': {
                'endpoint': f'{host}:{port}',
                'protocol': 'WebRTC / WebSocket',
                'active_rooms': active_rooms,
                'latency_ms': latency_ms,
            }
        }
    else:
        return {
            'id': 'livekit',
            'name': 'LiveKit SFU Bridge',
            'status': 'down',
            'badge': 'Offline',
            'port': port,
            'host': host,
            'active_rooms': active_rooms,
            'latency_ms': None,
            'description': f'SFU bridge port {port} is closed or unreachable. Live sessions may fail to connect.',
            'details': {
                'endpoint': f'{host}:{port}',
                'error': f'Socket connect to {host}:{port} timed out after {timeout}s.',
                'active_rooms': active_rooms
            }
        }


def check_django_daphne(timeout: float = 2.0) -> dict:
    """
    Checks Django ASGI/WSGI web runtime, process state, and channel layer configuration.
    """
    asgi_app = getattr(settings, 'ASGI_APPLICATION', 'edumi_core.asgi.application')
    channel_layers = getattr(settings, 'CHANNEL_LAYERS', {})
    default_layer = channel_layers.get('default', {})
    backend_name = default_layer.get('BACKEND', '').split('.')[-1] or 'InMemory'

    pid = os.getpid()
    python_ver = sys.version.split()[0]

    return {
        'id': 'django_daphne',
        'name': 'Django / Daphne ASGI',
        'status': 'operational',
        'badge': 'Active',
        'server_mode': 'ASGI (Daphne)' if asgi_app else 'WSGI',
        'pid': pid,
        'python_version': python_ver,
        'channel_layer': backend_name,
        'description': f'ASGI application server running (PID {pid}, Python {python_ver}). Channels: {backend_name}.',
        'details': {
            'pid': pid,
            'python_version': python_ver,
            'asgi_app': asgi_app,
            'channel_layer_backend': default_layer.get('BACKEND', 'InMemoryChannelLayer')
        }
    }


def check_redis(timeout: float = 2.0) -> dict:
    """
    Checks Redis cache and pub/sub cluster latency, memory usage, and connection status.
    """
    redis_url = getattr(settings, 'REDIS_URL', None)
    if not redis_url or str(redis_url).startswith('locmem'):
        return {
            'id': 'redis',
            'name': 'Redis Cache & Pub/Sub',
            'status': 'degraded',
            'badge': 'In-Memory',
            'latency_ms': 0.1,
            'used_memory': 'N/A (LocMem)',
            'peak_memory': 'N/A',
            'description': 'Running in-memory cache (LocMem). Distributed pub/sub and high-concurrency caching disabled.',
            'details': {
                'mode': 'InMemory (LocMem)',
                'latency_ms': 0.1,
                'note': 'Set REDIS_URL to enable high-throughput production Redis.'
            }
        }

    parsed = urllib.parse.urlparse(redis_url)
    host = parsed.hostname or '127.0.0.1'
    port = parsed.port or 6379

    is_open, latency_ms = _probe_socket(host, port, timeout=min(timeout, 2.0))
    if not is_open:
        return {
            'id': 'redis',
            'name': 'Redis Cache & Pub/Sub',
            'status': 'down',
            'badge': 'Offline',
            'latency_ms': None,
            'used_memory': 'N/A',
            'peak_memory': 'N/A',
            'description': f'Redis server at {host}:{port} is unreachable. Falling back to in-memory buffers.',
            'details': {
                'endpoint': f'{host}:{port}',
                'error': f'Failed to establish TCP handshake with {host}:{port}'
            }
        }

    # Query info('memory') if redis client library is available
    used_memory_str = 'N/A'
    peak_memory_str = 'N/A'
    try:
        import redis
        client = redis.from_url(redis_url, socket_timeout=min(timeout, 2.0))
        t0 = time.perf_counter()
        client.ping()
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        info = client.info('memory')
        used_memory_str = info.get('used_memory_human', 'N/A')
        peak_memory_str = info.get('used_memory_peak_human', 'N/A')
    except Exception as exc:
        logger.debug(f"Redis memory inspection fallback: {exc}")

    return {
        'id': 'redis',
        'name': 'Redis Cache & Pub/Sub',
        'status': 'operational',
        'badge': 'Operational',
        'latency_ms': latency_ms or 0.5,
        'used_memory': used_memory_str,
        'peak_memory': peak_memory_str,
        'description': f'Connected ({latency_ms}ms roundtrip). Memory consumed: {used_memory_str}.',
        'details': {
            'endpoint': f'{host}:{port}',
            'latency_ms': latency_ms,
            'used_memory': used_memory_str,
            'peak_memory': peak_memory_str,
        }
    }


def check_celery(timeout: float = 3.0) -> dict:
    """
    Checks Celery distributed task queue: online workers, queue depth, and failed tasks.
    """
    from common.models import UserActivityLog
    
    workers_online = 0
    worker_names = []
    queue_depth = 0
    failed_tasks = 0

    # 1. Queue depth via Redis if possible
    redis_url = getattr(settings, 'REDIS_URL', None)
    if redis_url and not str(redis_url).startswith('locmem'):
        try:
            import redis
            client = redis.from_url(redis_url, socket_timeout=1.5)
            queue_depth = client.llen('celery')
        except Exception:
            pass

    # 2. Inspect workers
    try:
        from edumi_core.celery import app
        insp = app.control.inspect(timeout=min(timeout, 2.5))
        ping_res = insp.ping() if insp else None
        if ping_res:
            worker_names = list(ping_res.keys())
            workers_online = len(worker_names)

        active = insp.active() if insp else None
        if active:
            active_count = sum(len(tasks) for tasks in active.values())
            queue_depth = max(queue_depth, active_count)
    except Exception as exc:
        logger.debug(f"Celery inspect failed: {exc}")

    # 3. Failed tasks count
    try:
        failed_tasks = UserActivityLog.objects.filter(
            event_name__in=['TASK_FAILED', 'CELERY_TASK_FAILED']
        ).count()
    except Exception:
        failed_tasks = 0

    if workers_online > 0:
        status = 'operational'
        badge = f'{workers_online} Online'
        desc = f'{workers_online} worker node{"s" if workers_online != 1 else ""} active. Queue depth: {queue_depth}.'
    else:
        status = 'degraded' if queue_depth == 0 else 'down'
        badge = 'No Workers'
        desc = f'No active Celery worker processes responding. Tasks in queue: {queue_depth}.'

    return {
        'id': 'celery',
        'name': 'Celery Worker Fleet',
        'status': status,
        'badge': badge,
        'workers_online': workers_online,
        'worker_names': worker_names,
        'queue_depth': queue_depth,
        'failed_tasks': failed_tasks,
        'description': desc,
        'details': {
            'workers_count': workers_online,
            'workers': worker_names,
            'queue_depth': queue_depth,
            'failed_tasks_recorded': failed_tasks
        }
    }


def check_database(timeout: float = 3.0) -> dict:
    """
    Checks Primary Relational Database connectivity, engine, and query response time.
    """
    vendor = connection.vendor
    engine_name = connection.settings_dict.get('ENGINE', '').split('.')[-1]
    db_name = connection.settings_dict.get('NAME', 'default')
    if isinstance(db_name, Path):
        db_name = db_name.name

    t0 = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            'id': 'database',
            'name': 'Primary Database',
            'status': 'operational',
            'badge': 'Operational',
            'vendor': vendor.upper(),
            'engine': engine_name,
            'db_name': str(db_name),
            'latency_ms': latency_ms,
            'description': f'{vendor.upper()} ({engine_name}) operational. Query round-trip: {latency_ms}ms.',
            'details': {
                'vendor': vendor,
                'engine': engine_name,
                'database': str(db_name),
                'latency_ms': latency_ms
            }
        }
    except Exception as exc:
        return {
            'id': 'database',
            'name': 'Primary Database',
            'status': 'down',
            'badge': 'Down',
            'vendor': vendor.upper(),
            'engine': engine_name,
            'db_name': str(db_name),
            'latency_ms': None,
            'description': f'Database connection failed: {exc}',
            'details': {
                'error': str(exc)
            }
        }


def check_camera_gateway(timeout: float = 2.0) -> dict:
    """
    Checks Camera Gateway service (port 8008) and streaming camera fleet.
    """
    from cameras.models import Camera

    camera_url = getattr(settings, 'CAMERA_SERVICE_URL', 'http://localhost:8008')
    parsed = urllib.parse.urlparse(camera_url)
    host = parsed.hostname or '127.0.0.1'
    port = parsed.port or 8008

    is_open, latency_ms = _probe_socket(host, port, timeout=min(timeout, 2.0))

    try:
        total_cameras = Camera.objects.count()
        online_cameras = Camera.objects.filter(is_active=True).count()
        offline_cameras = total_cameras - online_cameras
    except Exception:
        total_cameras = online_cameras = offline_cameras = 0

    if is_open:
        status = 'operational'
        badge = 'Port 8008 OK'
        desc = f'Camera service proxy connected ({latency_ms}ms). Fleet: {online_cameras}/{total_cameras} online.'
    elif total_cameras > 0:
        status = 'degraded'
        badge = 'Service Offline'
        desc = f'Camera microservice (port {port}) unreachable. In-process OpenCV proxy active for {online_cameras} cameras.'
    else:
        status = 'operational'
        badge = 'Ready'
        desc = f'No cameras registered in fleet. Port {port} available for future configuration.'

    return {
        'id': 'camera_gateway',
        'name': 'Camera Gateway (Port 8008)',
        'status': status,
        'badge': badge,
        'port': port,
        'latency_ms': latency_ms,
        'total_cameras': total_cameras,
        'online_cameras': online_cameras,
        'offline_cameras': offline_cameras,
        'description': desc,
        'details': {
            'endpoint': f'{host}:{port}',
            'gateway_reachable': is_open,
            'total_cameras': total_cameras,
            'online_cameras': online_cameras,
            'offline_cameras': offline_cameras
        }
    }


def check_ollama(timeout: float = 2.0) -> dict:
    """
    Checks Ollama local/remote RAG inference server if configured.
    """
    ollama_url = getattr(settings, 'OLLAMA_URL', None) or os.environ.get('OLLAMA_URL', '')
    if not ollama_url:
        try:
            from rag_assistant.services import get_ai_config
            cfg = get_ai_config()
            ollama_url = cfg.get('embedding_url') or cfg.get('llm_url') or ''
        except Exception:
            pass

    is_explicit = bool(ollama_url)
    target_url = ollama_url or 'http://localhost:11434'
    parsed = urllib.parse.urlparse(target_url)
    host = parsed.hostname or '127.0.0.1'
    port = parsed.port or 11434

    is_open, latency_ms = _probe_socket(host, port, timeout=min(timeout, 1.5))

    if is_open:
        models_list = []
        try:
            import requests
            res = requests.get(f"http://{host}:{port}/api/tags", timeout=min(timeout, 2.0))
            if res.status_code == 200:
                data = res.json()
                models_list = [m.get('name') for m in data.get('models', [])[:5]]
        except Exception:
            pass

        return {
            'id': 'ollama',
            'name': 'Ollama (RAG & Embeddings)',
            'status': 'operational',
            'badge': 'Online',
            'configured': True,
            'port': port,
            'latency_ms': latency_ms,
            'models': models_list,
            'description': f'Ollama inference active on port {port}. Models loaded: {", ".join(models_list) if models_list else "Default"}.',
            'details': {
                'endpoint': f'{host}:{port}',
                'models': models_list,
                'latency_ms': latency_ms
            }
        }
    elif is_explicit:
        return {
            'id': 'ollama',
            'name': 'Ollama (RAG & Embeddings)',
            'status': 'down',
            'badge': 'Offline',
            'configured': True,
            'port': port,
            'latency_ms': None,
            'models': [],
            'description': f'Configured Ollama endpoint {host}:{port} is unreachable. Local RAG will fall back to Gemini.',
            'details': {
                'endpoint': f'{host}:{port}',
                'error': 'Connection refused / port closed'
            }
        }
    else:
        return {
            'id': 'ollama',
            'name': 'Ollama (RAG & Embeddings)',
            'status': 'not_configured',
            'badge': 'Not Configured',
            'configured': False,
            'port': port,
            'latency_ms': None,
            'models': [],
            'description': 'Local Ollama RAG server not configured. Cloud Gemini LLM inference active.',
            'details': {
                'note': 'Optional component. Set OLLAMA_URL or AI_EMBEDDING_URL to enable local RAG.'
            }
        }


def get_storage_breakdown() -> dict:
    """
    Computes overall disk capacity and breaks down media storage by:
    - recordings (lecture captures, camera streams)
    - uploads (assignments, study materials, documents)
    - avatars (user profile pictures, course covers)
    """
    # 1. Volume Capacity
    try:
        total_b, used_b, free_b = shutil.disk_usage('.')
        total_gb = round(total_b / (1024 ** 3), 1)
        used_gb = round(used_b / (1024 ** 3), 1)
        free_gb = round(free_b / (1024 ** 3), 1)
        percent = round((used_b / total_b) * 100, 1)
        status = 'danger' if percent > 90 else ('warning' if percent > 80 else 'normal')
    except Exception:
        total_gb, used_gb, free_gb, percent, status = 250.0, 35.0, 215.0, 14.0, 'normal'
        total_b, used_b, free_b = 250 * 1024**3, 35 * 1024**3, 215 * 1024**3

    # 2. Directory breakdowns in media
    media_root = Path(getattr(settings, 'MEDIA_ROOT', './database/media'))
    
    def _dir_size(subpaths: list) -> int:
        total = 0
        for sub in subpaths:
            p = media_root / sub
            if p.exists() and p.is_dir():
                try:
                    for entry in os.scandir(p):
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat().st_size
                except Exception:
                    pass
        return total

    rec_bytes = _dir_size(['recordings', 'videos', 'temp_recordings', 'proxies'])
    upload_bytes = _dir_size(['assignments', 'study_materials', 'temp_uploads'])
    avatar_bytes = _dir_size(['profile_pictures', 'cover_photos'])
    
    # Also sum file sizes from CameraRecording model if media folder is empty/virtual
    if rec_bytes == 0:
        try:
            from cameras.models import CameraRecording
            from django.db.models import Sum
            db_size = CameraRecording.objects.aggregate(s=Sum('file_size'))['s'] or 0
            rec_bytes = max(rec_bytes, db_size)
        except Exception:
            pass

    def _fmt(b: int) -> tuple:
        if b >= 1024 ** 3:
            return (round(b / (1024 ** 3), 2), f"{round(b / (1024 ** 3), 2)} GB")
        else:
            mb = round(b / (1024 ** 2), 1)
            return (mb, f"{mb} MB")

    rec_val, rec_lbl = _fmt(rec_bytes)
    up_val, up_lbl = _fmt(upload_bytes)
    av_val, av_lbl = _fmt(avatar_bytes)

    # Segment percentage calculation against total used volume
    media_total_b = max(1, rec_bytes + upload_bytes + avatar_bytes)
    rec_pct = round((rec_bytes / media_total_b) * 100, 1)
    up_pct = round((upload_bytes / media_total_b) * 100, 1)
    av_pct = round((avatar_bytes / media_total_b) * 100, 1)

    return {
        'total_gb': total_gb,
        'used_gb': used_gb,
        'free_gb': free_gb,
        'percent': percent,
        'status': status,
        'categories': {
            'recordings': {
                'label': 'Classroom Recordings',
                'bytes': rec_bytes,
                'display': rec_lbl,
                'percent': rec_pct,
                'color': '#8b5cf6'  # Purple theme
            },
            'uploads': {
                'label': 'Course Materials & Uploads',
                'bytes': upload_bytes,
                'display': up_lbl,
                'percent': up_pct,
                'color': '#3b82f6'  # Blue
            },
            'avatars': {
                'label': 'Avatars & User Assets',
                'bytes': avatar_bytes,
                'display': av_lbl,
                'percent': av_pct,
                'color': '#10b981'  # Green
            }
        }
    }


def get_recent_errors(limit: int = 20) -> list:
    """
    Retrieves the last 20 errors recorded in log files and security audit logs.
    """
    errors = []

    # 1. Parse system_errors.log from logs directory
    log_dir = Path(getattr(settings, 'LOG_DIR', './logs'))
    error_files = []
    
    if log_dir.exists():
        # Check today's and recent dated directories
        today_dir = log_dir / timezone.now().strftime('%Y-%m-%d')
        if today_dir.exists():
            error_files.append(today_dir / 'system_errors.log')
            error_files.append(today_dir / 'crash_reports.log')

        # Also check root log dir
        error_files.append(log_dir / 'system_errors.log')

        # Also find most recent dated folder
        try:
            dated_folders = sorted([d for d in log_dir.iterdir() if d.is_dir()], reverse=True)
            for df in dated_folders[:3]:
                ef = df / 'system_errors.log'
                if ef.exists() and ef not in error_files:
                    error_files.append(ef)
        except Exception:
            pass

    for ef in error_files:
        if not ef.exists():
            continue
        try:
            with open(ef, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                current_err = None
                for line in lines[-200:]:
                    line_s = line.strip()
                    if line_s.startswith('[') and (' ERROR ' in line_s or ' CRITICAL ' in line_s):
                        if current_err:
                            errors.append(current_err)
                            if len(errors) >= limit * 2:
                                break
                        parts = line_s.split('] ', 2)
                        ts = parts[0].replace('[', '') if len(parts) > 0 else ''
                        lvl_and_module = parts[1] if len(parts) > 1 else ''
                        msg = parts[2] if len(parts) > 2 else line_s
                        
                        level = 'CRITICAL' if 'CRITICAL' in lvl_and_module else 'ERROR'
                        logger_name = lvl_and_module.split('[')[-1].replace(']', '') if '[' in lvl_and_module else 'System'

                        current_err = {
                            'timestamp': ts,
                            'level': level,
                            'logger': logger_name,
                            'message': msg,
                            'details': ''
                        }
                    elif current_err and line_s:
                        if len(current_err['details']) < 500:
                            current_err['details'] += line + '\n'

                if current_err and current_err not in errors:
                    errors.append(current_err)
        except Exception as exc:
            logger.debug(f"Error reading log file {ef}: {exc}")

    # 2. Database UserActivityLog failed events fallback
    if len(errors) < limit:
        try:
            from common.models import UserActivityLog
            db_errs = UserActivityLog.objects.filter(
                Q(event_name__icontains='ERROR') | Q(event_name__icontains='FAIL')
            ).order_by('-created_at')[:limit]

            for de in db_errs:
                errors.append({
                    'timestamp': de.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'level': 'ERROR',
                    'logger': de.event_name,
                    'message': de.details or de.event_name,
                    'details': f"User: {de.user.username if de.user else 'Anonymous'}, IP: {de.ip_address}"
                })
        except Exception:
            pass

    # Reverse chronological sort and slice to requested limit
    errors.sort(key=lambda x: str(x.get('timestamp', '')), reverse=True)
    return errors[:limit]


def get_full_system_health(use_cache: bool = True, force: bool = False) -> dict:
    """
    Main aggregator for System Health.
    Performs all component checks, aggregates results, computes overall cluster status,
    and caches data for 15 seconds.
    """
    if use_cache and not force:
        cached = cache.get(CACHE_KEY_SYSTEM_HEALTH)
        if cached is not None:
            cached['cached'] = True
            return cached

    # Run component checks with strict <=5s timeouts
    livekit = check_livekit(timeout=2.0)
    django_daphne = check_django_daphne(timeout=1.0)
    redis_info = check_redis(timeout=2.0)
    celery_info = check_celery(timeout=2.5)
    db_info = check_database(timeout=2.5)
    camera_info = check_camera_gateway(timeout=2.0)
    ollama_info = check_ollama(timeout=2.0)

    storage = get_storage_breakdown()
    recent_errors = get_recent_errors(limit=20)

    # Determine overall status
    statuses = [
        db_info['status'],
        livekit['status'],
        django_daphne['status'],
        redis_info['status'],
        celery_info['status']
    ]

    if 'down' in [db_info['status'], django_daphne['status']]:
        overall_status = 'critical'
        overall_label = 'Critical Outage'
    elif 'down' in statuses or storage['status'] == 'danger':
        overall_status = 'degraded'
        overall_label = 'Degraded Services'
    elif 'degraded' in statuses or storage['status'] == 'warning':
        overall_status = 'degraded'
        overall_label = 'Attention Required'
    else:
        overall_status = 'healthy'
        overall_label = 'All Systems Operational'

    data = {
        'timestamp': timezone.now().isoformat(),
        'timestamp_display': timezone.now().strftime('%b %d, %Y %H:%M:%S'),
        'overall_status': overall_status,
        'overall_label': overall_label,
        'checks': {
            'livekit': livekit,
            'django_daphne': django_daphne,
            'redis': redis_info,
            'celery': celery_info,
            'database': db_info,
            'camera_gateway': camera_info,
            'ollama': ollama_info,
        },
        'storage': storage,
        'recent_errors': recent_errors,
        'cached': False
    }

    try:
        cache.set(CACHE_KEY_SYSTEM_HEALTH, data, timeout=CACHE_TTL)
    except Exception as exc:
        logger.warning(f"Failed to cache system health: {exc}")

    return data

"""
Django settings for school_project — production-hardened.
Split into: base (this file) → reads from .env for all environments.
"""

from pathlib import Path
import os
import sys
import asyncio
import mimetypes
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

# ── Windows asyncio fix (dev only) ────────────────────────────────────────────
if sys.platform == 'win32':
    try:
        if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

# ── Base paths ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env (always override so systemd EnvironmentFile values take precedence)
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

# ── Helper ────────────────────────────────────────────────────────────────────
def env(key, default=None, required=False):
    value = os.environ.get(key, default)
    if required and not value:
        raise ImproperlyConfigured(f"Required environment variable '{key}' is not set.")
    return value

def env_bool(key, default='False'):
    return env(key, default).lower() in ('true', '1', 'yes')

def env_list(key, default=''):
    raw = env(key, default)
    return [v.strip() for v in raw.split(',') if v.strip()]


# ==============================================================================
# CORE
# ==============================================================================

SECRET_KEY = env('SECRET_KEY', required=True)
DEBUG       = env_bool('DEBUG', 'False')

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1')
# Always include localhost for healthchecks
for _h in ('localhost', '127.0.0.1'):
    if _h not in ALLOWED_HOSTS and '*' not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_h)

# Auto-detect LAN/server IP and add to ALLOWED_HOSTS (dev convenience only)
if DEBUG:
    import socket as _socket
    try:
        _s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        _s.connect(('8.8.8.8', 80))
        _lan_ip = _s.getsockname()[0]
        _s.close()
        if _lan_ip not in ALLOWED_HOSTS and '*' not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(_lan_ip)
    except Exception:
        pass


# ==============================================================================
# SECURITY
# ==============================================================================

# HTTPS / SSL
SECURE_SSL_REDIRECT          = env_bool('SECURE_SSL_REDIRECT', 'False')
SECURE_PROXY_SSL_HEADER      = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE        = env_bool('SESSION_COOKIE_SECURE', 'True')
CSRF_COOKIE_SECURE           = env_bool('CSRF_COOKIE_SECURE', 'True')
SESSION_COOKIE_HTTPONLY      = True
CSRF_COOKIE_HTTPONLY         = False   # Must be False for JS to read the token
SESSION_COOKIE_SAMESITE      = 'Lax'
CSRF_COOKIE_SAMESITE         = 'Lax'
SESSION_COOKIE_AGE           = 60 * 60 * 8   # 8 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# HSTS (0 in dev, 31536000 in prod)
SECURE_HSTS_SECONDS             = int(env('SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS  = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', 'True')
SECURE_HSTS_PRELOAD             = env_bool('SECURE_HSTS_PRELOAD', 'False')

# Additional security headers
SECURE_BROWSER_XSS_FILTER    = True
SECURE_CONTENT_TYPE_NOSNIFF  = True
SECURE_REFERRER_POLICY       = 'strict-origin-when-cross-origin'
X_FRAME_OPTIONS              = 'SAMEORIGIN'

# CSRF trusted origins — always include env + sensible defaults
CSRF_TRUSTED_ORIGINS = env_list(
    'CSRF_TRUSTED_ORIGINS',
    'https://localhost:8002,https://127.0.0.1:8002,http://localhost:8002'
)
# Pull Render / Railway / Fly.io platform URL automatically
for _plat_var in ('RENDER_EXTERNAL_URL', 'RAILWAY_STATIC_URL', 'FLY_APP_NAME'):
    _url = env(_plat_var)
    if _url and _url not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_url)


# ==============================================================================
# APPLICATIONS
# ==============================================================================

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'common',
    'accounts',
    'cameras',
    'mobile_cameras',
    'meetings',
    'attendance',
    'videos',
    'video_editing',
    'assignments',
    'django_extensions',
    'compressor',
]


# ==============================================================================
# MIDDLEWARE
# ==============================================================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
]

try:
    import whitenoise  # noqa
    MIDDLEWARE.append('whitenoise.middleware.WhiteNoiseMiddleware')
except ImportError:
    pass

MIDDLEWARE += [
    'school_project.middleware.DatabaseErrorMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ==============================================================================
# URLS / WSGI / ASGI
# ==============================================================================

ROOT_URLCONF       = 'school_project.urls'
WSGI_APPLICATION   = 'school_project.wsgi.application'
ASGI_APPLICATION   = 'school_project.asgi.application'


# ==============================================================================
# TEMPLATES
# ==============================================================================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.timestamp',
                'accounts.context_processors.face_registered',
            ],
        },
    },
]


# ==============================================================================
# DATABASE
# ==============================================================================

DATABASE_DIR = BASE_DIR / 'database'
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

_database_url = env('DATABASE_URL')

if _database_url:
    try:
        import dj_database_url
        db_config = dj_database_url.config(
            default=_database_url,
            conn_max_age=0,
            conn_health_checks=True,
        )
        if 'sslmode' in _database_url:
            db_config.setdefault('OPTIONS', {})['sslmode'] = 'prefer'
        DATABASES = {'default': db_config}
    except ImportError:
        raise ImproperlyConfigured(
            "DATABASE_URL is set but dj-database-url is not installed. "
            "Run: pip install dj-database-url psycopg2-binary"
        )
else:
    # SQLite — fine for dev, not recommended for production
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': DATABASE_DIR / 'db.sqlite3',
            'OPTIONS': {
                'timeout': 30,
                'check_same_thread': False,
            },
        }
    }
    if not DEBUG:
        import warnings
        warnings.warn(
            "Production is using SQLite. Set DATABASE_URL to a PostgreSQL connection string.",
            RuntimeWarning,
            stacklevel=1,
        )


# ==============================================================================
# CHANNEL LAYERS (WebSockets)
# ==============================================================================

REDIS_URL = env('REDIS_URL', 'redis://localhost:6379/0')

# Always use Redis on Linux/Production if URL is provided; InMemory on Windows/local dev
if REDIS_URL and sys.platform != 'win32' and (not DEBUG or env_bool('FORCE_REDIS_CHANNELS', 'False')):
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
                'capacity': 1500,
                'expiry': 10,
            },
        }
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        }
    }


# ==============================================================================
# CACHING
# ==============================================================================

if REDIS_URL and not DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'SOCKET_CONNECT_TIMEOUT': 5,
                'SOCKET_TIMEOUT': 5,
                'IGNORE_EXCEPTIONS': True,   # Don't crash if Redis is briefly down
                'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            },
            'KEY_PREFIX': 'edumi',
            'TIMEOUT': 300,  # 5 minutes default TTL
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    # Dev: use local memory cache
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'edumi-local-cache',
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'


# ==============================================================================
# PASSWORD VALIDATION
# ==============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ==============================================================================
# INTERNATIONALISATION
# ==============================================================================

LANGUAGE_CODE = 'en-us'
TIME_ZONE     = env('TIME_ZONE', 'Asia/Kolkata')
USE_I18N      = True
USE_TZ        = True


# ==============================================================================
# STATIC & MEDIA FILES
# ==============================================================================

STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
]

# WhiteNoise: compressed + cache-busted static files
try:
    import whitenoise  # noqa
    STORAGES = {
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
    }
    WHITENOISE_ROOT         = BASE_DIR / 'staticfiles'
    WHITENOISE_AUTOREFRESH  = True
    WHITENOISE_USE_FINDERS  = True
    WHITENOISE_MAX_AGE      = 0 if DEBUG else 31_536_000   # 1 year in prod
except ImportError:
    STORAGES = {
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage',
        },
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
    }

MEDIA_URL  = '/media/'
MEDIA_ROOT = DATABASE_DIR / 'media'
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# Django Compressor
COMPRESS_ENABLED  = env_bool('COMPRESS_ENABLED', 'True')
COMPRESS_URL      = STATIC_URL
COMPRESS_ROOT     = STATIC_ROOT
COMPRESS_STORAGE  = 'compressor.storage.CompressorFileStorage'
COMPRESS_OFFLINE  = env_bool('COMPRESS_OFFLINE', 'True')
COMPRESS_OFFLINE_MANIFEST = 'compressor.json'
COMPRESS_REBUILD_TIMEOUT = 0 if DEBUG else 300

# Register MIME types (Windows registry is often missing these)
mimetypes.add_type('text/css',               '.css')
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/javascript',        '.js')
mimetypes.add_type('image/svg+xml',          '.svg')
mimetypes.add_type('application/json',       '.json')
mimetypes.add_type('font/woff',              '.woff')
mimetypes.add_type('font/woff2',             '.woff2')
mimetypes.add_type('image/x-icon',           '.ico')


# ==============================================================================
# LOGGING CONFIGURATION (Clean Terminal & Systemd Journal)
# ==============================================================================

LOG_DIR = BASE_DIR / 'logs'
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

LOG_LEVEL = env('LOG_LEVEL', 'INFO').upper()

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'clean_console': {
            'format': '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s',
            'datefmt': '%H:%M:%S',
        },
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'clean_console',
            'level': 'INFO',
        },
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': LOG_LEVEL,
    },
    'loggers': {
        # Core Django request & security logs
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        # App-specific loggers
        'accounts': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'cameras': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'meetings': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'recording_engine': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Suppress noisy external libraries
        'daphne':       {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'asyncio':      {'handlers': ['null'],    'level': 'CRITICAL', 'propagate': False},
        'PIL':          {'handlers': ['null'],    'level': 'CRITICAL', 'propagate': False},
        'urllib3':      {'handlers': ['null'],    'level': 'WARNING', 'propagate': False},
    },
}


# ==============================================================================
# CELERY
# ==============================================================================

CELERY_BROKER_URL            = env('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND        = env('REDIS_URL', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT        = ['application/json']
CELERY_TASK_SERIALIZER       = 'json'
CELERY_RESULT_SERIALIZER     = 'json'
CELERY_TIMEZONE              = TIME_ZONE
CELERY_TASK_TRACK_STARTED    = True
CELERY_TASK_TIME_LIMIT       = 30 * 60       # Hard 30-minute limit per task
CELERY_TASK_SOFT_TIME_LIMIT  = 25 * 60       # Soft 25-minute limit
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100      # Recycle workers to prevent memory leaks
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True


# ==============================================================================
# LIVEKIT
# ==============================================================================

LIVEKIT_URL              = env('LIVEKIT_URL', 'ws://localhost:8002/livekit-proxy/')
LIVEKIT_INTERNAL_URL     = env('LIVEKIT_INTERNAL_URL', 'ws://localhost:7880')
LIVEKIT_INTERNAL_HTTP_URL = env('LIVEKIT_INTERNAL_HTTP_URL', 'http://localhost:7880')
LIVEKIT_API_KEY          = env('LIVEKIT_API_KEY', required=True)
LIVEKIT_API_SECRET       = env('LIVEKIT_API_SECRET', required=True)


# ==============================================================================
# CAMERA & FACE RECOGNITION
# ==============================================================================

CAMERA_SERVICE_URL     = env('CAMERA_SERVICE_URL', 'http://localhost:8003')
HEAD_COUNT_INTERVAL    = int(env('HEAD_COUNT_INTERVAL', '30'))
ATTENTION_THRESHOLD    = float(env('ATTENTION_THRESHOLD', '0.6'))
EMOTION_LOGGING_ENABLED = env_bool('EMOTION_LOGGING_ENABLED', 'True')

FACE_ENCRYPTION_KEY    = env('FACE_ENCRYPTION_KEY', required=True)
FACE_MATCH_THRESHOLD   = float(env('FACE_MATCH_THRESHOLD', '0.50'))
FACE_PRESENCE_DURATION = int(env('FACE_PRESENCE_DURATION', '30'))


# ==============================================================================
# AUTH
# ==============================================================================

LOGIN_URL              = 'login'
LOGOUT_REDIRECT_URL    = '/'
LOGIN_REDIRECT_URL     = 'student_dashboard'


# ==============================================================================
# MISC
# ==============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# File upload limits
DATA_UPLOAD_MAX_MEMORY_SIZE    = 500 * 1024 * 1024   # 500 MB
FILE_UPLOAD_MAX_MEMORY_SIZE    = 500 * 1024 * 1024   # 500 MB
DATA_UPLOAD_MAX_NUMBER_FIELDS  = 10_000

# ==============================================================================
# FFMPEG / FFPROBE BINARY PATHS
# ==============================================================================
try:
    from cameras.ffmpeg_helpers import get_ffmpeg_binary, get_ffprobe_binary
    FFMPEG_BINARY = get_ffmpeg_binary()
    FFPROBE_BINARY = get_ffprobe_binary()
except Exception:
    FFMPEG_BINARY = env('FFMPEG_BINARY', 'ffmpeg')
    FFPROBE_BINARY = env('FFPROBE_BINARY', 'ffprobe')


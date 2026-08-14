"""Camera Service Settings - Dedicated RTSP streaming service"""
from pathlib import Path
import os
import sys

# Add parent directory to path to access main project's database
BASE_DIR = Path(__file__).resolve().parent.parent
MAIN_PROJECT_DIR = BASE_DIR.parent

sys.path.insert(0, str(MAIN_PROJECT_DIR))

from dotenv import load_dotenv
load_dotenv(MAIN_PROJECT_DIR / '.env', override=True)

SECRET_KEY = os.environ.get('CAMERA_SERVICE_SECRET_KEY', 'camera-service-key-change-in-production')
DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '10.17.2.47', '*']

# Disable SSL redirect for development (enable in production)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = [
    'https://localhost',
    'https://localhost:8443',
    'https://127.0.0.1',
    'https://127.0.0.1:8443',
    'https://10.17.2.47',
    'https://10.17.2.47:8443',
]
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    SECURE_HSTS_SECONDS = 0

SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CONTENT_TYPE_NOSNIFF = True

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'corsheaders',
    'cameras',  # Need Camera model
    'mobile_cameras',  # Need MobileCamera model
    'accounts',  # Need UserProfile model for mobile camera permissions
    'meetings',  # Need Classroom model for head count feature
    'camera_api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
]

# CORS settings - allow main app to access camera service
CORS_ALLOWED_ORIGINS = [
    "https://localhost",
    "https://localhost:8002",
    "https://localhost:8443",
    "https://127.0.0.1",
    "https://127.0.0.1:8002",
    "https://127.0.0.1:8443",
    "http://localhost:8002",
    "http://127.0.0.1:8002",
    "http://10.7.11.141:8002",
    "https://10.7.11.141:8002",
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = True  # Allow all origins for development

ROOT_URLCONF = 'camera_service.urls'

# Use the same database as main project
DATABASE_DIR = MAIN_PROJECT_DIR / 'database'
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

if os.environ.get('DATABASE_URL'):
    import dj_database_url
    db_config = dj_database_url.config(conn_max_age=0)
    if 'sslmode' in os.environ.get('DATABASE_URL', ''):
        db_config.setdefault('OPTIONS', {})['sslmode'] = 'prefer'
    DATABASES = {'default': db_config}
else:
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

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'camera_api': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

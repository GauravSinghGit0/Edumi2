"""WSGI config for camera service"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'camera_service.settings')
application = get_wsgi_application()

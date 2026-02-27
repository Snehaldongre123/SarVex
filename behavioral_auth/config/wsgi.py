"""
config/wsgi.py — WSGI entry point for production deployment (gunicorn, uWSGI, etc.)
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = get_wsgi_application()

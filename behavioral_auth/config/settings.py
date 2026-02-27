"""
config/settings.py
Passwordless Behavioral Authentication System
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------
# SECURITY
# ------------------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-change-this")
DEBUG = True
ALLOWED_HOSTS = []

# ------------------------------------------------------------------
# INSTALLED APPS
# ------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'authcore',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

# ------------------------------------------------------------------
# DATABASE (PostgreSQL)
# ------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ------------------------------------------------------------------
# CUSTOM USER MODEL
# ------------------------------------------------------------------
AUTH_USER_MODEL = 'authcore.User'

# Disable password validators (we don’t use passwords)
AUTH_PASSWORD_VALIDATORS = []

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# ------------------------------------------------------------------
# SESSION SETTINGS
# ------------------------------------------------------------------
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# ------------------------------------------------------------------
# REST FRAMEWORK
# ------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
}

# ------------------------------------------------------------------
# BEHAVIOR CONFIG
# ------------------------------------------------------------------
BEHAVIOR_CONFIG = {
    'TYPING_SPEED_TOLERANCE': 0.30,
    'KEY_HOLD_TOLERANCE': 0.30,
    'MOUSE_VELOCITY_TOLERANCE': 0.40,
    'CLICK_INTERVAL_TOLERANCE': 0.35,
    'SCROLL_DEPTH_TOLERANCE': 0.50,
    'MAX_NETWORK_LATENCY_MS': 300,
    'TRUST_SCORE_THRESHOLD': 60,
    'BASELINE_LOG_COUNT': 5,
}

# ------------------------------------------------------------------
# DEFAULTS
# ------------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_TZ = True
STATIC_URL = 'static/'
# ------------------------------------------------------------------
# TEMPLATES (Required for Django Admin)
# ------------------------------------------------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],  # You can add custom template folders later
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
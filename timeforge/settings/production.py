from .base import *
import dj_database_url
from decouple import config, Csv
import os

DEBUG = config("DEBUG", default=False, cast=bool)

# Render sets 'RENDER_EXTERNAL_HOSTNAME' in production, or read from ALLOWED_HOSTS
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default=os.getenv('RENDER_EXTERNAL_HOSTNAME', ''), cast=Csv())

# Database configuration via dj_database_url
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default='postgres://localhost'),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Static Files (WhiteNoise)
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Security Settings
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=True, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)

# HSTS settings (recommended for production)
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True, cast=bool)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=True, cast=bool)

# Trust the Render external hostname for CSRF
if 'RENDER_EXTERNAL_HOSTNAME' in os.environ:
    CSRF_TRUSTED_ORIGINS = [f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}"]
else:
    CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())

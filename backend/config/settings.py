"""Django settings. Everything that differs between laptop and server comes from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # local development only; the server sets real env vars


def env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes"}


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("Set DJANGO_SECRET_KEY (or DJANGO_DEBUG=true for local development).")
    SECRET_KEY = "local-development-only"

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]

# Routing uses TomTom when this key is set, otherwise the public OSRM demo server.
TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "").strip()

INSTALLED_APPS = [
    "rest_framework",
    "trips",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",  # trip responses are large JSON; gzip cuts them ~10x
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# No database: the app keeps nothing between requests except the cache below.
DATABASES = {}

# One process with threads on the server, so this in-memory cache is shared by all requests.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "truck-routing",
        "OPTIONS": {"MAX_ENTRIES": 50_000},
    }
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    # Protects the free API quotas (TomTom: 2,500 requests/day).
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "trips": os.environ.get("TRIPS_RATE", "60/hour"),  # a trip is 2 calls: routes, then heatmap
        "geocode": os.environ.get("GEOCODE_RATE", "120/minute"),
    },
}

USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # the host terminates HTTPS
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^api/health$"]  # the host's health check may use plain HTTP
    SECURE_HSTS_SECONDS = 3600

# CSRF protects cookie-based logins. This API has no logins or cookies, so the check does not apply.
SILENCED_SYSTEM_CHECKS = ["security.W003"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    # urllib3 prints full request URLs when it retries; the TomTom key is in the URL, so keep it quiet.
    "loggers": {"urllib3": {"level": "ERROR"}},
}

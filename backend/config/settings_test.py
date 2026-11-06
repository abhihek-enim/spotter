"""Settings for pytest: debug on, no real API key, generous rate limits."""

import os

os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ["TOMTOM_API_KEY"] = ""  # set before settings load .env, so tests never use a real key

from .settings import *  # noqa: E402,F403

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"trips": "1000/minute", "geocode": "1000/minute"}  # noqa: F405

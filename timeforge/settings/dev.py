"""
Local development settings.

Requires a `.env` file at the project root so misconfigured machines fail
loudly instead of falling back to insecure defaults.
"""

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = _BASE_DIR / ".env"

if not ENV_FILE.is_file():
    raise ImproperlyConfigured(
        "Missing .env file at the project root. "
        "Copy .env.example to .env and configure your local environment. "
        "See docs/SETUP.md for step-by-step instructions."
    )

from .base import *  # noqa: E402, F403

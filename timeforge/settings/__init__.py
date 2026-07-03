"""
TimeForge settings package.

Default entry point (`timeforge.settings`) loads dev settings for local work.
Production deployments should set DJANGO_SETTINGS_MODULE to a dedicated module
when one is added (e.g. timeforge.settings.prod).
"""

from .dev import *  # noqa: F403

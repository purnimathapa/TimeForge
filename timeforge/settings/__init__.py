"""
TimeForge settings package.

Default entry point (`timeforge.settings`) loads dev settings for local work.
Production deployments should set DJANGO_SETTINGS_MODULE to a dedicated module
when one is added (e.g. timeforge.settings.prod).
"""

import os

if os.getenv('DJANGO_ENV') == 'production':
    from .production import *
else:
    from .dev import *

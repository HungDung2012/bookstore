"""
ASGI config for advisor_service project.

It exposes the ASGI callable as a module-level variable named ``application``.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "advisor_service.settings")

application = get_asgi_application()

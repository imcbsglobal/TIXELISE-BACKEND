import os  # noqa: F401

from .base import *  # noqa: F401,F403

DEBUG = False

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # noqa: F405

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ["DJANGO_ALLOWED_HOSTS"].split(",")
    if h.strip()
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))

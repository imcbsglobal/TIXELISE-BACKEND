from .base import *  # noqa: F401,F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# SQLite when no DATABASE_URL is set (base.py handles the switch).

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "apps": {"handlers": ["console"], "level": "WARNING"},
        "django.request": {"handlers": ["console"], "level": "WARNING"},
    },
}

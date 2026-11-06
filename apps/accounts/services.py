import html
import json
import os
from urllib import error, request

from django.contrib.auth import get_user_model

User = get_user_model()

DEFAULT_SUPERUSER_ENDPOINT = "https://su.myimc.in/api/superusers/endpoint/TIXELISE/EUH6POZG/"


def sync_platform_superuser_from_external_api():
    """Sync the local platform superuser with the configured external API."""
    endpoint = os.getenv("TIXELISE_SUPERUSER_ENDPOINT", DEFAULT_SUPERUSER_ENDPOINT)
    if not endpoint:
        return False

    try:
        with request.urlopen(
            request.Request(endpoint, headers={"User-Agent": "Tixelise/1.0"}),
            timeout=10,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, ValueError, TimeoutError):
        return False

    if not isinstance(payload, dict):
        return False

    if str(payload.get("status", "")).strip().lower() != "active":
        return False

    username = html.unescape(str(payload.get("username") or "")).strip()
    password = html.unescape(str(payload.get("password") or "")).strip()
    if not username or not password:
        return False

    user, _ = User.objects.get_or_create(
        username=username,
        defaults={
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
            "is_platform_admin": True,
        },
    )

    user.is_active = True
    user.is_staff = True
    user.is_superuser = True
    user.is_platform_admin = True
    user.set_password(password)

    if payload.get("email"):
        user.email = str(payload.get("email"))

    user.save(
        update_fields=[
            "password",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "is_platform_admin",
        ]
    )
    return True

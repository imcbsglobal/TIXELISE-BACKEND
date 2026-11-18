import html
import json
import os
from urllib import error, request

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.core.exceptions import CentralMasterUnavailable, TixeliseAPIException

User = get_user_model()

DEFAULT_SUPERUSER_ENDPOINT = "https://su.myimc.in/api/superusers/endpoint/TIXELISE/EUH6POZG/"
TENANT_LICENSE_LOOKUP_URL = (
    "https://activate.imcbs.com/mobileapp/api/project/tixelise/"
)


def tenant_license_profile_for_login(client_id):
    """Return verified license details needed to bootstrap a missing tenant."""
    req = request.Request(
        TENANT_LICENSE_LOOKUP_URL,
        headers={"User-Agent": "Tixelise/1.0"},
    )
    try:
        with request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, OSError) as exc:
        raise CentralMasterUnavailable(
            "The tenant license service could not be reached or returned invalid data."
        ) from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("customers"), list):
        raise CentralMasterUnavailable(
            "The tenant license service returned an invalid response."
        )

    wanted_client = (client_id or "").strip().casefold()
    for customer in payload["customers"]:
        if not isinstance(customer, dict):
            continue
        returned_client = str(customer.get("client_id") or "").strip()
        if returned_client.casefold() != wanted_client:
            continue
        active = str(customer.get("status") or "").strip().casefold() == "active"
        validity = customer.get("license_validity") or {}
        if not active or not isinstance(validity, dict) or validity.get("is_expired") is True:
            raise TixeliseAPIException(
                detail="The organization license is inactive or expired.",
                code="TENANT_LICENSE_INACTIVE",
                status_code=403,
            )
        name = str(customer.get("customer_name") or "").strip()
        if not name:
            raise CentralMasterUnavailable(
                "The tenant license service did not return an organization name."
            )
        return {"code": returned_client, "name": name}

    raise TixeliseAPIException(
        detail="Unknown tenant code.",
        code="TENANT_NOT_FOUND",
        status_code=404,
    )


def authenticate_central_tenant_user(client_id, username, password):
    """Verify tenant credentials and Tixelise access with the central master."""
    payload = {
        "client_id": client_id,
        "username": username,
        "password": password,
        "project": "tixelise",
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        settings.CENTRAL_USER_LOGIN_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Tixelise/1.0",
        },
    )

    try:
        with request.urlopen(
            req, timeout=settings.CENTRAL_USER_LOGIN_TIMEOUT_SECONDS
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        if exc.code == 401:
            return False
        if exc.code in (400, 403):
            raise TixeliseAPIException(
                detail="This account is not authorized for Tixelise.",
                code="CENTRAL_ACCESS_DENIED",
                status_code=403,
            ) from exc
        raise CentralMasterUnavailable(
            f"The central login service returned HTTP {exc.code}."
        ) from exc
    except (error.URLError, TimeoutError, ValueError, OSError) as exc:
        raise CentralMasterUnavailable(
            "The central login service could not be reached or returned invalid data."
        ) from exc

    if not isinstance(result, dict):
        raise CentralMasterUnavailable(
            "The central login service returned an invalid response."
        )
    if result.get("success") is not True:
        return False
    if result.get("project") != "tixelise" or result.get("project_enabled") is not True:
        raise TixeliseAPIException(
            detail="This account is not authorized for Tixelise.",
            code="CENTRAL_ACCESS_DENIED",
            status_code=403,
        )
    return True


def central_user_profile_for_login(client_id, username):
    """Read the central account details only when local provisioning is needed."""
    from apps.platform_admin import views as platform_views

    row, checked = platform_views._find_central_user(client_id, username)
    if not checked or not row:
        raise CentralMasterUnavailable(
            "The verified central account could not be read for local provisioning."
        )

    central_id = str(row.get("id") or "").strip()
    central_username = str(row.get("username") or "").strip()
    user_role = str(row.get("user_role") or "").strip().upper()
    status = str(row.get("status") or "").strip().upper()
    if (
        not central_id
        or not central_username
        or user_role not in {"ADMIN", "USER"}
        or status != "ACTIVE"
        or row.get("tixelise") is not True
    ):
        raise CentralMasterUnavailable(
            "The central account is missing required Tixelise user details."
        )

    return {
        "id": central_id,
        "username": central_username,
        "first_name": str(row.get("first_name") or "").strip(),
        "last_name": str(row.get("last_name") or "").strip(),
        "email": str(row.get("email") or "").strip(),
        "phone_number": str(row.get("phone_number") or "").strip(),
        "user_role": user_role,
    }


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

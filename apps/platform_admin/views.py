import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.exceptions import (
    CentralMasterUnavailable,
    CentralRegistrationRejected,
    CentralUpdateRejected,
    NotFound,
    TixeliseAPIException,
)
from apps.core.permissions import IsPlatformAdmin
from apps.tenancy.models import Tenant, TenantMembership
from apps.tenancy.services import delete_tenant

from .serializers import TenantCreateSerializer, TenantSerializer

CENTRAL_CURRENCY_URL = (
    "https://centralmastermanagement.imcbs.com/api/financial-year/country-wise/"
)
CURRENCY_MASTER_URL = (
    "https://centralmastermanagement.imcbs.com/api/currency-master/currencies/"
)
USER_MASTER_URL = "https://centralmastermanagement.imcbs.com/api/user-master/"

# The master keeps one row per account per product. Only Tixelise is enabled
# here; every other product flag must still be sent explicitly as false.
_PRODUCT_FLAGS = {
    "trellisco": False,
    "claudius": False,
    "melone": False,
    "tixelise": True,
    "trellisco_crm": False,
    "melone_stay": False,
    "trellisco_books": False,
}

# Long names for the currencies offered by the financial-year master, sent as
# `name` when a tenant's currency is registered in the central currency master.
_CURRENCY_NAMES = {
    "AED": "UAE Dirham",
    "BHD": "Bahraini Dinar",
    "INR": "Indian Rupee",
    "KWD": "Kuwaiti Dinar",
    "OMR": "Omani Rial",
    "QAR": "Qatari Riyal",
    "SAR": "Saudi Riyal",
}

# Used only when the central master list cannot be reached, so tenant creation
# is never blocked by an outage on a third-party host.
_FALLBACK_CURRENCIES = (
    ("BH", "BAHRAIN", "BHD", "JANUARY", "DECEMBER"),
    ("IN", "INDIA", "INR", "APRIL", "MARCH"),
    ("KW", "KUWAIT", "KWD", "JANUARY", "DECEMBER"),
    ("OM", "OMAN", "OMR", "JANUARY", "DECEMBER"),
    ("QA", "QATAR", "QAR", "JANUARY", "DECEMBER"),
    ("SA", "SAUDI ARABIA", "SAR", "JANUARY", "DECEMBER"),
    ("AE", "UNITED ARAB EMIRATES", "AED", "JANUARY", "DECEMBER"),
)

CURRENCY_CACHE_TTL_SECONDS = 300
_currency_cache = {"fetched_at": None, "results": None}


def _normalize_currency_rows(rows):
    options = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        currency_code = (row.get("currency_code") or "").strip().upper()
        country_code = (row.get("country_code") or "").strip().upper()
        if not currency_code or not country_code:
            continue
        options.append(
            {
                "country_code": country_code,
                "country_name": (row.get("country_name") or "").strip(),
                "currency_code": currency_code,
                "fy_from_month": (row.get("fy_from_month") or "").strip(),
                "fy_to_month": (row.get("fy_to_month") or "").strip(),
                "remark": (row.get("remark") or "").strip(),
            }
        )
    options.sort(key=lambda item: (item["country_name"], item["currency_code"]))
    return options


def _fallback_currency_options():
    return [
        {
            "country_code": country_code,
            "country_name": country_name,
            "currency_code": currency_code,
            "fy_from_month": fy_from,
            "fy_to_month": fy_to,
            "remark": "",
        }
        for country_code, country_name, currency_code, fy_from, fy_to in _FALLBACK_CURRENCIES
    ]


def _fetch_currency_options():
    """Return (options, source) where source is "remote" or "fallback"."""
    now = time.monotonic()
    cached_at = _currency_cache["fetched_at"]
    if (
        _currency_cache["results"]
        and cached_at is not None
        and now - cached_at < CURRENCY_CACHE_TTL_SECONDS
    ):
        return _currency_cache["results"], "remote"

    try:
        req = Request(CENTRAL_CURRENCY_URL, headers={"User-Agent": "Tixelise-Platform"})
        with urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, ValueError, OSError):
        payload = None

    options = _normalize_currency_rows(payload) if isinstance(payload, list) else []
    if not options:
        return _fallback_currency_options(), "fallback"

    _currency_cache["fetched_at"] = now
    _currency_cache["results"] = options
    return options, "remote"


def _currency_already_registered(client_id, currency_code):
    try:
        req = Request(CURRENCY_MASTER_URL, headers={"User-Agent": "Tixelise-Platform"})
        with urlopen(req, timeout=5) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, ValueError, OSError):
        return False

    if not isinstance(rows, list):
        return False

    for row in rows:
        if not isinstance(row, dict):
            continue
        same_client = (row.get("client_id") or "").strip().upper() == client_id
        same_code = (row.get("code") or "").strip().upper() == currency_code
        if same_client and same_code:
            return True
    return False


def _register_tenant_currency(client_id, currency_code):
    """
    Best-effort registration of a tenant's currency in the central currency
    master. Never raises — the outcome is returned so the caller can decide how
    to report it. A third-party outage must not block tenant onboarding.
    """
    client_id = (client_id or "").strip().upper()
    currency_code = (currency_code or "").strip().upper()
    if not client_id or not currency_code:
        return {"status": "skipped", "detail": "Tenant code or currency missing."}

    if _currency_already_registered(client_id, currency_code):
        return {"status": "skipped", "detail": "Already present in the currency master."}

    body = json.dumps(
        {
            "client_id": client_id,
            "code": currency_code,
            "name": _CURRENCY_NAMES.get(currency_code, currency_code),
            "status": "ACTIVE",
        }
    ).encode("utf-8")
    req = Request(
        CURRENCY_MASTER_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "Tixelise-Platform"},
    )

    try:
        with urlopen(req, timeout=5) as resp:
            resp.read()
    except HTTPError as exc:
        return {"status": "failed", "detail": f"Currency master returned HTTP {exc.code}."}
    except (URLError, TimeoutError, OSError):
        return {"status": "failed", "detail": "Currency master unreachable."}

    return {
        "status": "registered",
        "detail": f"{currency_code} registered for {client_id}.",
    }


# The central master is a shared third-party host: a create that validates
# uniqueness can take several seconds, so the 5s used for the read-only lookups
# is too tight for it.
CENTRAL_TIMEOUT_SECONDS = 20


def _http_error_detail(exc):
    """Field-level message from the master, without any echoed secret.

    The master answers a rejected create with ``{"phone_number": ["..."]}``,
    which is far more useful than the bare status code.
    """
    payload = None
    try:
        raw = exc.read()
        payload = json.loads(raw.decode("utf-8")) if raw else None
    except (ValueError, OSError, AttributeError):
        payload = None

    if isinstance(payload, dict):
        payload.pop("password", None)
        detail = payload.get("detail") or payload.get("message") or payload
    else:
        detail = payload

    text = detail if isinstance(detail, str) else json.dumps(detail, sort_keys=True)
    text = (text or "").strip()
    if len(text) > 200:
        text = f"{text[:197]}..."
    if not text:
        return f"Central master rejected the request (HTTP {exc.code})."
    return f"Central master rejected the request (HTTP {exc.code}: {text})."


def _unreachable_detail(exc):
    reason = getattr(exc, "reason", None) or exc
    return f"Central master unreachable ({type(exc).__name__}: {reason})."


def _central_request(method, url, payload=None, timeout=CENTRAL_TIMEOUT_SECONDS, attempts=2):
    """Best-effort call against the central master.

    Returns ``(ok, status_code, data, error)`` and never raises, so a third
    party outage is reported instead of failing the platform request. The
    payload is never logged or echoed back: it carries a plaintext password.

    Transport failures are retried once. That is safe for the create call
    because the master enforces username/email/phone uniqueness per client, so
    a repeated attempt is rejected rather than duplicated.
    """
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    error = "Central master is unreachable."

    for attempt in range(attempts):
        headers = {"User-Agent": "Tixelise-Platform"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=timeout) as response:
                status_code = getattr(response, "status", 200)
                raw = response.read()
        except HTTPError as exc:
            return False, exc.code, None, _http_error_detail(exc)
        except (URLError, TimeoutError, OSError) as exc:
            error = _unreachable_detail(exc)
            if attempt + 1 < attempts:
                time.sleep(1)
                continue
            return False, None, None, error

        if not raw:
            return True, status_code, None, ""
        try:
            return True, status_code, json.loads(raw.decode("utf-8")), ""
        except ValueError:
            return True, status_code, None, ""

    return False, None, None, error


def _central_user_body(
    tenant_code,
    *,
    username,
    email,
    password,
    role="ADMIN",
    phone=None,
    first_name=None,
    last_name=None,
):
    """The documented create payload, built from inputs instead of a ``User``.

    Onboarding calls this before the local account exists, so nothing here can
    depend on a saved model.
    """
    return {
        "client_id": tenant_code,
        "first_name": first_name or username,
        "last_name": last_name or "-",
        "username": username,
        "password": password,
        "email": email,
        # Staff need their own number: the master enforces uniqueness per
        # client_id, so two accounts cannot share the tenant's phone.
        "phone_number": phone or "",
        "user_role": role,
        "status": "ACTIVE",
        **_PRODUCT_FLAGS,
    }


def _central_user_payload(
    tenant, user, password, role="ADMIN", phone=None, first_name=None, last_name=None
):
    """The same payload for an account that already exists locally."""
    return _central_user_body(
        tenant.code,
        username=user.username,
        email=user.email,
        password=password,
        role=role,
        phone=phone or tenant.phone,
        first_name=first_name or user.first_name,
        last_name=last_name or user.last_name,
    )


def _find_central_user(client_id, username):
    """Return ``(row_or_None, checked)``.

    ``checked`` is False when the master list could not be read, so the caller
    can refuse to POST rather than risk creating a duplicate account.
    """
    ok, _status_code, rows, _error = _central_request("GET", USER_MASTER_URL)
    if not ok or not isinstance(rows, list):
        return None, False
    wanted_client = (client_id or "").strip().upper()
    wanted_username = (username or "").strip().lower()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if (
            (row.get("client_id") or "").strip().upper() == wanted_client
            and (row.get("username") or "").strip().lower() == wanted_username
        ):
            return row, True
    return None, True


def _link_central_user(membership, row, status_word, detail):
    central_id = str(row.get("id") or "")
    if central_id:
        membership.central_user_id = central_id
        membership.save(update_fields=["central_user_id", "updated_at"])
    return {"status": status_word, "central_user_id": central_id, "detail": detail}


def _read_back_central_user(tenant, membership):
    """The create response is only ``{"message": ...}``, so the id is read back."""
    existing, checked = _find_central_user(tenant.code, membership.user.username)
    if checked and existing:
        return _link_central_user(
            membership, existing, "registered", "Registered in the central user master."
        )
    return {
        "status": "registered",
        "central_user_id": "",
        "detail": "Registered, but the account was not listed afterwards, so no id was stored.",
    }


def _register_central_user(
    tenant,
    membership,
    password,
    check_existing=False,
    role="ADMIN",
    phone=None,
    first_name=None,
    last_name=None,
):
    """Register an account in the central user master (best effort).

    Never raises: the local rows already exist, so the outcome is reported back
    to the UI and can be retried.

    ``role`` is ``ADMIN`` for a tenant admin and ``USER`` for POS staff; those are
    the only two values the master documents.
    ``check_existing`` belongs to the retry path. A freshly created account
    cannot already exist (usernames are unique platform-wide here), so the
    create paths skip the lookup and save a round trip to a slow host.
    """
    user = membership.user

    if membership.central_user_id:
        return {
            "status": "skipped",
            "central_user_id": membership.central_user_id,
            "detail": "This account is already linked to the central master.",
        }

    if check_existing:
        existing, checked = _find_central_user(tenant.code, user.username)
        if not checked:
            return {
                "status": "failed",
                "central_user_id": "",
                "detail": "Could not read the central user list, so no account was created.",
            }
        if existing:
            return _link_central_user(
                membership,
                existing,
                "skipped",
                "Central user already existed; link recovered.",
            )

    if not password:
        return {
            "status": "failed",
            "central_user_id": "",
            "detail": "A password is required to create the central user.",
        }

    ok, _status_code, _data, error = _central_request(
        "POST",
        USER_MASTER_URL,
        _central_user_payload(
            tenant,
            user,
            password,
            role=role,
            phone=phone,
            first_name=first_name,
            last_name=last_name,
        ),
    )
    if ok:
        return _read_back_central_user(tenant, membership)

    # The write may have landed before the response was lost. Never report a
    # failure without checking: that is exactly what made a real success look
    # like an outage.
    existing, checked = _find_central_user(tenant.code, user.username)
    if checked and existing:
        return _link_central_user(
            membership,
            existing,
            "registered",
            "Registration confirmed after a failed response.",
        )
    return {"status": "failed", "central_user_id": "", "detail": error}


def create_central_user(
    tenant_code,
    *,
    username,
    email,
    password,
    role="ADMIN",
    phone=None,
    first_name=None,
    last_name=None,
    check_existing=True,
    attempts=1,
):
    """Create an account in the central user master, or raise.

    Runs before any local row exists, so the caller can make central success a
    precondition for onboarding. Returns ``{status, central_user_id, detail}``
    on success.

    ``check_existing`` (default on) makes a retried onboarding idempotent: an
    account that already exists for this client is adopted instead of posted
    again, so a crash between the POST and the local commit is recoverable.
    ``attempts`` defaults to one: the strict path must not add 40s of latency.

    Raises ``CentralRegistrationRejected`` when the master answers 4xx and
    ``CentralMasterUnavailable`` when it cannot be reached *or* when the new id
    cannot be read back — an account Tixelise cannot link is not a success.
    """
    tenant_code = (tenant_code or "").strip()
    username = (username or "").strip()
    if not tenant_code or not username:
        raise CentralRegistrationRejected(
            "A tenant code and username are required to create the central user."
        )
    if not password:
        raise CentralRegistrationRejected(
            "A password is required to create the central user."
        )

    if check_existing:
        existing, checked = _find_central_user(tenant_code, username)
        if not checked:
            # Posting blind here could create a second account for this admin.
            raise CentralMasterUnavailable(
                "Could not read the central user list, so no account was created."
            )
        if existing:
            central_id = str(existing.get("id") or "")
            if not central_id:
                raise CentralMasterUnavailable(
                    "The central master listed this username without an id."
                )
            return {
                "status": "skipped",
                "central_user_id": central_id,
                "detail": "Central user already existed; link adopted.",
            }

    body = _central_user_body(
        tenant_code,
        username=username,
        email=email,
        password=password,
        role=role,
        phone=phone,
        first_name=first_name,
        last_name=last_name,
    )
    ok, status_code, _data, error = _central_request(
        "POST", USER_MASTER_URL, body, attempts=attempts
    )

    if not ok:
        # The write may have landed before the response was lost: never report
        # a failure without looking, or a retry would be rejected as a
        # duplicate of an account that does exist.
        existing, checked = _find_central_user(tenant_code, username)
        if checked and existing and str(existing.get("id") or ""):
            return {
                "status": "registered",
                "central_user_id": str(existing["id"]),
                "detail": "Registration confirmed after a failed response.",
            }
        if status_code is not None and 400 <= status_code < 500:
            raise CentralRegistrationRejected(error)
        raise CentralMasterUnavailable(error)

    existing, checked = _find_central_user(tenant_code, username)
    if checked and existing and str(existing.get("id") or ""):
        return {
            "status": "registered",
            "central_user_id": str(existing["id"]),
            "detail": "Registered in the central user master.",
        }
    raise CentralMasterUnavailable(
        "The central master accepted the account but its id could not be read "
        "back, so it was not linked to a local record."
    )


def _registration_failure(detail):
    """Map a currency-master failure onto the strict-onboarding contract."""
    if "unreachable" in (detail or "").lower():
        return CentralMasterUnavailable(detail)
    return CentralRegistrationRejected(detail)


def _linked_central_user_ids(tenant):
    return [
        membership.central_user_id
        for membership in tenant.memberships.all()
        if membership.central_user_id
    ]


def _delete_central_users(tenant_code, central_ids):
    """Remove the tenant's central accounts. Never blocks the local delete."""
    results = []
    expected_client = (tenant_code or "").strip().upper()

    for central_id in central_ids:
        url = f"{USER_MASTER_URL}{central_id}/"
        ok, status_code, record, error = _central_request("GET", url)

        if status_code == 404:
            results.append(
                {"central_user_id": central_id, "status": "gone", "detail": "Already removed."}
            )
            continue
        if not ok or not isinstance(record, dict):
            results.append(
                {
                    "central_user_id": central_id,
                    "status": "failed",
                    "detail": error or "Central record could not be read.",
                }
            )
            continue

        # Never delete by a stored id alone: a stale or mistyped id would take
        # out another client's account.
        belongs = (record.get("client_id") or "").strip().upper() == expected_client
        if not belongs or not record.get("tixelise"):
            results.append(
                {
                    "central_user_id": central_id,
                    "status": "skipped",
                    "detail": "Record does not belong to this tenant.",
                }
            )
            continue

        deleted, delete_status, _data, delete_error = _central_request("DELETE", url)
        if deleted or delete_status == 404:
            results.append({"central_user_id": central_id, "status": "deleted", "detail": ""})
        else:
            results.append(
                {
                    "central_user_id": central_id,
                    "status": "failed",
                    "detail": delete_error,
                }
            )
    return results


def update_central_user(
    tenant_code, central_id, *, first_name=None, last_name=None, email=None, phone=None
):
    """Edit the linked account in the central user master, or raise.

    Only the fields that actually changed are sent: the master documents PATCH
    as a partial edit, so the product flags and any omitted value keep their
    current state. Nothing about the local rows is decided here — the caller
    runs this before committing, so a master failure leaves them untouched.

    Raises ``CentralRegistrationRejected``'s sibling ``CentralUpdateRejected``
    when the master answers 4xx and ``CentralMasterUnavailable`` when it cannot
    be read or written at all. A record that no longer exists, or that belongs
    to another client, is reported as ``gone``/``skipped`` instead of raising,
    so removing it centrally must never block an otherwise valid local edit.
    """
    central_id = str(central_id or "").strip()
    if not central_id:
        return {
            "status": "skipped",
            "central_user_id": "",
            "detail": "No central account is linked.",
        }

    body = {}
    if first_name is not None:
        body["first_name"] = first_name
    if last_name is not None:
        body["last_name"] = last_name
    if email is not None:
        body["email"] = email
    if phone is not None:
        body["phone_number"] = phone
    if not body:
        return {
            "status": "skipped",
            "central_user_id": central_id,
            "detail": "Nothing to update.",
        }

    url = f"{USER_MASTER_URL}{central_id}/"
    ok, status_code, record, error = _central_request("GET", url)
    if status_code == 404:
        return {
            "status": "gone",
            "central_user_id": central_id,
            "detail": "The central account no longer exists.",
        }
    if not ok or not isinstance(record, dict):
        raise CentralMasterUnavailable(
            error or "The central account could not be read, so nothing was saved."
        )

    # Never write by a stored id alone: a stale or mistyped id would edit
    # another client's account.
    expected_client = (tenant_code or "").strip().upper()
    belongs = (record.get("client_id") or "").strip().upper() == expected_client
    if not belongs or not record.get("tixelise"):
        return {
            "status": "skipped",
            "central_user_id": central_id,
            "detail": "Record does not belong to this tenant.",
        }

    ok, status_code, _data, error = _central_request("PATCH", url, body, attempts=1)
    if not ok:
        if status_code is not None and 400 <= status_code < 500:
            raise CentralUpdateRejected(error)
        raise CentralMasterUnavailable(error)

    return {
        "status": "updated",
        "central_user_id": central_id,
        "detail": "Central account updated.",
    }


class TenantCurrencyOptionsView(APIView):
    """
    Currency/country list for the tenant form. The browser never calls the
    central master host directly, so there is no cross-origin dependency.
    """

    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        options, source = _fetch_currency_options()
        return Response({"source": source, "results": options})


class TenantLookupView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        code = (request.query_params.get("code") or "").strip().upper()
        if not code:
            return Response({"found": False})

        try:
            req = Request(
                "https://activate.imcbs.com/mobileapp/api/project/tixelise/",
                headers={"User-Agent": "Tixelise-Platform"},
            )
            with urlopen(req, timeout=5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (URLError, HTTPError, TimeoutError, ValueError, OSError):
            return Response({"found": False, "error": "lookup_failed"})

        customers = payload.get("customers") or []
        for customer in customers:
            client_id = (customer.get("client_id") or "").strip().upper()
            if client_id == code:
                if (customer.get("status") or "").strip().lower() != "active":
                    return Response({"found": False, "reason": "inactive"})
                return Response(
                    {
                        "found": True,
                        "name": customer.get("customer_name") or "",
                        "client_id": customer.get("client_id") or code,
                        "license_key": customer.get("license_key") or "",
                        "status": customer.get("status") or "",
                    }
                )
        return Response({"found": False})


class TenantListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    queryset = Tenant.objects.all().order_by("code").prefetch_related("memberships")
    serializer_class = TenantSerializer

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TenantCreateSerializer
        return TenantSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Read these before save(): the serializer pops them off validated_data.
        admin_username = serializer.validated_data.get("admin_username")
        admin_password = serializer.validated_data.get("admin_password")
        tenant_code = (serializer.validated_data.get("code") or "").strip()
        currency_code = serializer.validated_data.get("currency") or ""

        # Fail-closed: nothing is written locally unless the central master
        # succeeds. The calls run before the transaction on purpose — a 20s
        # third-party timeout must never hold the database write lock.
        if getattr(settings, "CENTRAL_CURRENCY_SYNC_ENABLED", True):
            registration = _register_tenant_currency(tenant_code, currency_code)
            if registration["status"] == "failed":
                raise _registration_failure(registration["detail"])
        else:
            registration = {
                "status": "skipped",
                "detail": "Central currency sync is disabled.",
            }

        if getattr(settings, "CENTRAL_USER_SYNC_ENABLED", True):
            central_user = create_central_user(
                tenant_code,
                username=admin_username,
                email=serializer.validated_data.get("admin_email") or "",
                password=admin_password,
                role="ADMIN",
                phone=serializer.validated_data.get("phone") or "",
                first_name=serializer.validated_data.get("admin_first_name") or "",
                last_name=serializer.validated_data.get("admin_last_name") or "",
            )
        else:
            central_user = {
                "status": "skipped",
                "central_user_id": "",
                "detail": "Central user sync is disabled.",
            }

        try:
            tenant = serializer.save(central_user_id=central_user["central_user_id"])
            # The local rows are only written now, with the link already set, so
            # a tenant can never be created without its central account.
            record_audit(
                actor=request.user,
                tenant=None,
                action="platform.tenant.created",
                target_type="tenant",
                target_id=tenant.id,
                metadata={
                    "code": tenant.code,
                    "name": tenant.name,
                    "admin": admin_username,
                },
            )
        except Exception:
            # The master already holds an account this request created, so drop
            # it: a failed local commit must not leave a half-onboarded tenant.
            # An adopted row (`skipped`) predates this request and is left alone.
            if central_user["status"] == "registered" and central_user["central_user_id"]:
                _delete_central_users(tenant_code, [central_user["central_user_id"]])
            raise

        record_audit(
            actor=request.user,
            tenant=None,
            action="platform.tenant.currency_registered",
            target_type="tenant",
            target_id=tenant.id,
            metadata={
                "code": tenant.code,
                "currency": tenant.currency,
                "status": registration["status"],
                "detail": registration["detail"],
            },
        )
        record_audit(
            actor=request.user,
            tenant=None,
            action="platform.tenant.central_user_registered",
            target_type="tenant",
            target_id=tenant.id,
            metadata={
                "code": tenant.code,
                "username": admin_username,
                "status": central_user["status"],
                "central_user_id": central_user["central_user_id"],
                "detail": central_user["detail"],
            },
        )

        body = dict(serializer.data)
        body["currency_registration"] = registration
        body["central_user_registration"] = central_user
        return Response(
            body,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(serializer.data),
        )


class TenantDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = TenantSerializer

    def get_queryset(self):
        return Tenant.objects.prefetch_related("memberships")

    def perform_update(self, serializer):
        tenant = serializer.save()
        record_audit(
            actor=self.request.user,
            tenant=None,
            action="platform.tenant.updated",
            target_type="tenant",
            target_id=tenant.id,
            metadata={"code": tenant.code},
        )

    def perform_destroy(self, instance):
        tenant_id = instance.id
        tenant_code = instance.code
        tenant_name = instance.name
        # Read the links first: delete_tenant purges the memberships.
        central_ids = _linked_central_user_ids(instance)
        deleted = delete_tenant(instance)
        # Deliberately after the local delete and never fatal: blocking here
        # would leave a live tenant with a dead central account, which is worse
        # than an orphaned record the audit log can point at.
        central = (
            _delete_central_users(tenant_code, central_ids)
            if getattr(settings, "CENTRAL_USER_SYNC_ENABLED", True)
            else []
        )
        record_audit(
            actor=self.request.user,
            tenant=None,
            action="platform.tenant.deleted",
            target_type="tenant",
            target_id=tenant_id,
            metadata={
                "code": tenant_code,
                "name": tenant_name,
                "deleted": deleted,
                "central_users": central,
            },
        )


class TenantStatusActionView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    allowed_transition = None
    audit_action = None

    def post(self, request, pk):
        try:
            tenant = Tenant.objects.get(pk=pk)
        except Tenant.DoesNotExist:
            raise NotFound("Tenant not found.")

        if tenant.status == self.allowed_transition:
            raise TixeliseAPIException(
                detail=f"Tenant is already {self.allowed_transition}.",
                code="ALREADY_IN_STATE",
            )

        tenant.status = self.allowed_transition
        tenant.save(update_fields=["status", "updated_at"])
        record_audit(
            actor=request.user,
            tenant=None,
            action=self.audit_action,
            target_type="tenant",
            target_id=tenant.id,
            metadata={"code": tenant.code, "status": tenant.status},
        )
        return Response(
            {"id": tenant.id, "code": tenant.code, "status": tenant.status},
            status=status.HTTP_200_OK,
        )


class TenantActivateView(TenantStatusActionView):
    allowed_transition = Tenant.Status.ACTIVE
    audit_action = "platform.tenant.activated"


class TenantSuspendView(TenantStatusActionView):
    allowed_transition = Tenant.Status.SUSPENDED
    audit_action = "platform.tenant.suspended"


class TenantDeactivateView(TenantStatusActionView):
    allowed_transition = Tenant.Status.INACTIVE
    audit_action = "platform.tenant.deactivated"


class TenantCentralSyncView(APIView):
    """
    Re-runs both central registrations for an existing tenant.

    Needed because the first attempt is best-effort: a transient outage would
    otherwise leave the tenant permanently unregistered, and the create form
    cannot be submitted twice (duplicate code).
    """

    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def post(self, request, pk):
        tenant = Tenant.objects.filter(pk=pk).first()
        if tenant is None:
            raise NotFound("Tenant not found.")

        membership = (
            tenant.memberships.select_related("user")
            .filter(role=TenantMembership.Role.TENANT_ADMIN)
            .first()
        )
        if membership is None:
            raise NotFound("Tenant admin not found.")

        if getattr(settings, "CENTRAL_CURRENCY_SYNC_ENABLED", True):
            currency = _register_tenant_currency(tenant.code, tenant.currency)
        else:
            currency = {
                "status": "skipped",
                "detail": "Central currency sync is disabled.",
            }

        if getattr(settings, "CENTRAL_USER_SYNC_ENABLED", True):
            central_user = _register_central_user(
                tenant,
                membership,
                (request.data.get("password") or "").strip(),
                check_existing=True,
            )
        else:
            central_user = {
                "status": "skipped",
                "central_user_id": "",
                "detail": "Central user sync is disabled.",
            }

        record_audit(
            actor=request.user,
            tenant=None,
            action="platform.tenant.central_sync",
            target_type="tenant",
            target_id=tenant.id,
            metadata={
                "code": tenant.code,
                "username": membership.user.username,
                "currency": currency["status"],
                "user": central_user["status"],
                "central_user_id": central_user["central_user_id"],
            },
        )
        return Response({"currency": currency, "user": central_user})

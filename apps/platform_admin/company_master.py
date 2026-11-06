"""Authenticated proxy for the central company master.

The central master has no authentication of its own, and a plain GET returns
every client's companies. Calling it from the browser would therefore let any
visitor read and write other tenants' records, so the calls live here instead:

* the JWT decides which ``client_id`` the caller owns; that value is injected
  into every request and never taken from the request body;
* reads are filtered to it, and writes to a row belonging to another client are
  reported as missing rather than forbidden;
* transport, timeout and retry behaviour are the ones already used for the
  central currency and user masters.

Nothing is stored locally - this is a pass-through, so there is no new table,
no migration and no copy to keep in step.
"""

import logging

from django.urls import path
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.exceptions import Conflict, NotFound, TixeliseAPIException, ValidationError
from apps.core.permissions import IsTenantAdmin

from .views import (
    CENTRAL_TIMEOUT_SECONDS,
    _central_request,
    _fetch_currency_options,
)

logger = logging.getLogger(__name__)

COMPANY_MASTER_URL = "https://centralmastermanagement.imcbs.com/api/company-master/"
# The activation service holds the client list this tenant was licensed from,
# including the licence key. Already consulted at login to reject expired
# licences, so this reuses an existing dependency rather than adding one.
CLIENT_LICENSE_URL = "https://activate.imcbs.com/mobileapp/api/project/tixelise/"
# Read-only lookup on a third-party host: short and single-attempt, matching
# the licence check in apps.accounts.serializers.
LOOKUP_TIMEOUT_SECONDS = 5

MAX_LENGTHS = {
    "company_name": 255,
    "license_key": 100,
    "gst_number": 20,
    "pan_number": 10,
    "email": 254,
    "phone_number": 20,
    "address_line_1": 255,
    "address_line_2": 255,
    "city": 100,
    "district": 100,
    "state": 100,
    "country": 100,
}
REQUIRED_FIELDS = tuple(key for key in MAX_LENGTHS if key != "address_line_2")
PRODUCT_FLAGS = (
    "trellisco",
    "claudius",
    "melone",
    "tixelise",
    "trellisco_crm",
    "melone_stay",
    "trellisco_books",
)
STATUSES = ("ACTIVE", "INACTIVE")
# A company registered through Tixelise is a Tixelise company: when a caller
# expresses no product access at all, only Tixelise is enabled. Same convention
# as the central user master registration in .views.
_DEFAULT_PRODUCT_FLAGS = {field: field == "tixelise" for field in PRODUCT_FLAGS}
SEARCH_FIELDS = (
    "company_name",
    "city",
    "district",
    "state",
    "email",
    "phone_number",
    "gst_number",
    "pan_number",
    "license_key",
)


class CentralMasterUnavailable(TixeliseAPIException):
    status_code = 503
    default_code = "SERVICE_UNAVAILABLE"
    default_detail = "The central company master is unavailable."


def _raise_upstream(status_code, error):
    """Turn a central master failure into our standard error envelope."""
    if status_code == 404:
        raise NotFound("Company not found.")
    detail = (error or "").strip()
    if status_code == 400:
        raise ValidationError(detail or "The company master rejected this data.")
    raise CentralMasterUnavailable(detail or "The central company master is unavailable.")


def _client_id(request):
    code = str(getattr(request.tenant_obj, "code", "") or "").strip()
    if not code:
        raise NotFound("This organization has no client ID.")
    return code


def _clean_text(field, value, errors):
    text = "" if value is None else str(value).strip()
    if not text:
        if field in REQUIRED_FIELDS:
            errors[field] = "This field is required."
    elif len(text) > MAX_LENGTHS[field]:
        errors[field] = f"Ensure this value has no more than {MAX_LENGTHS[field]} characters."
    return text


def _validate(payload, *, partial):
    """``partial=True`` for PATCH: omitted fields keep their stored values."""
    if not isinstance(payload, dict):
        raise ValidationError("Expected a JSON object.")

    allowed = set(MAX_LENGTHS) | set(PRODUCT_FLAGS) | {"status"}
    unknown = sorted(
        str(key) for key in payload if key not in allowed and key not in ("id", "client_id")
    )
    errors = {}
    if unknown:
        errors["payload"] = f"Unknown fields: {', '.join(unknown)}."

    cleaned = {}
    for field in MAX_LENGTHS:
        if field in payload or not partial:
            cleaned[field] = _clean_text(field, payload.get(field), errors)

    for field in PRODUCT_FLAGS:
        if field in payload or not partial:
            value = payload.get(field, False)
            if not isinstance(value, bool):
                errors[field] = "Must be true or false."
            else:
                cleaned[field] = value

    # Only when no flag was mentioned: an explicit set of all-false values is
    # still rejected below by _require_any_product.
    if not partial and not any(field in payload for field in PRODUCT_FLAGS):
        cleaned.update(_DEFAULT_PRODUCT_FLAGS)

    status_value = str(payload.get("status") or "").strip().upper()
    if status_value:
        if status_value not in STATUSES:
            errors["status"] = "Status must be ACTIVE or INACTIVE."
        else:
            cleaned["status"] = status_value
    elif not partial:
        cleaned["status"] = "ACTIVE"

    if errors:
        raise ValidationError(errors)
    return cleaned


def _require_any_product(record):
    if not any(bool(record.get(field)) for field in PRODUCT_FLAGS):
        raise ValidationError({"products": "At least one product must be enabled."})


def _companies_for_client(client_id):
    """Every row the central master holds for this client ID."""
    ok, code, data, error = _central_request("GET", COMPANY_MASTER_URL)
    if not ok:
        _raise_upstream(code, error)

    rows = data if isinstance(data, list) else []
    wanted = client_id.upper()
    return [
        row
        for row in rows
        if isinstance(row, dict)
        and str(row.get("client_id") or "").strip().upper() == wanted
    ]


def _license_key_for_client(client_id):
    """Return ``(license_key, source)`` for this client from the activation list.

    Never raises. A company cannot be created without a licence key, but an
    outage here must not stop the page from loading: the caller falls back to a
    blank field the administrator can type, so the lookup stays a convenience.
    """
    ok, _code, data, error = _central_request(
        "GET", CLIENT_LICENSE_URL, timeout=LOOKUP_TIMEOUT_SECONDS, attempts=1
    )
    if not ok:
        logger.warning("Client licence lookup failed: %s", error)
        return "", "unavailable"

    customers = data.get("customers") if isinstance(data, dict) else None
    wanted = client_id.upper()
    for customer in customers or []:
        if not isinstance(customer, dict):
            continue
        if str(customer.get("client_id") or "").strip().upper() == wanted:
            # Only this client's own row is ever read out of the list.
            return str(customer.get("license_key") or "").strip(), "remote"
    return "", "unknown"


def _country_names():
    """Country names Tixelise supports, taken from the financial-year master.

    Reuses the cached options behind tenant onboarding, so the company form and
    the tenant's currency always agree on what a country is called. Never
    returns an empty list: that helper falls back to a built-in set when the
    remote host is unreachable.
    """
    options, _source = _fetch_currency_options()
    names = {str(item.get("country_name") or "").strip().upper() for item in options}
    return sorted(names - {""})


def _fetch_company(company_id, client_id):
    ok, code, data, error = _central_request(
        "GET", f"{COMPANY_MASTER_URL}{company_id}/", timeout=CENTRAL_TIMEOUT_SECONDS
    )
    if not ok:
        _raise_upstream(code, error)
    if not isinstance(data, dict):
        raise NotFound("Company not found.")
    if str(data.get("client_id") or "").strip().upper() != client_id.upper():
        # Another client's row: reported as missing so the existence of other
        # tenants' companies is not disclosed.
        raise NotFound("Company not found.")
    return data


class CompanyMasterView(APIView):
    """List this client's companies and create a new one."""

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        client_id = _client_id(request)
        mine = _companies_for_client(client_id)

        search = str(request.query_params.get("search") or "").strip().lower()
        if search:
            mine = [
                row
                for row in mine
                if search in " ".join(str(row.get(key) or "") for key in SEARCH_FIELDS).lower()
            ]

        # The create form needs a licence key. Rather than make the
        # administrator hunt for it, offer the one this client was licensed
        # with; it stays editable and is still validated on the way out.
        license_key, license_source = _license_key_for_client(client_id)
        return Response(
            {
                "client_id": client_id,
                "count": len(mine),
                "license_key": license_key,
                "license_source": license_source,
                "countries": _country_names(),
                "results": mine,
            }
        )

    def post(self, request):
        client_id = _client_id(request)
        # One company per tenant: Tixelise stores nothing about companies, so
        # the central master is the only place to look for an existing record.
        if _companies_for_client(client_id):
            raise Conflict(
                "This client ID already has a company in the central master. "
                "Edit the existing record instead of creating another."
            )

        record = _validate(request.data, partial=False)
        _require_any_product(record)

        ok, code, data, error = _central_request(
            "POST", COMPANY_MASTER_URL, {"client_id": client_id, **record}
        )
        if not ok:
            _raise_upstream(code, error)

        created = data if isinstance(data, dict) else {}
        record_audit(
            action="company_master.created",
            actor=request.user,
            tenant=request.tenant_obj,
            target_type="central.company",
            target_id=created.get("id", ""),
            metadata={"company_name": record["company_name"], "client_id": client_id},
        )
        return Response(created or {"company_name": record["company_name"]}, status=201)


class CompanyMasterItemView(APIView):
    """Read, edit or delete one company, scoped to the caller's client ID."""

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request, company_id):
        return Response(_fetch_company(company_id, _client_id(request)))

    def patch(self, request, company_id):
        client_id = _client_id(request)
        existing = _fetch_company(company_id, client_id)
        record = _validate(request.data, partial=True)

        merged = {**existing, **record}
        _require_any_product(merged)

        ok, code, data, error = _central_request(
            "PATCH", f"{COMPANY_MASTER_URL}{company_id}/", record
        )
        if not ok:
            _raise_upstream(code, error)

        record_audit(
            action="company_master.updated",
            actor=request.user,
            tenant=request.tenant_obj,
            target_type="central.company",
            target_id=company_id,
            metadata={"fields": sorted(record), "client_id": client_id},
        )
        return Response(data if isinstance(data, dict) and data else {**existing, **record})

    def put(self, request, company_id):
        client_id = _client_id(request)
        _fetch_company(company_id, client_id)
        record = _validate(request.data, partial=False)
        _require_any_product(record)

        ok, code, data, error = _central_request(
            "PUT", f"{COMPANY_MASTER_URL}{company_id}/", {"client_id": client_id, **record}
        )
        if not ok:
            _raise_upstream(code, error)

        record_audit(
            action="company_master.replaced",
            actor=request.user,
            tenant=request.tenant_obj,
            target_type="central.company",
            target_id=company_id,
            metadata={"company_name": record["company_name"], "client_id": client_id},
        )
        return Response(data if isinstance(data, dict) and data else record)

    def delete(self, request, company_id):
        client_id = _client_id(request)
        _fetch_company(company_id, client_id)

        ok, code, _, error = _central_request("DELETE", f"{COMPANY_MASTER_URL}{company_id}/")
        if not ok:
            _raise_upstream(code, error)

        record_audit(
            action="company_master.deleted",
            actor=request.user,
            tenant=request.tenant_obj,
            target_type="central.company",
            target_id=company_id,
            metadata={"client_id": client_id},
        )
        return Response(status=204)


urlpatterns = [
    path("", CompanyMasterView.as_view(), name="central-company-list"),
    path("<int:company_id>/", CompanyMasterItemView.as_view(), name="central-company-detail"),
]

"""Authenticated proxy for the central tax master.

Same reasoning as .company_master: the tax master has no authentication of its
own, and a plain GET returns every client's tax records, so the calls cannot be
made from the browser. They live here instead:

* the JWT decides which ``client_id`` the caller owns; that value is injected
  into every request and never taken from the request body;
* reads are filtered to it, and writes to a row belonging to another client are
  reported as missing rather than forbidden;
* transport, timeout and retry behaviour are the ones already used for the
  central currency, user and company masters.

Nothing is stored locally - this is a pass-through, so there is no new table, no
migration and no copy to keep in step. Nothing in Tixelise reads these records
either: no price, ticket or report depends on them.

One upstream quirk shapes the whole module. There is no PATCH: an update is a
``PUT`` to the *collection* URL carrying the complete record and its ``id`` in
the body. So an edit is assembled here - load the row, merge the change, send
the whole thing back - and the frontend only ever sees ordinary PATCH semantics.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.urls import path
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.exceptions import BadRequest, NotFound, TixeliseAPIException, ValidationError
from apps.core.permissions import IsTenantAdmin

from .views import _central_request

TAX_MASTER_BASE_URL = "https://centralmastermanagement.imcbs.com/api/tax-master/"

# The master takes any string here, but Tixelise only works in percentages.
# Every record this page writes is marked PERCENTAGE, and the value is never
# taken from the request, so nobody can create a row that the rest of the
# system would read as a different kind of charge.
CAL_METHOD = "PERCENTAGE"
KINDS = ("india", "other")
STATUSES = ("ACTIVE", "INACTIVE")

# Field rules per kind, from the tax master reference of 04 Nov 2026. India
# exposes the four GST components; every other country has one flat rate.
_TEXT_FIELDS = {
    "india": {"code": 20, "name": 100, "type": 50},
    "other": {"code": 20, "name": 100},
}
_REQUIRED_TEXT = ("code", "name")
_RATE_FIELDS = {
    "india": ("cgst", "sgst", "igst", "gst"),
    "other": ("tax",),
}
SEARCH_FIELDS = ("code", "name", "type")

# Rates are percentages, so 0-100 is the only range that means anything. Zero
# is allowed on purpose: a zero-rated or exempt supply is a real configuration,
# not a mistake.
_PERCENT_MAX = Decimal("100")
_CENT = Decimal("0.01")


class CentralTaxMasterUnavailable(TixeliseAPIException):
    status_code = 503
    default_code = "SERVICE_UNAVAILABLE"
    default_detail = "The central tax master is unavailable."


def _raise_upstream(status_code, error):
    """Turn a central master failure into our standard error envelope."""
    if status_code == 404:
        raise NotFound("Tax record not found.")
    detail = (error or "").strip()
    if status_code == 400:
        raise ValidationError(detail or "The tax master rejected this data.")
    raise CentralTaxMasterUnavailable(detail or "The central tax master is unavailable.")


def _client_id(request):
    code = str(getattr(request.tenant_obj, "code", "") or "").strip()
    if not code:
        raise NotFound("This organization has no client ID.")
    return code


def _require_kind(kind):
    """Only the two path segments the master actually serves."""
    value = str(kind or "").strip().lower()
    if value not in KINDS:
        raise BadRequest(f"Tax type must be one of: {', '.join(KINDS)}.")
    return value


def _collection_url(kind):
    return f"{TAX_MASTER_BASE_URL}{kind}/"


def _suggested_kind(tenant):
    """Which tab to open first, decided locally from the tenant's currency.

    A convenience for the page, not a restriction: both lists belong to this
    same client ID, so an administrator can switch tabs freely.
    """
    currency = str(getattr(tenant, "currency", "") or "").strip().upper()
    return "india" if currency == "INR" else "other"


def _clean_text(field, value, maximum, errors):
    text = "" if value is None else str(value).strip()
    if not text:
        if field in _REQUIRED_TEXT:
            errors[field] = "This field is required."
    elif len(text) > maximum:
        errors[field] = f"Ensure this value has no more than {maximum} characters."
    return text


def _clean_rate(field, value, errors):
    """Normalise one percentage to the 2-dp string the master both takes and gives."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "0.00"
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        errors[field] = "Enter a number."
        return "0.00"
    if not number.is_finite():
        errors[field] = "Enter a number."
        return "0.00"
    if number < 0 or number > _PERCENT_MAX:
        errors[field] = "Enter a percentage between 0 and 100."
        return "0.00"
    return str(number.quantize(_CENT, rounding=ROUND_HALF_UP))


def _validate(kind, payload, *, partial):
    """``partial=True`` for PATCH: omitted fields keep their stored values."""
    if not isinstance(payload, dict):
        raise ValidationError("Expected a JSON object.")

    text_fields = _TEXT_FIELDS[kind]
    rate_fields = _RATE_FIELDS[kind]
    allowed = set(text_fields) | set(rate_fields) | {"status"}
    unknown = sorted(
        str(key)
        for key in payload
        if key not in allowed and key not in ("id", "client_id", "cal_method")
    )
    errors = {}
    if unknown:
        errors["payload"] = f"Unknown fields: {', '.join(unknown)}."
    if "cal_method" in payload:
        errors["cal_method"] = f"Calculation method is always {CAL_METHOD}; do not send it."

    cleaned = {}
    for field, maximum in text_fields.items():
        if field in payload or not partial:
            cleaned[field] = _clean_text(field, payload.get(field), maximum, errors)

    for field in rate_fields:
        if field in payload or not partial:
            cleaned[field] = _clean_rate(field, payload.get(field), errors)

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


def _project(kind, record, client_id):
    """The exact keys the master expects for this kind, and nothing else.

    Built from the merged record rather than the request, so an update sends a
    complete row as PUT requires, and so a field the master adds later cannot be
    echoed back to it unasked.
    """
    errors = {}
    payload = {
        "client_id": client_id,
        "cal_method": CAL_METHOD,
        "status": str(record.get("status") or "ACTIVE").strip().upper(),
    }
    for field, maximum in _TEXT_FIELDS[kind].items():
        payload[field] = _clean_text(field, record.get(field), maximum, errors)
    for field in _RATE_FIELDS[kind]:
        payload[field] = _clean_rate(field, record.get(field), errors)
    if errors:
        # Only reachable when a stored row holds something unusable; saying so is
        # better than quietly rewriting the value to zero.
        raise ValidationError(errors)
    return payload


def _taxes_for_client(kind, client_id):
    """Every row the central master holds for this client ID."""
    ok, code, data, error = _central_request("GET", _collection_url(kind))
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


def _fetch_tax(kind, tax_id, client_id):
    ok, code, data, error = _central_request("GET", f"{_collection_url(kind)}{tax_id}/")
    if not ok:
        _raise_upstream(code, error)
    if not isinstance(data, dict):
        raise NotFound("Tax record not found.")
    if str(data.get("client_id") or "").strip().upper() != client_id.upper():
        # Another client's row: reported as missing so the existence of other
        # tenants' records is not disclosed.
        raise NotFound("Tax record not found.")
    return data


class TaxMasterView(APIView):
    """List this client's tax records of one kind, and create a new one."""

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request, kind):
        kind = _require_kind(kind)
        client_id = _client_id(request)
        mine = _taxes_for_client(kind, client_id)

        search = str(request.query_params.get("search") or "").strip().lower()
        if search:
            mine = [
                row
                for row in mine
                if search in " ".join(str(row.get(key) or "") for key in SEARCH_FIELDS).lower()
            ]

        return Response(
            {
                "client_id": client_id,
                "kind": kind,
                "count": len(mine),
                "suggested_kind": _suggested_kind(request.tenant_obj),
                "cal_method": CAL_METHOD,
                "results": mine,
            }
        )

    def post(self, request, kind):
        kind = _require_kind(kind)
        client_id = _client_id(request)
        record = _validate(kind, request.data, partial=False)
        payload = _project(kind, record, client_id)

        ok, code, data, error = _central_request("POST", _collection_url(kind), payload)
        if not ok:
            _raise_upstream(code, error)

        created = data if isinstance(data, dict) else {}
        record_audit(
            action="tax_master.created",
            actor=request.user,
            tenant=request.tenant_obj,
            target_type="central.tax",
            target_id=created.get("id", ""),
            metadata={"kind": kind, "code": payload["code"], "client_id": client_id},
        )
        return Response(created or payload, status=201)


class TaxMasterItemView(APIView):
    """Read, edit or delete one tax record, scoped to the caller's client ID."""

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request, kind, tax_id):
        kind = _require_kind(kind)
        return Response(_fetch_tax(kind, tax_id, _client_id(request)))

    def patch(self, request, kind, tax_id):
        kind = _require_kind(kind)
        client_id = _client_id(request)
        existing = _fetch_tax(kind, tax_id, client_id)
        changed = _validate(kind, request.data, partial=True)

        # The master has no partial update, so the stored row is the base and the
        # submitted fields are laid over it before the whole thing goes back.
        merged = {**existing, **changed}
        payload = _project(kind, merged, client_id)
        payload["id"] = tax_id

        ok, code, data, error = _central_request("PUT", _collection_url(kind), payload)
        if not ok:
            _raise_upstream(code, error)

        record_audit(
            action="tax_master.updated",
            actor=request.user,
            tenant=request.tenant_obj,
            target_type="central.tax",
            target_id=tax_id,
            metadata={"kind": kind, "fields": sorted(changed), "client_id": client_id},
        )
        return Response(data if isinstance(data, dict) and data else payload)

    def delete(self, request, kind, tax_id):
        kind = _require_kind(kind)
        client_id = _client_id(request)
        _fetch_tax(kind, tax_id, client_id)

        ok, code, _, error = _central_request("DELETE", f"{_collection_url(kind)}{tax_id}/")
        if not ok:
            _raise_upstream(code, error)

        record_audit(
            action="tax_master.deleted",
            actor=request.user,
            tenant=request.tenant_obj,
            target_type="central.tax",
            target_id=tax_id,
            metadata={"kind": kind, "client_id": client_id},
        )
        return Response(status=204)


urlpatterns = [
    path("<str:kind>/", TaxMasterView.as_view(), name="central-tax-list"),
    path("<str:kind>/<int:tax_id>/", TaxMasterItemView.as_view(), name="central-tax-detail"),
]

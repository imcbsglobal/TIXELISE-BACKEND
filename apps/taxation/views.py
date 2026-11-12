"""Read and change the tenant's ticket-tax setting.

The tax *records* stay in the central master (see ``apps.platform_admin.tax_master``
and its existing ``/api/v1/admin/tax-master/{kind}/`` proxy). This module only
stores which of those records applies to ticket sales, plus a frozen copy of its
rate, so that a sale never depends on a third-party host.

Selecting a record reads it back from the master through that same proxy: the
``client_id`` comes from the JWT exactly as it does there, so a tenant can only
ever select one of its own records.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.exceptions import BadRequest, ValidationError
from apps.core.permissions import IsTenantAdmin
from apps.platform_admin.tax_master import KINDS, _client_id, _taxes_for_client

from .models import TaxSetting
from .services import rate_from_master_row

# A copy older than this is flagged so the UI can suggest "Refresh from master".
STALE_AFTER_DAYS = 7

_EDITABLE = {"enabled", "kind", "tax_master_id", "prices_include_tax"}


def _as_bool(field, value, errors):
    if isinstance(value, bool):
        return value
    errors[field] = "Must be true or false."
    return None


def _setting_for(tenant):
    return TaxSetting.objects.filter(tenant=tenant).first()


def _snapshot(kind, row):
    """The stored copy of one central tax record."""
    return {
        "kind": kind,
        "tax_master_id": str(row.get("id") or ""),
        "code": str(row.get("code") or "").strip()[:20],
        "name": str(row.get("name") or "").strip()[:100],
        "rate": rate_from_master_row(kind, row),
        "cgst": rate_from_master_row("india", {"gst": row.get("cgst")})
        if kind == TaxSetting.Kind.INDIA
        else None,
        "sgst": rate_from_master_row("india", {"gst": row.get("sgst")})
        if kind == TaxSetting.Kind.INDIA
        else None,
        "igst": rate_from_master_row("india", {"gst": row.get("igst")})
        if kind == TaxSetting.Kind.INDIA
        else None,
        "synced_at": timezone.now(),
    }


def _serialize(setting):
    if setting is None:
        return {
            "configured": False,
            "enabled": False,
            "kind": TaxSetting.Kind.INDIA,
            "tax_master_id": "",
            "code": "",
            "name": "",
            "rate": "0.00",
            "cgst": None,
            "sgst": None,
            "igst": None,
            "prices_include_tax": False,
            "synced_at": None,
            "stale": False,
            "stale_after_days": STALE_AFTER_DAYS,
        }

    def money(value):
        return None if value is None else str(value.quantize(Decimal("0.01")))

    stale = setting.synced_at is None or (
        timezone.now() - setting.synced_at
    ) > timedelta(days=STALE_AFTER_DAYS)
    return {
        "configured": True,
        "enabled": setting.enabled,
        "kind": setting.kind,
        "tax_master_id": setting.tax_master_id,
        "code": setting.code,
        "name": setting.name,
        "rate": money(setting.rate),
        "cgst": money(setting.cgst),
        "sgst": money(setting.sgst),
        "igst": money(setting.igst),
        "prices_include_tax": setting.prices_include_tax,
        "synced_at": setting.synced_at.isoformat() if setting.synced_at else None,
        "stale": stale,
        "stale_after_days": STALE_AFTER_DAYS,
    }


def _find_record(kind, tax_master_id, client_id):
    """This client's record with that id, read live from the central master."""
    for row in _taxes_for_client(kind, client_id):
        if str(row.get("id")) == str(tax_master_id):
            return row
    return None


class TaxSettingView(APIView):
    """Read the current setting, or enable/disable and pick the tax record."""

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        return Response(_serialize(_setting_for(request.tenant_obj)))

    def patch(self, request):
        tenant = request.tenant_obj
        data = request.data or {}
        if not isinstance(data, dict):
            raise ValidationError("Body must be a JSON object.")

        unknown = sorted(set(data) - _EDITABLE)
        if unknown:
            raise ValidationError(f"Unknown fields: {', '.join(unknown)}")

        errors = {}
        enabled = (
            _as_bool("enabled", data["enabled"], errors)
            if "enabled" in data
            else None
        )
        inclusive = (
            _as_bool("prices_include_tax", data["prices_include_tax"], errors)
            if "prices_include_tax" in data
            else None
        )
        if errors:
            raise ValidationError(errors)

        setting = _setting_for(tenant)
        selecting = "tax_master_id" in data or "kind" in data

        if selecting:
            kind = str(data.get("kind") or (setting.kind if setting else "")).strip().lower()
            if kind not in KINDS:
                raise BadRequest(f"Tax type must be one of: {', '.join(KINDS)}.")
            tax_master_id = str(data.get("tax_master_id") or "").strip()
            if not tax_master_id:
                raise ValidationError({"tax_master_id": "This field is required."})

            record = _find_record(kind, tax_master_id, _client_id(request))
            if record is None:
                raise ValidationError(
                    {"tax_master_id": "No tax record with that id belongs to this client."}
                )
            snapshot = _snapshot(kind, record)
        else:
            snapshot = {}

        # A tenant with no row yet is the common case: selecting a record must
        # work before anything is stored, so never assume `setting` exists.
        if enabled is not None:
            final_enabled = enabled
        else:
            final_enabled = bool(setting.enabled) if setting is not None else False
        if final_enabled:
            # Enabling without a selection is only allowed when a rate is
            # already stored; the master is not called again just for a toggle.
            known_rate = snapshot.get("rate", setting.rate if setting else Decimal("0.00"))
            if known_rate is None or known_rate <= Decimal("0.00"):
                raise ValidationError(
                    {
                        "tax_master_id": "Select a tax record before enabling tax "
                        "on ticket sales."
                    }
                )

        if setting is None:
            setting = TaxSetting(tenant=tenant)
        for field, value in snapshot.items():
            setattr(setting, field, value)
        if enabled is not None:
            setting.enabled = enabled
        if inclusive is not None:
            setting.prices_include_tax = inclusive
        setting.save()

        record_audit(
            actor=request.user,
            tenant=tenant,
            action="tax_setting.updated",
            target_type="tax_setting",
            target_id=setting.id,
            metadata={
                "enabled": setting.enabled,
                "code": setting.code,
                "rate": str(setting.rate),
                "prices_include_tax": setting.prices_include_tax,
                "selection_changed": bool(snapshot),
            },
        )
        return Response(_serialize(setting))


class TaxSettingRefreshView(APIView):
    """Re-read the chosen record from the central master.

    Never raises because a record disappeared: the last snapshot stays in place
    and the response says so, so sales keep working and the UI can warn. An
    unreachable master still returns 503 and writes nothing.
    """

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def post(self, request):
        tenant = request.tenant_obj
        setting = _setting_for(tenant)
        if setting is None or not setting.tax_master_id:
            raise ValidationError({"tax_master_id": "No tax record is selected yet."})

        record = _find_record(setting.kind, setting.tax_master_id, _client_id(request))
        if record is None:
            record_audit(
                actor=request.user,
                tenant=tenant,
                action="tax_setting.refresh_missing",
                target_type="tax_setting",
                target_id=setting.id,
                metadata={"code": setting.code, "kind": setting.kind},
            )
            payload = _serialize(setting)
            payload["found"] = False
            payload["warning"] = (
                f"{setting.code or 'The selected tax record'} no longer exists in the "
                "central tax master. Ticket sales keep using the last known rate "
                f"({setting.rate}%). Select another record to change it."
            )
            return Response(payload)

        for field, value in _snapshot(setting.kind, record).items():
            setattr(setting, field, value)
        setting.save()

        record_audit(
            actor=request.user,
            tenant=tenant,
            action="tax_setting.synced",
            target_type="tax_setting",
            target_id=setting.id,
            metadata={"code": setting.code, "rate": str(setting.rate)},
        )
        payload = _serialize(setting)
        payload["found"] = True
        return Response(payload)

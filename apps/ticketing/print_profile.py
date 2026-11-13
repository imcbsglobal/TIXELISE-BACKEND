"""Organization name (top) and thanks text (bottom) for printed tickets.

Both strings live in the existing `TicketTemplate.config` whitelist
(`header` / `footer`) inside one reserved row named "POS Print" — so this
needs no schema change, no migration, and no edit to any existing endpoint.
"""
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.catalog.models import TicketTemplate
from apps.core.exceptions import Forbidden, NotFound
from apps.core.permissions import IsPOSSStaff, IsTenantAdmin

from .models import Ticket

PRINT_TEMPLATE_NAME = "POS Print"
HEADER_MAX = 80
FOOTER_MAX = 200


def _print_template(tenant):
    return (
        TicketTemplate.objects.filter(tenant=tenant, name=PRINT_TEMPLATE_NAME)
        .order_by("id")
        .first()
    )


def _stored_config(tenant):
    template = _print_template(tenant)
    return template, dict(template.config or {}) if template else {}


def print_profile(tenant):
    """(header, footer, customized) with safe defaults when unset."""
    _, config = _stored_config(tenant)
    header = str(config.get("header") or "").strip()
    footer = str(config.get("footer") or "").strip()
    return {
        "header": header or tenant.name,
        "footer": footer,
        "customized": bool(header or footer),
    }


class TicketPrintProfileView(APIView):
    """Read / update the two printable strings. `tenant_admin` only."""

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        return Response(print_profile(request.tenant_obj))

    def put(self, request):
        return self._save(request)

    def patch(self, request):
        return self._save(request)

    def _save(self, request):
        tenant = request.tenant_obj
        data = request.data or {}
        if not isinstance(data, dict):
            raise ValidationError("Body must be a JSON object.")

        unknown = set(data) - {"header", "footer"}
        if unknown:
            raise ValidationError(f"Unknown fields: {', '.join(sorted(unknown))}")

        template, config = _stored_config(tenant)
        for field, limit in (("header", HEADER_MAX), ("footer", FOOTER_MAX)):
            if field not in data:
                continue
            value = data[field]
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise ValidationError(f"{field} must be a string.")
            value = value.strip()
            if len(value) > limit:
                raise ValidationError(f"{field} must be at most {limit} characters.")
            config[field] = value

        if template is None:
            template = TicketTemplate.objects.create(
                tenant=tenant, name=PRINT_TEMPLATE_NAME, config=config
            )
        else:
            template.config = config
            template.save(update_fields=["config", "updated_at"])

        record_audit(
            actor=request.user,
            tenant=tenant,
            action="ticket_print.updated",
            target_type="ticket_template",
            target_id=template.id,
            metadata={
                "header": config.get("header", ""),
                "footer": config.get("footer", ""),
            },
        )
        return Response(print_profile(tenant))


class POSTicketPrintProfileView(TicketPrintProfileView):
    """Read / update the two printable strings. `pos_staff` only.

    Same storage and validation as the admin endpoint, exposed under `/pos/`
    so a POS client never has to call `/admin/`.

    Security tradeoff: the profile is tenant-wide, so any POS staff member
    editing it re-brands **every** printed ticket for the whole tenant. Access
    is still bounded by an active tenant membership, every save is audited as
    `ticket_print.updated` with the actor, and a `tenant_admin` can overwrite
    the same strings at any time via `/api/v1/admin/ticket-print/`.
    """

    permission_classes = [IsAuthenticated, IsPOSSStaff]


class TicketPrintView(APIView):
    """Print payload for one ticket.

    Same access rule as the existing reprint endpoint: a `tenant_admin` may
    print any ticket in the tenant, a `pos_staff` only their own.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from apps.core.context import get_current_role

        try:
            ticket = Ticket.objects.select_related(
                "event", "staff", "category", "sale", "tenant"
            ).get(pk=pk)
        except Ticket.DoesNotExist:
            raise NotFound("Ticket not found.")

        role = get_current_role()
        if role == "pos_staff":
            if ticket.staff.user_id != request.user.id:
                raise Forbidden("You may only print your own tickets.")
        elif role != "tenant_admin":
            raise Forbidden()

        tz = ZoneInfo(ticket.tenant.timezone or "UTC")
        local = timezone.localtime(ticket.issued_at, tz)

        # A sale holds at most one item per category, so a ticket's money is
        # unambiguous. Read from the sale line's own snapshot, never the live
        # price or tax setting: a reprint must match the original ticket.
        item = ticket.sale.items.filter(category_id=ticket.category_id).first()
        price_fields = {
            "currency": ticket.sale.currency,
            "unit_price": str(item.unit_price_snapshot) if item else None,
            "quantity": item.quantity if item else None,
            "line_total": str(item.line_total) if item else None,
            "tax_rate": str(item.tax_rate_snapshot) if item else "0.00",
            "tax_code": item.tax_code if item else "",
            "tax_name": item.tax_name if item else "",
            "tax_amount": str(item.tax_amount) if item else "0.00",
            "hsn_code": item.hsn_code if item else "",
            "total": str(item.line_total + item.tax_amount) if item else None,
        }

        return Response(
            {
                "ticket": {
                    "id": str(ticket.id),
                    "ticket_code": ticket.ticket_code,
                    "sequence_number": ticket.sequence_number,
                    "status": ticket.status,
                    "issued_at": ticket.issued_at.isoformat(),
                    "issued_at_local": local.strftime("%d-%m-%Y %I:%M %p"),
                    "event": {
                        "code": ticket.event.code,
                        "name": ticket.event.name,
                        "venue": ticket.event.venue,
                        "start_at": ticket.event.start_at.isoformat(),
                    },
                    "category": ticket.category.name,
                    "staff_code": ticket.staff.staff_code,
                    "sale_reference": ticket.sale.sale_reference,
                    **price_fields,
                },
                "print": print_profile(ticket.tenant),
            }
        )

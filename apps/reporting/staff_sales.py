"""Standalone per-sale detail listing: every sale, one by one, with a date filter.

Deliberately self-contained — it has its own route and shares no view or
serializer with the aggregate summary endpoint or the existing reports.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.context import get_current_role
from apps.core.exceptions import Forbidden
from apps.core.permissions import IsTenantAdminOrPOSSStaff
from apps.sales.models import Sale
from apps.staff.models import StaffProfile
from apps.ticketing.models import Ticket

_DATE_FORMAT = "%Y-%m-%d"
DEFAULT_LIMIT = 500
MAX_LIMIT = 2000


def _parse_day(raw):
    return datetime.strptime(raw, _DATE_FORMAT).date()


def _money(value):
    return str((value or Decimal("0.00")).quantize(Decimal("0.01")))


def _bad_request(message):
    return Response(
        {"error": {"code": "VALIDATION_ERROR", "message": message}}, status=400
    )


class StaffSalesDetailView(APIView):
    """One response entry per sale, ordered newest first.

    `date_from` / `date_to` are optional and inclusive, resolved in the
    tenant's timezone: no params means today; `date_from` alone spans it to
    today; `date_to` alone covers that single day.

    A `tenant_admin` sees every staff member (optionally narrowed with
    `staff=<id>`); a `pos_staff` caller only ever sees their own sales.
    `totals` always describes the whole filtered range, not the returned page.
    """

    permission_classes = [IsAuthenticated, IsTenantAdminOrPOSSStaff]

    def get(self, request):
        tenant = request.tenant_obj
        tz = ZoneInfo(tenant.timezone or "UTC")
        today = timezone.now().astimezone(tz).date()

        raw_from = (request.query_params.get("date_from") or "").strip()
        raw_to = (request.query_params.get("date_to") or "").strip()

        try:
            end_day = _parse_day(raw_to) if raw_to else today
            start_day = _parse_day(raw_from) if raw_from else end_day
        except ValueError:
            return _bad_request("date_from and date_to must be YYYY-MM-DD.")
        if start_day > end_day:
            return _bad_request("date_from must be on or before date_to.")

        raw_limit = (request.query_params.get("limit") or "").strip()
        raw_offset = (request.query_params.get("offset") or "").strip()
        try:
            limit = int(raw_limit) if raw_limit else DEFAULT_LIMIT
            offset = int(raw_offset) if raw_offset else 0
        except ValueError:
            return _bad_request("limit and offset must be integers.")
        if limit < 1 or offset < 0:
            return _bad_request("limit must be positive and offset non-negative.")
        limit = min(limit, MAX_LIMIT)

        start = datetime.combine(start_day, time.min, tzinfo=tz)
        end = datetime.combine(end_day, time.min, tzinfo=tz) + timedelta(days=1)

        sales = Sale.objects.filter(
            tenant=tenant,
            created_at__gte=start,
            created_at__lt=end,
            source=Sale.Source.POS,
        )
        tickets = Ticket.objects.filter(
            tenant=tenant, issued_at__gte=start, issued_at__lt=end
        )

        scope = "tenant"
        if get_current_role() == "pos_staff":
            profile = StaffProfile.objects.filter(
                tenant=tenant, user=request.user, status=StaffProfile.Status.ACTIVE
            ).first()
            if profile is None:
                raise Forbidden("No active staff profile.")
            sales = sales.filter(staff=profile)
            tickets = tickets.filter(staff=profile)
            scope = "self"
        else:
            raw_staff = (request.query_params.get("staff") or "").strip()
            if raw_staff:
                if not raw_staff.isdigit():
                    return _bad_request("staff must be a numeric id.")
                sales = sales.filter(staff_id=int(raw_staff))
                tickets = tickets.filter(staff_id=int(raw_staff))

        summary = sales.aggregate(
            transactions=Count("id"),
            gross=Sum("gross_total"),
            refunds=Sum("refund_total"),
        )
        gross = summary["gross"] or Decimal("0.00")
        refunds = summary["refunds"] or Decimal("0.00")

        rows = (
            sales.select_related("event", "staff")
            .prefetch_related("items__category")
            .annotate(ticket_count=Count("tickets"))
            .order_by("-created_at")[offset : offset + limit]
        )

        sales_payload = []
        for sale in rows:
            local = timezone.localtime(sale.created_at, tz)
            sales_payload.append(
                {
                    "sale_id": sale.id,
                    "sale_reference": sale.sale_reference,
                    "created_at": sale.created_at.isoformat(),
                    "date": local.date().isoformat(),
                    "time": local.strftime("%H:%M:%S"),
                    "status": sale.status,
                    "event_id": sale.event_id,
                    "event_code": sale.event.code,
                    "event_name": sale.event.name,
                    "staff_id": sale.staff_id,
                    "staff_code": sale.staff.staff_code,
                    "staff_name": sale.staff.display_name,
                    "tickets": sale.ticket_count,
                    "items": [
                        {
                            "category_id": item.category_id,
                            "category_code": item.category.code,
                            "category_name": item.category.name,
                            "quantity": item.quantity,
                            "unit_price": _money(item.unit_price_snapshot),
                            "line_total": _money(item.line_total),
                        }
                        for item in sale.items.all()
                    ],
                    "gross_total": _money(sale.gross_total),
                    "refund_total": _money(sale.refund_total),
                    "net_total": _money(sale.gross_total - sale.refund_total),
                }
            )

        return Response(
            {
                "date_from": start_day.isoformat(),
                "date_to": end_day.isoformat(),
                "timezone": tenant.timezone,
                "currency": tenant.currency,
                "scope": scope,
                "count": summary["transactions"],
                "returned": len(sales_payload),
                "limit": limit,
                "offset": offset,
                "totals": {
                    "tickets": tickets.count(),
                    "transactions": summary["transactions"],
                    "amount": _money(gross),
                    "refunds": _money(refunds),
                    "net": _money(gross - refunds),
                },
                "sales": sales_payload,
            }
        )

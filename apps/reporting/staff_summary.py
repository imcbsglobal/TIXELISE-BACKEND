"""Standalone per-staff sales summary: tickets sold, transactions, amount.

Deliberately self-contained — it has its own route and imports no view or
serializer from the existing reporting module, so changes here cannot alter
`/admin/reports/staff/` or `/admin/reports/daily/`.
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


def _parse_day(raw):
    return datetime.strptime(raw, _DATE_FORMAT).date()


def _money(value):
    return str((value or Decimal("0.00")).quantize(Decimal("0.01")))


def _bad_request(message):
    return Response(
        {"error": {"code": "VALIDATION_ERROR", "message": message}}, status=400
    )


class StaffSalesSummaryView(APIView):
    """Ticket count, transaction count and gross amount per staff member.

    `date_from` / `date_to` are optional and inclusive, resolved in the
    tenant's timezone: no params means today; `date_from` alone spans it to
    today; `date_to` alone covers that single day.

    A `tenant_admin` sees every staff member; a `pos_staff` caller sees only
    their own row, with `scope: "self"` in the response.
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

        start = datetime.combine(start_day, time.min, tzinfo=tz)
        end = datetime.combine(end_day, time.min, tzinfo=tz) + timedelta(days=1)

        sale_rows = {
            row["staff_id"]: row
            for row in Sale.objects.filter(
                tenant=tenant,
                created_at__gte=start,
                created_at__lt=end,
            )
            .values("staff_id")
            .annotate(
                transactions=Count("id"),
                amount=Sum("gross_total"),
                tax=Sum("tax_total"),
            )
        }
        ticket_rows = {
            row["staff_id"]: row["tickets"]
            for row in Ticket.objects.filter(
                tenant=tenant, issued_at__gte=start, issued_at__lt=end
            )
            .values("staff_id")
            .annotate(tickets=Count("id"))
        }

        roster = StaffProfile.objects.filter(tenant=tenant)
        scope = "tenant"
        if get_current_role() == "pos_staff":
            profile = roster.filter(
                user=request.user, status=StaffProfile.Status.ACTIVE
            ).first()
            if profile is None:
                raise Forbidden("No active staff profile.")
            roster = roster.filter(id=profile.id)
            scope = "self"

        staff = []
        for member in roster.values("id", "staff_code", "display_name"):
            rollup = sale_rows.get(member["id"], {})
            amount = rollup.get("amount") or None
            tax = rollup.get("tax") or Decimal("0.00")
            staff.append(
                {
                    "staff_id": member["id"],
                    "staff_code": member["staff_code"],
                    "display_name": member["display_name"],
                    "tickets": ticket_rows.get(member["id"], 0),
                    "transactions": rollup.get("transactions", 0),
                    "amount": _money(amount),
                    "tax": _money(tax),
                    "total": _money((amount or Decimal("0.00")) + tax),
                }
            )

        staff.sort(key=lambda row: (-Decimal(row["amount"]), row["staff_code"]))

        return Response(
            {
                "date_from": start_day.isoformat(),
                "date_to": end_day.isoformat(),
                "timezone": tenant.timezone,
                "currency": tenant.currency,
                "scope": scope,
                "totals": {
                    "tickets": sum(row["tickets"] for row in staff),
                    "transactions": sum(row["transactions"] for row in staff),
                    "amount": _money(
                        sum((Decimal(row["amount"]) for row in staff), Decimal("0.00"))
                    ),
                    "tax": _money(
                        sum((Decimal(row["tax"]) for row in staff), Decimal("0.00"))
                    ),
                    "total": _money(
                        sum((Decimal(row["total"]) for row in staff), Decimal("0.00"))
                    ),
                },
                "staff": staff,
            }
        )

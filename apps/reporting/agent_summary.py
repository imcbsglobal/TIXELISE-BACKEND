from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Count, Max, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.models import Agent
from apps.core.permissions import IsTenantAdmin
from apps.sales.models import Sale
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


class AgentSalesSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

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
            row["agent_id"]: row
            for row in Sale.objects.filter(
                tenant=tenant,
                agent__isnull=False,
                created_at__gte=start,
                created_at__lt=end,
            )
            .values("agent_id")
            .annotate(
                transactions=Count("id"),
                gross=Sum("gross_total"),
                refunds=Sum("refund_total"),
                tax=Sum("tax_total"),
                last_sale_at=Max("created_at"),
            )
        }
        ticket_rows = {
            row["sale__agent_id"]: row["tickets"]
            for row in Ticket.objects.filter(
                tenant=tenant,
                sale__agent__isnull=False,
                issued_at__gte=start,
                issued_at__lt=end,
            )
            .values("sale__agent_id")
            .annotate(tickets=Count("id"))
        }

        agents = []
        for agent in Agent.objects.filter(tenant=tenant).values(
            "id", "code", "name", "place", "status"
        ):
            rollup = sale_rows.get(agent["id"], {})
            gross = rollup.get("gross") or Decimal("0.00")
            refunds = rollup.get("refunds") or Decimal("0.00")
            tax = rollup.get("tax") or Decimal("0.00")
            total = gross + tax - refunds
            agents.append(
                {
                    "agent_id": agent["id"],
                    "agent_code": agent["code"],
                    "agent_name": agent["name"],
                    "place": agent["place"],
                    "status": agent["status"],
                    "tickets": ticket_rows.get(agent["id"], 0),
                    "transactions": rollup.get("transactions", 0),
                    "gross": _money(gross),
                    "tax": _money(tax),
                    "refunds": _money(refunds),
                    "total": _money(total),
                    "last_sale_at": rollup.get("last_sale_at"),
                }
            )

        agents.sort(key=lambda row: (-Decimal(row["total"]), row["agent_code"]))

        return Response(
            {
                "date_from": start_day.isoformat(),
                "date_to": end_day.isoformat(),
                "timezone": tenant.timezone,
                "currency": tenant.currency,
                "totals": {
                    "agents_with_sales": sum(
                        1 for row in agents if row["transactions"] > 0
                    ),
                    "transactions": sum(row["transactions"] for row in agents),
                    "tickets": sum(row["tickets"] for row in agents),
                    "gross": _money(
                        sum((Decimal(row["gross"]) for row in agents), Decimal("0.00"))
                    ),
                    "tax": _money(
                        sum((Decimal(row["tax"]) for row in agents), Decimal("0.00"))
                    ),
                    "refunds": _money(
                        sum((Decimal(row["refunds"]) for row in agents), Decimal("0.00"))
                    ),
                    "total": _money(
                        sum((Decimal(row["total"]) for row in agents), Decimal("0.00"))
                    ),
                },
                "agents": agents,
            }
        )

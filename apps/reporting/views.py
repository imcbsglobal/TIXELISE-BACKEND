"""
Dashboard and daily report (MD §7.2 / §7.10).

Date boundaries use the tenant's configured timezone. Gross = completed
sales before refunds; net = gross - recorded refunds.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsTenantAdmin
from apps.events.models import Event
from apps.sales.models import Sale
from apps.staff.models import StaffProfile
from apps.ticketing.models import Ticket


def _tenant_now(tenant):
    tz = ZoneInfo(tenant.timezone or "UTC")
    return timezone.now().astimezone(tz)


def _day_bounds(tenant, day):
    tz = ZoneInfo(tenant.timezone or "UTC")
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end


def _sales_between(tenant, start, end):
    return Sale.objects.filter(
        tenant=tenant, created_at__gte=start, created_at__lt=end
    )


def _totals(sales_qs):
    agg = sales_qs.aggregate(gross=Sum("gross_total"), refunds=Sum("refund_total"))
    gross = (agg["gross"] or Decimal("0.00")).quantize(Decimal("0.01"))
    refunds = (agg["refunds"] or Decimal("0.00")).quantize(Decimal("0.01"))
    return gross, refunds, (gross - refunds).quantize(Decimal("0.01"))


class DashboardView(APIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        tenant = request.tenant_obj
        today = _tenant_now(tenant).date()
        start, end = _day_bounds(tenant, today)

        sales = _sales_between(tenant, start, end)
        gross, refunds, net = _totals(sales)

        tickets_today = Ticket.objects.filter(
            tenant=tenant, issued_at__gte=start, issued_at__lt=end
        ).count()

        return Response(
            {
                "date": today.isoformat(),
                "timezone": tenant.timezone,
                "tickets_sold_today": tickets_today,
                "completed_sales_today": sales.count(),
                "gross_sales_today": str(gross),
                "refunds_today": str(refunds),
                "net_sales_today": str(net),
                "active_events": Event.objects.filter(
                    tenant=tenant, status=Event.Status.ACTIVE
                ).count(),
                "active_staff": StaffProfile.objects.filter(
                    tenant=tenant, status=StaffProfile.Status.ACTIVE
                ).count(),
            }
        )


class DailyReportView(APIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        tenant = request.tenant_obj
        date_param = request.query_params.get("date")
        if date_param:
            try:
                day = datetime.strptime(date_param, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"error": {"code": "VALIDATION_ERROR", "message": "date must be YYYY-MM-DD."}},
                    status=400,
                )
        else:
            day = _tenant_now(tenant).date()

        start, end = _day_bounds(tenant, day)
        sales = _sales_between(tenant, start, end)
        gross, refunds, net = _totals(sales)

        tickets = Ticket.objects.filter(
            tenant=tenant, issued_at__gte=start, issued_at__lt=end
        )

        def bucket(field):
            return (
                tickets.values(field)
                .annotate(quantity=Count("id"))
                .order_by(field)
            )

        by_event = [
            {"event_id": row["event_id"], "tickets": row["quantity"]}
            for row in bucket("event_id")
        ]
        from apps.events.models import Event as E

        code_map = dict(E.objects.filter(tenant=tenant).values_list("id", "code"))
        for row in by_event:
            row["event_code"] = code_map.get(row["event_id"], "")

        by_category = [
            {"category_id": row["category_id"], "tickets": row["quantity"]}
            for row in bucket("category_id")
        ]
        from apps.catalog.models import TicketCategory as TC

        cat_map = dict(TC.objects.filter(tenant=tenant).values_list("id", "code"))
        for row in by_category:
            row["category_code"] = cat_map.get(row["category_id"], "")

        by_staff = [
            {"staff_id": row["staff_id"], "tickets": row["quantity"]}
            for row in bucket("staff_id")
        ]
        from apps.staff.models import StaffProfile as SP

        staff_map = dict(SP.objects.filter(tenant=tenant).values_list("id", "staff_code"))
        for row in by_staff:
            row["staff_code"] = staff_map.get(row["staff_id"], "")

        return Response(
            {
                "date": day.isoformat(),
                "timezone": tenant.timezone,
                "tickets_sold": tickets.count(),
                "transactions": sales.count(),
                "gross_sales": str(gross),
                "refunds": str(refunds),
                "net_sales": str(net),
                "by_event": by_event,
                "by_category": by_category,
                "by_staff": by_staff,
            }
        )

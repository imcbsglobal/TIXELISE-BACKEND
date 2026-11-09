"""
Dashboard and daily report (MD §7.2 / §7.10).

Date boundaries use the tenant's configured timezone. Gross = completed
sales before refunds; net = gross - recorded refunds.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import TicketCategory
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

        active_ticket_types = TicketCategory.objects.filter(
            tenant=tenant, status=TicketCategory.Status.ACTIVE
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
                "active_ticket_types": active_ticket_types,
                "active_staff": StaffProfile.objects.filter(
                    tenant=tenant, status=StaffProfile.Status.ACTIVE
                ).count(),
            }
        )


class DailyReportView(APIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        tenant = request.tenant_obj
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        if date_from or date_to:
            if not (date_from and date_to):
                return Response(
                    {
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "date_from and date_to must both be provided.",
                        }
                    },
                    status=400,
                )
            try:
                start_day = datetime.strptime(date_from, "%Y-%m-%d").date()
                end_day = datetime.strptime(date_to, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "date_from and date_to must be YYYY-MM-DD.",
                        }
                    },
                    status=400,
                )
            if start_day > end_day:
                return Response(
                    {
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "date_from must be on or before date_to.",
                        }
                    },
                    status=400,
                )
            start, _ = _day_bounds(tenant, start_day)
            _, end = _day_bounds(tenant, end_day)
        else:
            date_param = request.query_params.get("date")
            if date_param:
                try:
                    start_day = end_day = datetime.strptime(date_param, "%Y-%m-%d").date()
                except ValueError:
                    return Response(
                        {"error": {"code": "VALIDATION_ERROR", "message": "date must be YYYY-MM-DD."}},
                        status=400,
                    )
            else:
                start_day = end_day = _tenant_now(tenant).date()
            start, end = _day_bounds(tenant, start_day)
        sales = _sales_between(tenant, start, end)
        gross, refunds, net = _totals(sales)

        today_start, today_end = _day_bounds(tenant, _tenant_now(tenant).date())
        sales_today, _refunds_today, _net_today = _totals(
            _sales_between(tenant, today_start, today_end)
        )

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
        cents = Decimal("0.01")
        event_amounts = {
            row["event_id"]: (row["amount"] or Decimal("0.00")).quantize(cents)
            for row in sales.values("event_id").annotate(amount=Sum("gross_total"))
        }
        for row in by_event:
            row["event_code"] = code_map.get(row["event_id"], "")
            row["amount"] = str(event_amounts.get(row["event_id"], Decimal("0.00")))

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
                "date": start_day.isoformat()
                if start_day == end_day
                else f"{start_day.isoformat()}..{end_day.isoformat()}",
                "date_from": start_day.isoformat(),
                "date_to": end_day.isoformat(),
                "timezone": tenant.timezone,
                "tickets_sold": tickets.count(),
                "transactions": sales.count(),
                "gross_sales": str(gross),
                "refunds": str(refunds),
                "net_sales": str(net),
                "sales_today": str(sales_today),
                "by_event": by_event,
                "by_category": by_category,
                "by_staff": by_staff,
            }
        )


def _range_bounds(tenant, start_day, end_day):
    """Inclusive day range -> half-open aware datetimes in the tenant's timezone."""
    tz = ZoneInfo(tenant.timezone or "UTC")
    start = datetime.combine(start_day, time.min, tzinfo=tz)
    end = datetime.combine(end_day, time.min, tzinfo=tz) + timedelta(days=1)
    return start, end


def _parse_day(name, raw):
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be YYYY-MM-DD.")


def _money(value):
    return str((value or Decimal("0.00")).quantize(Decimal("0.01")))


def _validation_error(message):
    return Response(
        {"error": {"code": "VALIDATION_ERROR", "message": message}}, status=400
    )


class StaffReportView(APIView):
    """Per-staff sales totals plus a per-event split (MD §7.10 extension).

    Every staff member in the tenant is listed, including those with no sales in
    the range, so the table reconciles against the roster. Money keeps the daily
    report's definition: gross counts every sale row regardless of status and
    net = gross - recorded refunds; voided transactions are surfaced separately.
    """

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        tenant = request.tenant_obj
        params = request.query_params
        today = _tenant_now(tenant).date()

        try:
            start_day = (
                _parse_day("date_from", params["date_from"])
                if params.get("date_from")
                else today
            )
            end_day = (
                _parse_day("date_to", params["date_to"])
                if params.get("date_to")
                else today
            )
        except ValueError as exc:
            return _validation_error(str(exc))

        if start_day > end_day:
            return _validation_error("date_from must be on or before date_to.")

        event_raw = params.get("event") or ""
        staff_raw = params.get("staff") or ""
        if event_raw and not event_raw.isdigit():
            return _validation_error("event must be a numeric id.")
        if staff_raw and not staff_raw.isdigit():
            return _validation_error("staff must be a numeric id.")

        start, end = _range_bounds(tenant, start_day, end_day)

        sales = Sale.objects.filter(
            tenant=tenant, created_at__gte=start, created_at__lt=end
        )
        tickets = Ticket.objects.filter(
            tenant=tenant, issued_at__gte=start, issued_at__lt=end
        )
        if event_raw:
            sales = sales.filter(event_id=int(event_raw))
            tickets = tickets.filter(event_id=int(event_raw))
        if staff_raw:
            sales = sales.filter(staff_id=int(staff_raw))
            tickets = tickets.filter(staff_id=int(staff_raw))

        sale_rollup = {
            row["staff_id"]: row
            for row in sales.values("staff_id").annotate(
                transactions=Count("id"),
                voided=Count("id", filter=Q(status=Sale.Status.VOIDED)),
                gross=Sum("gross_total"),
                refunds=Sum("refund_total"),
                last_sale_at=Max("created_at"),
            )
        }
        ticket_rollup = {
            row["staff_id"]: row["tickets"]
            for row in tickets.values("staff_id").annotate(tickets=Count("id"))
        }
        ticket_by_event = {
            (row["staff_id"], row["event_id"]): row["tickets"]
            for row in tickets.values("staff_id", "event_id").annotate(
                tickets=Count("id")
            )
        }

        event_rollup = {}
        for bucket in (
            sales.values("staff_id", "event_id")
            .annotate(
                transactions=Count("id"),
                gross=Sum("gross_total"),
                refunds=Sum("refund_total"),
            )
            .order_by("event_id")
        ):
            event_rollup.setdefault(bucket["staff_id"], []).append(bucket)

        event_map = {
            row["id"]: row
            for row in Event.objects.filter(tenant=tenant).values("id", "code", "name")
        }

        staff_qs = StaffProfile.objects.filter(tenant=tenant)
        if staff_raw:
            staff_qs = staff_qs.filter(id=int(staff_raw))

        rows = []
        for member in staff_qs.values("id", "staff_code", "display_name", "status"):
            rollup = sale_rollup.get(member["id"], {})
            gross = rollup.get("gross") or Decimal("0.00")
            refunds = rollup.get("refunds") or Decimal("0.00")
            tickets_sold = ticket_rollup.get(member["id"], 0)
            last_sale = rollup.get("last_sale_at")

            by_event = []
            for bucket in event_rollup.get(member["id"], []):
                meta = event_map.get(bucket["event_id"], {})
                by_event.append(
                    {
                        "event_id": bucket["event_id"],
                        "event_code": meta.get("code", ""),
                        "event_name": meta.get("name", ""),
                        "transactions": bucket["transactions"],
                        "tickets": ticket_by_event.get(
                            (member["id"], bucket["event_id"]), 0
                        ),
                        "gross": _money(bucket["gross"]),
                        "refunds": _money(bucket["refunds"]),
                    }
                )

            rows.append(
                {
                    "staff_id": member["id"],
                    "staff_code": member["staff_code"],
                    "display_name": member["display_name"],
                    "status": member["status"],
                    "transactions": rollup.get("transactions", 0),
                    "voided_transactions": rollup.get("voided", 0),
                    "tickets": tickets_sold,
                    "gross": _money(gross),
                    "refunds": _money(refunds),
                    "net": _money(gross - refunds),
                    "avg_ticket_value": _money(gross / tickets_sold)
                    if tickets_sold
                    else None,
                    "last_sale_at": last_sale.isoformat() if last_sale else None,
                    "by_event": by_event,
                }
            )

        # Busiest earners first; staff with no sales fall to the bottom by code.
        rows.sort(key=lambda row: (-Decimal(row["net"]), row["staff_code"]))

        gross_total, refunds_total, net_total = _totals(sales)

        return Response(
            {
                "date_from": start_day.isoformat(),
                "date_to": end_day.isoformat(),
                "timezone": tenant.timezone,
                "currency": tenant.currency,
                "totals": {
                    "staff_with_sales": sum(1 for row in rows if row["transactions"]),
                    "transactions": sum(row["transactions"] for row in rows),
                    "tickets": sum(row["tickets"] for row in rows),
                    "gross": str(gross_total),
                    "refunds": str(refunds_total),
                    "net": str(net_total),
                },
                "staff": rows,
            }
        )

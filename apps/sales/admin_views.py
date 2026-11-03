from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import IsTenantAdmin

from .models import Sale
from .serializers import SaleSerializer


def _day_start(tenant, raw, field):
    """Midnight of `raw` in the tenant's timezone; kept aware so UTC rows match."""
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValidationError({field: "must be YYYY-MM-DD."})
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(tenant.timezone or "UTC"))


class AdminSaleListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = SaleSerializer

    def get_queryset(self):
        qs = Sale.objects.select_related("event", "staff").prefetch_related(
            "items__category", "tickets"
        )
        params = self.request.query_params
        if params.get("event"):
            qs = qs.filter(event_id=params["event"])
        if params.get("staff"):
            qs = qs.filter(staff_id=params["staff"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("sale_reference"):
            qs = qs.filter(sale_reference=params["sale_reference"])
        if params.get("date_from"):
            qs = qs.filter(
                created_at__gte=_day_start(
                    self.request.tenant_obj, params["date_from"], "date_from"
                )
            )
        if params.get("date_to"):
            qs = qs.filter(
                created_at__lt=_day_start(
                    self.request.tenant_obj, params["date_to"], "date_to"
                )
                + timedelta(days=1)
            )
        return qs


class AdminSaleDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = SaleSerializer

    def get_queryset(self):
        return Sale.objects.select_related("event", "staff").prefetch_related(
            "items__category", "tickets"
        )

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import IsTenantAdmin

from .models import Sale
from .serializers import SaleSerializer


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
        return qs


class AdminSaleDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = SaleSerializer

    def get_queryset(self):
        return Sale.objects.select_related("event", "staff").prefetch_related(
            "items__category", "tickets"
        )

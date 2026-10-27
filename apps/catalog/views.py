from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.context import get_current_tenant_id
from apps.core.exceptions import Conflict, NotFound
from apps.core.permissions import IsTenantAdmin

from .models import EventPrice, TicketCategory, TicketTemplate
from .serializers import (
    EventPriceSerializer,
    EventPriceStatusSerializer,
    TicketCategorySerializer,
    TicketCategoryStatusSerializer,
    TicketTemplateSerializer,
)


class _AuditCreateMixin:
    audit_action = None
    audit_target = None

    def perform_create(self, serializer):
        obj = serializer.save(tenant_id=get_current_tenant_id())
        record_audit(
            actor=self.request.user,
            tenant=obj.tenant,
            action=self.audit_action,
            target_type=self.audit_target,
            target_id=obj.id,
        )
        return obj


class TicketCategoryListCreateView(_AuditCreateMixin, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = TicketCategorySerializer
    audit_action = "category.created"
    audit_target = "ticket_category"

    def get_queryset(self):
        return TicketCategory.objects.all()


class TicketCategoryDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = TicketCategorySerializer

    def get_queryset(self):
        return TicketCategory.objects.all()

    def perform_update(self, serializer):
        obj = serializer.save()
        record_audit(
            actor=self.request.user,
            tenant=obj.tenant,
            action="category.updated",
            target_type="ticket_category",
            target_id=obj.id,
        )

    def delete(self, request, pk):
        """Permanently removes the category row (and its prices) from the database.

        A category that already has sold tickets cannot be removed: the sale
        and ticket history points at it. Those can only be deactivated, which
        keeps the history intact while hiding the category from the POS.
        """
        try:
            category = TicketCategory.objects.get(pk=pk)
        except TicketCategory.DoesNotExist:
            raise NotFound("Category not found.")

        if category.tickets.exists() or category.sale_items.exists():
            raise Conflict(
                f"{category.code} already has sold tickets, so it cannot be permanently "
                "deleted. Deactivate it instead - it disappears from the POS catalogue "
                "and the sales history stays untouched."
            )

        category_id = category.id
        code = category.code
        tenant = category.tenant
        prices_removed = category.eventprices.count()
        category.eventprices.all().delete()
        category.delete()

        record_audit(
            actor=request.user,
            tenant=tenant,
            action="category.deleted",
            target_type="ticket_category",
            target_id=category_id,
            metadata={"code": code, "prices_removed": prices_removed},
        )
        return Response(
            {"deleted": True, "code": code, "prices_removed": prices_removed},
            status=200,
        )


class TicketCategoryStatusView(APIView):
    """Soft delete / restore a ticket category.

    A category is never hard deleted: prices and sold tickets point at it and
    must keep working for history. Setting it to inactive removes it from the
    POS catalogue and blocks new prices, which is what a delete means here.
    """

    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = TicketCategoryStatusSerializer

    def post(self, request, pk):
        try:
            category = TicketCategory.objects.get(pk=pk)
        except TicketCategory.DoesNotExist:
            raise NotFound("Category not found.")

        serializer = TicketCategoryStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        status = serializer.validated_data["status"]

        category.status = status
        category.save(update_fields=["status", "updated_at"])
        record_audit(
            actor=request.user,
            tenant=category.tenant,
            action=f"category.{status}",
            target_type="ticket_category",
            target_id=category.id,
            metadata={"code": category.code},
        )
        return Response(TicketCategorySerializer(category).data)


class EventPriceListCreateView(_AuditCreateMixin, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = EventPriceSerializer
    audit_action = "price.created"
    audit_target = "event_price"

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant_id"] = get_current_tenant_id()
        return ctx

    def get_queryset(self):
        qs = EventPrice.objects.all()
        event_id = self.request.query_params.get("event")
        if event_id:
            qs = qs.filter(event_id=event_id)
        return qs

    def perform_create(self, serializer):
        obj = serializer.save(tenant_id=get_current_tenant_id())
        record_audit(
            actor=self.request.user,
            tenant=obj.tenant,
            action="price.created",
            target_type="event_price",
            target_id=obj.id,
            metadata={"amount": str(obj.amount), "event_id": obj.event_id},
        )


class EventPriceDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = EventPriceSerializer

    def get_queryset(self):
        return EventPrice.objects.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant_id"] = get_current_tenant_id()
        return ctx

    def perform_update(self, serializer):
        obj = serializer.save()
        record_audit(
            actor=self.request.user,
            tenant=obj.tenant,
            action="price.updated",
            target_type="event_price",
            target_id=obj.id,
            metadata={"amount": str(obj.amount)},
        )


class EventPriceStatusView(APIView):
    """Soft delete / restore a single event price.

    Past sales keep their own price snapshot, so switching the price off only
    stops future sales of that category for that event.
    """

    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = EventPriceStatusSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant_id"] = get_current_tenant_id()
        return ctx

    def post(self, request, pk):
        try:
            price = EventPrice.objects.get(pk=pk)
        except EventPrice.DoesNotExist:
            raise NotFound("Price not found.")

        serializer = EventPriceStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        status = serializer.validated_data["status"]

        price.status = status
        price.save(update_fields=["status", "updated_at"])
        record_audit(
            actor=request.user,
            tenant=price.tenant,
            action=f"price.{status}",
            target_type="event_price",
            target_id=price.id,
            metadata={"amount": str(price.amount), "event_id": price.event_id},
        )
        return Response(EventPriceSerializer(price).data)


class TicketTemplateListCreateView(_AuditCreateMixin, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = TicketTemplateSerializer
    audit_action = "template.created"
    audit_target = "ticket_template"

    def get_queryset(self):
        return TicketTemplate.objects.all()


class TicketTemplateDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = TicketTemplateSerializer

    def get_queryset(self):
        return TicketTemplate.objects.all()

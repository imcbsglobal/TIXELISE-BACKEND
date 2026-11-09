from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.context import get_current_tenant_id
from apps.core.exceptions import BadRequest, Conflict, NotFound
from apps.core.permissions import IsTenantAdmin

from .models import Event
from .serializers import EventSerializer

# Explicit, audited state machine (MD §7.3).
ALLOWED_TRANSITIONS = {
    ("draft", "active"),
    ("draft", "cancelled"),
    ("active", "completed"),
    ("active", "cancelled"),
}


class EventListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = EventSerializer

    def get_queryset(self):
        qs = Event.objects.all()
        params = self.request.query_params
        search = params.get("search")
        if search:
            from django.db.models import Q

            qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search))
        event_status = params.get("status")
        if event_status:
            qs = qs.filter(status=event_status)
        return qs

    def perform_create(self, serializer):
        # The starting status comes from the payload (the New event form sends
        # `active`); callers that omit it, such as the setup wizard, fall back to
        # the model default (draft).
        event = serializer.save(
            tenant_id=get_current_tenant_id(),
            created_by=self.request.user,
        )
        record_audit(
            actor=self.request.user,
            tenant=event.tenant,
            action="event.created",
            target_type="event",
            target_id=event.id,
            metadata={"code": event.code, "name": event.name},
        )


class EventDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = EventSerializer

    def get_queryset(self):
        return Event.objects.all()

    def perform_update(self, serializer):
        event = serializer.save()
        record_audit(
            actor=self.request.user,
            tenant=event.tenant,
            action="event.updated",
            target_type="event",
            target_id=event.id,
            metadata={"code": event.code},
        )

    def delete(self, request, pk):
        """Permanently remove an event that has never been used for sales."""
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            raise NotFound("Event not found.")

        # Sales and tickets are financial/history records and deliberately use
        # PROTECT foreign keys. Return a useful API error instead of exposing
        # a database integrity error to the admin UI.
        if event.sales.exists() or event.tickets.exists():
            raise Conflict(
                f"{event.code} already has sales or issued tickets, so it cannot be "
                "permanently deleted. Cancel the event instead to preserve its history."
            )

        event_id = event.id
        code = event.code
        tenant = event.tenant
        with transaction.atomic():
            # Prices and staff assignments are configuration records whose
            # foreign keys cascade when their unused event is deleted.
            event.delete()
            record_audit(
                actor=request.user,
                tenant=tenant,
                action="event.deleted",
                target_type="event",
                target_id=event_id,
                metadata={"code": code},
            )

        return Response({"deleted": True, "code": code}, status=status.HTTP_200_OK)


class EventTransitionView(APIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def post(self, request, pk, target_status):
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            raise NotFound("Event not found.")

        if (event.status, target_status) not in ALLOWED_TRANSITIONS:
            raise BadRequest(
                detail=f"Cannot transition from {event.status} to {target_status}.",
                code="INVALID_TRANSITION",
            )

        if target_status == "active":
            has_price = event.eventprices.exists()
            if not has_price:
                raise BadRequest(
                    detail="An event must have at least one price before activation.",
                    code="CONFIGURATION_INCOMPLETE",
                )

        with transaction.atomic():
            event.status = target_status
            event.save(update_fields=["status", "updated_at"])
            record_audit(
                actor=request.user,
                tenant=event.tenant,
                action=f"event.{target_status}",
                target_type="event",
                target_id=event.id,
                metadata={"code": event.code},
            )
        return Response({"id": event.id, "status": event.status}, status=status.HTTP_200_OK)

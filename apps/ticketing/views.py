from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.exceptions import Forbidden, NotFound
from apps.core.permissions import IsTenantAdmin
from apps.sales.serializers import SaleSerializer
from apps.sales.services import issue_manual_tickets

from .models import Ticket
from .serializers import (
    ManualTicketIssueSerializer,
    TicketListSerializer,
    TicketSerializer,
)


def _tenant(request):
    """The tenant behind the request.

    This endpoint authenticates with IsAuthenticated (POS staff read it too), so
    unlike the admin views it cannot assume TenantScopedPermission has attached
    the tenant object yet.
    """
    tenant = getattr(request, "tenant_obj", None)
    if tenant is not None:
        return tenant
    from apps.core.context import get_current_tenant_id
    from apps.tenancy.models import Tenant

    tenant_id = get_current_tenant_id()
    return Tenant.objects.filter(pk=tenant_id).first() if tenant_id else None


def _day_start(tenant, raw, field):
    """Midnight of `raw` in the tenant's timezone; kept aware so UTC rows match."""
    from rest_framework.exceptions import ValidationError

    try:
        day = datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValidationError({field: "must be YYYY-MM-DD."})
    zone = getattr(tenant, "timezone", None) or "UTC"
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(zone))


class TicketListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TicketListSerializer

    def get_queryset(self):
        from apps.core.context import get_current_role

        qs = Ticket.objects.select_related("event", "staff", "category", "sale")
        params = self.request.query_params
        if params.get("event"):
            qs = qs.filter(event_id=params["event"])
        if params.get("staff"):
            qs = qs.filter(staff_id=params["staff"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("ticket_code"):
            qs = qs.filter(ticket_code=params["ticket_code"])
        # Issued-date bounds, in the tenant's timezone, matching the sales list.
        if params.get("date_from") or params.get("date_to"):
            tenant = _tenant(self.request)
        if params.get("date_from"):
            qs = qs.filter(
                issued_at__gte=_day_start(tenant, params["date_from"], "date_from")
            )
        if params.get("date_to"):
            qs = qs.filter(
                issued_at__lt=_day_start(tenant, params["date_to"], "date_to")
                + timedelta(days=1)
            )
        return qs


class TicketDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TicketListSerializer

    def get_queryset(self):
        return Ticket.objects.select_related("event", "staff", "category", "sale")


class TicketReprintView(APIView):
    """
    POS or admin reprint. Records the reprint — never creates a new ticket
    or sale (MD §11.3 printing retries).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from apps.core.context import get_current_role, get_current_tenant_id

        try:
            ticket = Ticket.objects.select_related("event", "staff", "category", "sale").get(
                pk=pk
            )
        except Ticket.DoesNotExist:
            raise NotFound("Ticket not found.")

        role = get_current_role()
        if role == "pos_staff":
            if ticket.staff.user_id != request.user.id:
                raise Forbidden("You may only reprint your own tickets.")
        elif role != "tenant_admin":
            raise Forbidden()

        ticket.reprint_count += 1
        ticket.save(update_fields=["reprint_count"])
        record_audit(
            actor=request.user,
            tenant=ticket.tenant,
            action="ticket.reprint",
            target_type="ticket",
            target_id=str(ticket.id),
            metadata={"ticket_code": ticket.ticket_code, "reprint_count": ticket.reprint_count},
        )
        return Response(
            {
                "id": str(ticket.id),
                "ticket_code": ticket.ticket_code,
                "reprint_count": ticket.reprint_count,
                "print_payload": {
                    "ticket_code": ticket.ticket_code,
                    "event": {"code": ticket.event.code, "name": ticket.event.name, "venue": ticket.event.venue},
                    "category": ticket.category.name,
                    "issued_at": ticket.issued_at.isoformat(),
                    "sequence_number": ticket.sequence_number,
                },
            },
            status=status.HTTP_200_OK,
        )


class ManualTicketIssueView(APIView):
    """Admin-issued manual tickets (a real, priced and taxed sale)."""

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def post(self, request):
        serializer = ManualTicketIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        items_data = [
            {"category_id": item["category"], "quantity": item["quantity"]}
            for item in serializer.validated_data["items"]
        ]
        idempotency_key = request.headers.get(
            "Idempotency-Key"
        ) or request.data.get("idempotency_key")

        result = issue_manual_tickets(
            tenant=request.tenant_obj,
            user=request.user,
            # Absent/null means the admin issues the tickets as themselves.
            staff_id=serializer.validated_data.get("staff"),
            agent_id=serializer.validated_data.get("agent"),
            event_id=serializer.validated_data["event"],
            items_data=items_data,
            idempotency_key=idempotency_key,
        )

        payload = SaleSerializer(result["sale"]).data
        payload["replayed"] = result["replayed"]
        return Response(
            payload,
            status=status.HTTP_201_CREATED
            if not result["replayed"]
            else status.HTTP_200_OK,
        )

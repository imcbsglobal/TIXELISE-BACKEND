from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assignments.models import StaffEventAssignment
from apps.catalog.models import EventPrice, TicketCategory
from apps.core.context import get_current_tenant_id, get_current_role
from apps.core.exceptions import Forbidden, NotFound
from apps.core.permissions import IsPOSSStaff
from apps.events.models import Event
from apps.staff.models import StaffProfile
from apps.taxation.services import apply_tax_to_line, resolve_tax
from apps.ticketing.models import Ticket

from .serializers import SaleCreateSerializer, SaleSerializer
from .services import create_sale


def _current_staff(request) -> StaffProfile:
    try:
        return StaffProfile.objects.get(user=request.user, status=StaffProfile.Status.ACTIVE)
    except StaffProfile.DoesNotExist:
        raise Forbidden("No active staff profile.")


class POSEventListView(APIView):
    """Assigned + active events only (MD §6.3)."""

    permission_classes = [IsAuthenticated, IsPOSSStaff]

    def get(self, request):
        staff = _current_staff(request)
        now_assignments = StaffEventAssignment.objects.filter(
            staff=staff, status=StaffEventAssignment.Status.ACTIVE
        ).select_related("event")
        event_ids = [
            a.event_id
            for a in now_assignments
            if a.is_usable_at() and a.event.status == Event.Status.ACTIVE
        ]
        events = Event.objects.filter(id__in=event_ids)
        return Response(
            [
                {
                    "id": e.id,
                    "code": e.code,
                    "name": e.name,
                    "venue": e.venue,
                    "start_at": e.start_at.isoformat(),
                    "end_at": e.end_at.isoformat() if e.end_at else None,
                    "event_type": e.event_type,
                }
                for e in events
            ]
        )


class POSCategoryListView(APIView):
    """Sellable categories for an event, honoring assignment restrictions."""

    permission_classes = [IsAuthenticated, IsPOSSStaff]

    def get(self, request, event_id):
        staff = _current_staff(request)
        try:
            assignment = StaffEventAssignment.objects.get(
                staff=staff, event_id=event_id, status=StaffEventAssignment.Status.ACTIVE
            )
        except StaffEventAssignment.DoesNotExist:
            raise Forbidden("You are not assigned to this event.")
        if not assignment.is_usable_at():
            raise Forbidden("This assignment is not currently valid.")

        prices = (
            EventPrice.objects.filter(
                event_id=event_id, status=EventPrice.Status.ACTIVE
            )
            .select_related("category")
            .filter(category__status=TicketCategory.Status.ACTIVE)
        )
        if assignment.restrict_categories:
            allowed = assignment.allowed_categories.values_list("id", flat=True)
            prices = prices.filter(category_id__in=allowed)

        # The terminal shows price + tax, so it needs the rate too. Read from the
        # stored setting (no network call) exactly like a sale does.
        tax = resolve_tax(request.tenant_obj)
        rows = []
        for p in prices:
            net, tax_amount = apply_tax_to_line(
                unit_price=p.amount, quantity=1, tax=tax
            )
            rows.append(
                {
                    "category": p.category.id,
                    "code": p.category.code,
                    "name": p.category.name,
                    "price": str(p.amount),
                    "currency": p.currency,
                    "tax_rate": str(tax.rate) if tax else "0.00",
                    "tax_code": tax.code if tax else "",
                    "tax_included": bool(tax.prices_include_tax) if tax else False,
                    "tax_amount": str(tax_amount),
                    "price_with_tax": str(net + tax_amount),
                }
            )
        return Response(rows)


class POSSaleCreateView(APIView):
    permission_classes = [IsAuthenticated, IsPOSSStaff]

    def post(self, request):
        staff = _current_staff(request)
        serializer = SaleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        items_data = [
            {"category_id": item["category"], "quantity": item["quantity"]}
            for item in serializer.validated_data["items"]
        ]

        idempotency_key = request.headers.get("Idempotency-Key") or request.data.get(
            "idempotency_key"
        )

        result = create_sale(
            tenant=request.tenant_obj,
            user=request.user,
            staff=staff,
            event_id=serializer.validated_data["event"],
            items_data=items_data,
            idempotency_key=idempotency_key,
        )

        sale = result["sale"]
        payload = SaleSerializer(sale).data
        payload["replayed"] = result["replayed"]
        return Response(payload, status=status.HTTP_201_CREATED if not result["replayed"] else status.HTTP_200_OK)


class POSSaleHistoryView(APIView):
    permission_classes = [IsAuthenticated, IsPOSSStaff]

    def get(self, request):
        staff = _current_staff(request)
        sales = Sale.objects.filter(staff=staff).select_related("event", "staff")[:50]
        return Response(SaleSerializer(sales, many=True).data)


class POSTicketDetailView(APIView):
    permission_classes = [IsAuthenticated, IsPOSSStaff]

    def get(self, request, pk):
        staff = _current_staff(request)
        try:
            ticket = Ticket.objects.select_related("event", "category", "staff", "sale").get(
                pk=pk
            )
        except Ticket.DoesNotExist:
            raise NotFound("Ticket not found.")
        if ticket.staff_id != staff.id:
            raise Forbidden("You may only view your own tickets.")
        from apps.ticketing.serializers import TicketSerializer

        return Response(TicketSerializer(ticket).data)

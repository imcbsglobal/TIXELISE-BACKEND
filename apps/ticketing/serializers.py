from rest_framework import serializers

from .models import Ticket


class TicketSerializer(serializers.ModelSerializer):
    event_code = serializers.CharField(source="event.code", read_only=True)
    staff_code = serializers.CharField(source="staff.staff_code", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "ticket_code",
            "event",
            "event_code",
            "staff",
            "staff_code",
            "category",
            "category_name",
            "sequence_number",
            "status",
            "issued_at",
            "reprint_count",
        ]


class TicketListSerializer(TicketSerializer):
    """Admin listing/detail: also reports which channel issued the ticket.

    Kept separate from TicketSerializer so nested tickets inside a sale
    (POS responses) never trigger a per-ticket sale lookup.
    """

    source = serializers.CharField(source="sale.source", read_only=True)

    class Meta(TicketSerializer.Meta):
        fields = TicketSerializer.Meta.fields + ["source"]


class ManualTicketItemSerializer(serializers.Serializer):
    category = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=100)


class ManualTicketIssueSerializer(serializers.Serializer):
    event = serializers.IntegerField()
    # Omitted or null means "the issuing admin": no assignment is required.
    # A value issues the tickets on behalf of that (assigned) staff member.
    staff = serializers.IntegerField(required=False, allow_null=True)
    items = ManualTicketItemSerializer(many=True, allow_empty=False)

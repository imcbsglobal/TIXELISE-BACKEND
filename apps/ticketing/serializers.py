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

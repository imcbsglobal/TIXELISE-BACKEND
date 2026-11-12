from decimal import Decimal

from rest_framework import serializers

from apps.ticketing.serializers import TicketSerializer

from .models import Sale, SaleItem


class SaleItemCreateSerializer(serializers.Serializer):
    category = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=100)


class SaleCreateSerializer(serializers.Serializer):
    event = serializers.IntegerField()
    items = SaleItemCreateSerializer(many=True)


class SaleItemSerializer(serializers.ModelSerializer):
    category_code = serializers.CharField(source="category.code", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = SaleItem
        fields = [
            "id",
            "category",
            "category_code",
            "category_name",
            "quantity",
            "unit_price_snapshot",
            "line_total",
            "tax_rate_snapshot",
            "tax_code",
            "tax_name",
            "tax_amount",
        ]


class SaleSerializer(serializers.ModelSerializer):
    event_code = serializers.CharField(source="event.code", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    staff_code = serializers.CharField(source="staff.staff_code", read_only=True)
    staff_name = serializers.CharField(source="staff.display_name", read_only=True)
    items = SaleItemSerializer(many=True, read_only=True)
    tickets = TicketSerializer(many=True, read_only=True)
    total_payable = serializers.SerializerMethodField()

    def get_total_payable(self, obj):
        """What the customer actually paid: taxable subtotal + tax - refunds.

        Identical to `gross_total` on every sale created before tax existed,
        because `tax_total` defaults to zero.
        """
        value = (
            Decimal(obj.gross_total or 0)
            + Decimal(obj.tax_total or 0)
            - Decimal(obj.refund_total or 0)
        )
        return str(value.quantize(Decimal("0.01")))

    class Meta:
        model = Sale
        fields = [
            "id",
            "sale_reference",
            "event",
            "event_code",
            "event_name",
            "staff",
            "staff_code",
            "staff_name",
            "status",
            "source",
            "gross_total",
            "tax_total",
            "refund_total",
            "total_payable",
            "currency",
            "items",
            "tickets",
            "created_at",
        ]

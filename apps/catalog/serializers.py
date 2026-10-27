from rest_framework import serializers

from apps.events.models import Event

from .models import EventPrice, TicketCategory, TicketTemplate


class TicketCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketCategory
        fields = ["id", "code", "name", "description", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

    def validate_code(self, value):
        value = value.upper()
        qs = TicketCategory.objects.filter(code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Category code already exists in this tenant.")
        return value


class EventPriceSerializer(serializers.ModelSerializer):
    category_code = serializers.CharField(source="category.code", read_only=True)

    class Meta:
        model = EventPrice
        fields = [
            "id",
            "event",
            "category",
            "category_code",
            "amount",
            "currency",
            "effective_from",
            "effective_to",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

    def validate_category(self, value):
        if value.tenant_id != self.context["tenant_id"]:
            raise serializers.ValidationError("Category belongs to another tenant.")
        if value.status != TicketCategory.Status.ACTIVE:
            raise serializers.ValidationError("Category is inactive.")
        return value

    def validate_event(self, value):
        if value.tenant_id != self.context["tenant_id"]:
            raise serializers.ValidationError("Event belongs to another tenant.")
        return value

    def validate(self, attrs):
        event = attrs.get("event") or (self.instance.event if self.instance else None)
        category = attrs.get("category") or (
            self.instance.category if self.instance else None
        )
        if event and category:
            qs = EventPrice.objects.filter(event=event, category=category)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"category": "A price already exists for this event and category."}
                )
        return attrs


class TicketCategoryStatusSerializer(serializers.Serializer):
    """Switches a category between active and inactive (soft delete)."""

    status = serializers.ChoiceField(choices=TicketCategory.Status.choices)


class EventPriceStatusSerializer(serializers.Serializer):
    """Switches a price between active and inactive (soft delete)."""

    status = serializers.ChoiceField(choices=EventPrice.Status.choices)


class TicketTemplateSerializer(serializers.ModelSerializer):
    ALLOWED_CONFIG_KEYS = {
        "header",
        "footer",
        "show_event_name",
        "show_venue",
        "show_category",
        "show_price",
        "show_ticket_number",
        "datetime_format",
        "logo_url",
        "paper_width",
        "printer_format",
    }

    class Meta:
        model = TicketTemplate
        fields = ["id", "name", "config", "version", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "version", "status", "created_at", "updated_at"]

    def validate_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Config must be an object.")
        unknown = set(value.keys()) - self.ALLOWED_CONFIG_KEYS
        if unknown:
            raise serializers.ValidationError(
                f"Unknown config keys: {', '.join(sorted(unknown))}"
            )
        return value

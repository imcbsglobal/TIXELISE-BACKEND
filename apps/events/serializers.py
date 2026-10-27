from django.utils import timezone
from rest_framework import serializers

from .models import Event


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            "id",
            "code",
            "name",
            "description",
            "venue",
            "address",
            "start_at",
            "end_at",
            "sales_start_at",
            "sales_end_at",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        start_at = attrs.get("start_at") or (self.instance.start_at if self.instance else None)
        end_at = attrs.get("end_at") or (self.instance.end_at if self.instance else None)
        if start_at and end_at and end_at <= start_at:
            raise serializers.ValidationError({"end_at": "End time must be after start time."})

        sales_start = attrs.get("sales_start_at", getattr(self.instance, "sales_start_at", None))
        sales_end = attrs.get("sales_end_at", getattr(self.instance, "sales_end_at", None))
        if sales_start and sales_end and sales_end <= sales_start:
            raise serializers.ValidationError(
                {"sales_end_at": "Sales end must be after sales start."}
            )
        return attrs

    def validate_code(self, value):
        if not value.isalnum():
            raise serializers.ValidationError("Event code must be alphanumeric.")
        value = value.upper()
        qs = Event.objects.filter(code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Event code already exists in this tenant.")
        return value


class EventStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Event.Status.choices)

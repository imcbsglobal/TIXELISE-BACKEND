from rest_framework import serializers

from apps.catalog.models import TicketCategory
from apps.events.models import Event
from apps.staff.models import StaffProfile

from .models import StaffEventAssignment


class AssignmentSerializer(serializers.ModelSerializer):
    staff_code = serializers.CharField(source="staff.staff_code", read_only=True)
    event_code = serializers.CharField(source="event.code", read_only=True)
    allowed_category_ids = serializers.PrimaryKeyRelatedField(
        queryset=TicketCategory.objects.all(),
        many=True,
        source="allowed_categories",
        required=False,
    )

    class Meta:
        model = StaffEventAssignment
        fields = [
            "id",
            "staff",
            "staff_code",
            "event",
            "event_code",
            "status",
            "valid_from",
            "valid_until",
            "restrict_categories",
            "allowed_category_ids",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        tenant_id = self.context["tenant_id"]
        staff = attrs.get("staff") or (self.instance.staff if self.instance else None)
        event = attrs.get("event") or (self.instance.event if self.instance else None)

        if staff and staff.tenant_id != tenant_id:
            raise serializers.ValidationError({"staff": "Staff belongs to another tenant."})
        if event and event.tenant_id != tenant_id:
            raise serializers.ValidationError({"event": "Event belongs to another tenant."})

        for category in attrs.get("allowed_categories", []):
            if category.tenant_id != tenant_id:
                raise serializers.ValidationError(
                    {"allowed_category_ids": "Category belongs to another tenant."}
                )

        valid_from = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_until = attrs.get("valid_until", getattr(self.instance, "valid_until", None))
        if valid_from and valid_until and valid_until <= valid_from:
            raise serializers.ValidationError(
                {"valid_until": "valid_until must be after valid_from."}
            )

        if staff and event:
            qs = StaffEventAssignment.objects.filter(staff=staff, event=event)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"event": "This staff member is already assigned to this event."}
                )
        return attrs

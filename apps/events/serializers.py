import re

from django.utils import timezone
from rest_framework import serializers

from .models import Event


class EventSerializer(serializers.ModelSerializer):
    program_duration_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "code",
            "name",
            "event_type",
            "description",
            "venue",
            "address",
            "start_at",
            "end_at",
            "sales_start_at",
            "sales_end_at",
            "program_start_time",
            "program_end_time",
            "program_duration_minutes",
            "tax_mode",
            "tax_rate",
            "hsn_code",
            "prices_include_tax",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]
        # Regular events carry no schedule, so required-ness is decided in validate().
        extra_kwargs = {
            "start_at": {"required": False},
            "end_at": {"required": False},
            "program_start_time": {"required": False},
            "program_end_time": {"required": False},
            "tax_rate": {"required": False},
            "hsn_code": {"required": False},
        }

    def validate(self, attrs):
        event_type = attrs.get("event_type") or (
            self.instance.event_type if self.instance else Event.EventType.PERIODICAL
        )

        if event_type == Event.EventType.REGULAR:
            # Regular events sell from "now" and never end; the schedule is
            # never user-supplied. Re-saving one keeps its original start_at.
            if self.instance is None:
                now = timezone.now()
                attrs["start_at"] = attrs.get("start_at") or now
                attrs["sales_start_at"] = attrs.get("sales_start_at") or now
            attrs["end_at"] = None
            attrs["sales_end_at"] = None
        else:
            start_at = attrs.get("start_at") or (
                self.instance.start_at if self.instance else None
            )
            end_at = attrs.get("end_at") or (
                self.instance.end_at if self.instance else None
            )
            if start_at is None:
                raise serializers.ValidationError(
                    {"start_at": "Start time is required for a periodical event."}
                )
            if end_at is None:
                raise serializers.ValidationError(
                    {"end_at": "End time is required for a periodical event."}
                )
            if end_at <= start_at:
                raise serializers.ValidationError(
                    {"end_at": "End time must be after start time."}
                )

        sales_start = attrs.get("sales_start_at", getattr(self.instance, "sales_start_at", None))
        sales_end = attrs.get("sales_end_at", getattr(self.instance, "sales_end_at", None))
        if sales_start and sales_end and sales_end <= sales_start:
            raise serializers.ValidationError(
                {"sales_end_at": "Sales end must be after sales start."}
            )

        program_start = attrs.get(
            "program_start_time",
            getattr(self.instance, "program_start_time", None),
        )
        program_end = attrs.get(
            "program_end_time",
            getattr(self.instance, "program_end_time", None),
        )
        if program_start is None and program_end is not None:
            raise serializers.ValidationError(
                {"program_start_time": "Program start time is required when an end time is set."}
            )
        if program_end is None and program_start is not None:
            raise serializers.ValidationError(
                {"program_end_time": "Program end time is required when a start time is set."}
            )
        if program_start is not None and program_end is not None and program_end <= program_start:
            raise serializers.ValidationError(
                {"program_end_time": "Program end time must be after program start time."}
            )

        tax_mode = attrs.get("tax_mode") or (
            self.instance.tax_mode if self.instance else Event.TaxMode.INHERIT
        )
        if tax_mode == Event.TaxMode.EVENT:
            tax_rate = attrs.get(
                "tax_rate", getattr(self.instance, "tax_rate", None)
            )
            if tax_rate is None:
                raise serializers.ValidationError(
                    {"tax_rate": "Tax percentage is required when event tax is on."}
                )
            if tax_rate <= 0 or tax_rate > 100:
                raise serializers.ValidationError(
                    {"tax_rate": "Tax percentage must be greater than 0 and at most 100."}
                )

            hsn_code = attrs.get(
                "hsn_code", getattr(self.instance, "hsn_code", "")
            )
            hsn_code = str(hsn_code or "").strip()
            if not hsn_code:
                raise serializers.ValidationError(
                    {"hsn_code": "HSN number is required when event tax is on."}
                )
            if not re.fullmatch(r"\d{4,8}", hsn_code):
                raise serializers.ValidationError(
                    {"hsn_code": "HSN number must be 4 to 8 digits."}
                )
            attrs["hsn_code"] = hsn_code

        return attrs

    def validate_status(self, value):
        """Status may be chosen once, at creation; later changes use the actions.

        The New event form creates a live event in one step, so `active` is
        allowed up front. Completed/cancelled are lifecycle transitions and are
        never a valid starting point.
        """
        if self.instance is not None:
            raise serializers.ValidationError(
                "Event status cannot be edited here. Use the activate, complete or "
                "cancel actions instead."
            )
        if value not in {Event.Status.DRAFT, Event.Status.ACTIVE}:
            raise serializers.ValidationError(
                "A new event can only start as draft or active."
            )
        return value

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

from rest_framework import serializers

from .models import Agent


class AgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agent
        fields = [
            "id",
            "code",
            "name",
            "place",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def validate_code(self, value):
        value = value.upper()
        qs = Agent.objects.filter(code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Agent code already exists in this tenant.")
        return value


class AgentStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Agent.Status.choices)

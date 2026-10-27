from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from apps.tenancy.models import TenantMembership

from .models import StaffProfile

User = get_user_model()


class StaffProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "user",
            "staff_code",
            "display_name",
            "phone",
            "email",
            "status",
            "created_by",
            "created_at",
            "updated_at",
            "last_login",
        ]
        read_only_fields = [
            "id",
            "user",
            "status",
            "created_by",
            "created_at",
            "updated_at",
            "last_login",
        ]

    def validate_staff_code(self, value):
        value = value.upper()
        qs = StaffProfile.objects.filter(staff_code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Staff code already exists in this tenant.")
        return value


class StaffCreateSerializer(serializers.Serializer):
    """Creates the login user, pos_staff membership, and StaffProfile atomically."""

    staff_code = serializers.CharField(max_length=32)
    display_name = serializers.CharField(max_length=255)
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True)

    def validate_staff_code(self, value):
        value = value.upper()
        if StaffProfile.objects.filter(staff_code=value).exists():
            raise serializers.ValidationError("Staff code already exists in this tenant.")
        return value

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        tenant = self.context["tenant"]
        actor = self.context["actor"]

        with transaction.atomic():
            user = User.objects.create_user(
                username=validated_data["username"],
                password=validated_data["password"],
                email=validated_data.get("email", ""),
            )
            TenantMembership.objects.create(
                tenant=tenant, user=user, role=TenantMembership.Role.POS_STAFF
            )
            profile = StaffProfile.objects.create(
                tenant=tenant,
                user=user,
                staff_code=validated_data["staff_code"],
                display_name=validated_data["display_name"],
                phone=validated_data.get("phone", ""),
                email=validated_data.get("email", ""),
                created_by=actor,
            )
        return profile

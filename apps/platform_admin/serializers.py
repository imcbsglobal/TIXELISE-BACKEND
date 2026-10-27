from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from apps.tenancy.models import Tenant, TenantMembership

User = get_user_model()


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = [
            "id",
            "code",
            "name",
            "status",
            "timezone",
            "currency",
            "settings",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]


class TenantCreateSerializer(serializers.ModelSerializer):
    """
    Creates the tenant AND its first tenant admin in one transaction —
    no seed script needed to get a loginable tenant.
    """

    admin_username = serializers.CharField(max_length=150, write_only=True)
    admin_password = serializers.CharField(write_only=True)
    admin_email = serializers.EmailField(
        required=False, allow_blank=True, default="", write_only=True
    )

    class Meta:
        model = Tenant
        fields = [
            "code",
            "name",
            "timezone",
            "currency",
            "settings",
            "admin_username",
            "admin_password",
            "admin_email",
        ]

    def validate_admin_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def validate_admin_password(self, value):
        validate_password(value)
        return value

    def to_representation(self, instance):
        # admin_* are write-only inputs; respond with the standard tenant shape
        return TenantSerializer(instance, context=self.context).data

    def create(self, validated_data):
        admin_username = validated_data.pop("admin_username")
        admin_password = validated_data.pop("admin_password")
        admin_email = validated_data.pop("admin_email", "")

        with transaction.atomic():
            tenant = Tenant.objects.create(status=Tenant.Status.ACTIVE, **validated_data)
            admin = User.objects.create_user(
                username=admin_username,
                password=admin_password,
                email=admin_email,
            )
            TenantMembership.objects.create(
                tenant=tenant,
                user=admin,
                role=TenantMembership.Role.TENANT_ADMIN,
            )
        return tenant


class TenantStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "code", "status"]

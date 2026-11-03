from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from apps.tenancy.models import Tenant, TenantMembership

User = get_user_model()


class TenantSerializer(serializers.ModelSerializer):
    admin_central_user_id = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            "id",
            "code",
            "name",
            "status",
            "timezone",
            "currency",
            "phone",
            "settings",
            "admin_central_user_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

    def get_admin_central_user_id(self, obj):
        # Iterate the prefetched relation so the tenant list stays at a fixed
        # number of queries instead of one lookup per row.
        for membership in obj.memberships.all():
            if (
                membership.role == TenantMembership.Role.TENANT_ADMIN
                and membership.central_user_id
            ):
                return membership.central_user_id
        return ""


class TenantCreateSerializer(serializers.ModelSerializer):
    """
    Creates the tenant AND its first tenant admin in one transaction —
    no seed script needed to get a loginable tenant.
    """

    admin_username = serializers.CharField(max_length=150, write_only=True)
    admin_password = serializers.CharField(write_only=True)
    admin_email = serializers.EmailField(write_only=True)
    admin_first_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default="", write_only=True
    )
    admin_last_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default="", write_only=True
    )
    phone = serializers.CharField(max_length=32)

    class Meta:
        model = Tenant
        fields = [
            "code",
            "name",
            "timezone",
            "currency",
            "phone",
            "settings",
            "admin_username",
            "admin_password",
            "admin_email",
            "admin_first_name",
            "admin_last_name",
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
        admin_first_name = validated_data.pop("admin_first_name", "")
        admin_last_name = validated_data.pop("admin_last_name", "")

        with transaction.atomic():
            tenant = Tenant.objects.create(status=Tenant.Status.ACTIVE, **validated_data)
            admin = User.objects.create_user(
                username=admin_username,
                password=admin_password,
                email=admin_email,
                first_name=admin_first_name,
                last_name=admin_last_name,
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

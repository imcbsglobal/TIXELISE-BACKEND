from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from apps.core.context import get_current_tenant_id
# The central user master client lives with the platform admin views; both
# onboarding paths must produce identical rows apart from `user_role`.
from apps.platform_admin.views import _register_central_user
from apps.staff.models import StaffProfile
from apps.tenancy.models import TenantMembership

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
    # The central master requires a valid email and a phone that is unique per
    # client_id, so both are mandatory before an account can be registered.
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=32)
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
                email=validated_data["email"],
            )
            membership = TenantMembership.objects.create(
                tenant=tenant, user=user, role=TenantMembership.Role.POS_STAFF
            )
            profile = StaffProfile.objects.create(
                tenant=tenant,
                user=user,
                staff_code=validated_data["staff_code"],
                display_name=validated_data["display_name"],
                phone=validated_data["phone"],
                email=validated_data["email"],
                created_by=actor,
            )

        # Outside the transaction, so an outage on a third-party host can never
        # roll the staff member back.
        if getattr(settings, "CENTRAL_USER_SYNC_ENABLED", True):
            first_name, _, last_name = validated_data["display_name"].partition(" ")
            registration = _register_central_user(
                tenant,
                membership,
                validated_data["password"],
                # The master only accepts ADMIN or USER; POS staff are USER.
                role="USER",
                phone=validated_data["phone"],
                first_name=first_name.strip(),
                last_name=last_name.strip(),
            )
        else:
            registration = {
                "status": "skipped",
                "central_user_id": "",
                "detail": "Central user sync is disabled.",
            }
        profile.central_user_registration = registration
        return profile

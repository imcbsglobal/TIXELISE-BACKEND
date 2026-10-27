from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.services import sync_platform_superuser_from_external_api
from apps.tenancy.models import Tenant, TenantMembership

User = get_user_model()


def build_tokens(user, tenant, role):
    """Refresh + access tokens carrying tenant claims (MD §10.2)."""
    refresh = RefreshToken.for_user(user)
    if tenant is not None:
        refresh["tenant_id"] = tenant.id
        refresh["tenant_code"] = tenant.code
        refresh["role"] = role
    else:
        refresh["tenant_id"] = None
        refresh["role"] = "platform_admin"
    access = refresh.access_token
    return str(refresh), str(access)


class LoginSerializer(serializers.Serializer):
    tenant_code = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        username = attrs["username"]
        password = attrs["password"]
        tenant_code = (attrs.get("tenant_code") or "").strip()

        if not tenant_code:
            sync_platform_superuser_from_external_api()

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {"detail": "Invalid credentials."}, code="authentication_failed"
            )

        if not user.check_password(password):
            raise serializers.ValidationError(
                {"detail": "Invalid credentials."}, code="authentication_failed"
            )
        if not user.is_active:
            raise serializers.ValidationError(
                {"detail": "This account is disabled."}, code="user_inactive"
            )

        if tenant_code:
            try:
                tenant = Tenant.objects.get(code=tenant_code)
            except Tenant.DoesNotExist:
                raise serializers.ValidationError(
                    {"tenant_code": "Unknown tenant code."},
                    code="tenant_not_found",
                )
            if tenant.status != Tenant.Status.ACTIVE:
                if tenant.status == Tenant.Status.SUSPENDED:
                    from apps.core.exceptions import TenantSuspended

                    raise TenantSuspended()
                from apps.core.exceptions import TenantInactive

                raise TenantInactive()

            try:
                membership = TenantMembership.objects.get(tenant=tenant, user=user)
            except TenantMembership.DoesNotExist:
                raise serializers.ValidationError(
                    {"tenant_code": "No membership in this organization."},
                    code="membership_not_found",
                )
            if membership.status != TenantMembership.Status.ACTIVE:
                from apps.core.exceptions import MembershipInactive

                raise MembershipInactive()

            attrs["tenant"] = tenant
            attrs["role"] = membership.role
        else:
            if not user.is_platform_admin:
                raise serializers.ValidationError(
                    {"tenant_code": "Tenant code is required."},
                    code="tenant_code_required",
                )
            attrs["tenant"] = None
            attrs["role"] = "platform_admin"

        attrs["user"] = user
        return attrs


class MembershipSerializer(serializers.ModelSerializer):
    tenant_code = serializers.CharField(source="tenant.code", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    tenant_status = serializers.CharField(source="tenant.status", read_only=True)

    class Meta:
        model = TenantMembership
        fields = ["id", "tenant", "tenant_code", "tenant_name", "tenant_status", "role", "status"]


class MeSerializer(serializers.ModelSerializer):
    memberships = MembershipSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "is_platform_admin", "memberships"]

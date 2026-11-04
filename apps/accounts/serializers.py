import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.services import (
    scoped_username,
    sync_platform_superuser_from_external_api,
    unscoped_username,
)
from apps.core.exceptions import TixeliseAPIException
from apps.tenancy.models import Tenant, TenantMembership

User = get_user_model()


def _check_license_expired(tenant_code):
    try:
        req = Request(
            "https://activate.imcbs.com/mobileapp/api/project/tixelise/",
            headers={"User-Agent": "Tixelise-Platform"},
        )
        with urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, ValueError, OSError):
        return False

    customers = payload.get("customers") or []
    code = (tenant_code or "").strip().upper()
    for customer in customers:
        client_id = (customer.get("client_id") or "").strip().upper()
        if client_id == code:
            validity = customer.get("license_validity") or {}
            if validity.get("is_expired") is True:
                return True
            if (customer.get("status") or "").strip().lower() != "active":
                return True
            break
    return False


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

        # Staff keys are namespaced with the tenant code; older rows and platform
        # admins still hold a plain username, so both forms are tried.
        lookup_keys = [username]
        if tenant_code:
            lookup_keys.insert(0, scoped_username(tenant_code, username))

        user = None
        for key in lookup_keys:
            user = User.objects.filter(username=key).first()
            if user is not None:
                break
        if user is None:
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
            if _check_license_expired(tenant.code):
                raise TixeliseAPIException(
                    detail="License expired.",
                    code="LICENSE_EXPIRED",
                    status_code=403,
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
    # The stored key carries the tenant prefix; nobody needs to see that.
    username = serializers.SerializerMethodField()

    def get_username(self, obj):
        return unscoped_username(obj.username)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "is_platform_admin", "memberships"]

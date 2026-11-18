import hashlib
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.services import (
    authenticate_central_tenant_user,
    central_user_profile_for_login,
    sync_platform_superuser_from_external_api,
    tenant_license_profile_for_login,
)
from apps.core.exceptions import (
    CentralMasterUnavailable,
    TixeliseAPIException,
)
from apps.staff.models import StaffProfile
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


def _matching_local_user(username):
    matches = list(User.objects.filter(username__iexact=username).order_by("id")[:2])
    if len(matches) > 1:
        raise TixeliseAPIException(
            detail="This username matches multiple local accounts.",
            code="CENTRAL_USER_CONFLICT",
            status_code=409,
        )
    return matches[0] if matches else None


def _local_role_for_central_user(user_role):
    if user_role == "ADMIN":
        return TenantMembership.Role.TENANT_ADMIN
    if user_role == "USER":
        return TenantMembership.Role.POS_STAFF
    raise CentralMasterUnavailable(
        "The central account has an unsupported Tixelise role."
    )


def _provision_central_tenant_user(
    tenant, tenant_code, username, password, license_profile=None
):
    user = _matching_local_user(username)
    membership = (
        TenantMembership.objects.filter(tenant=tenant, user=user).first()
        if tenant and user
        else None
    )

    if user and not user.is_active:
        raise serializers.ValidationError(
            {"detail": "This account is disabled."}, code="user_inactive"
        )
    if membership and membership.status != TenantMembership.Status.ACTIVE:
        from apps.core.exceptions import MembershipInactive

        raise MembershipInactive()

    central_user = None
    if not tenant or not user or not membership:
        central_user = central_user_profile_for_login(tenant_code, username)
        if not user:
            user = _matching_local_user(central_user["username"])
            if user and not user.is_active:
                raise serializers.ValidationError(
                    {"detail": "This account is disabled."}, code="user_inactive"
                )
            if user and tenant:
                membership = TenantMembership.objects.filter(
                    tenant=tenant, user=user
                ).first()
                if membership and membership.status != TenantMembership.Status.ACTIVE:
                    from apps.core.exceptions import MembershipInactive

                    raise MembershipInactive()

    central_role = (
        _local_role_for_central_user(central_user["user_role"])
        if central_user
        else None
    )
    central_user_id = central_user["id"] if central_user else ""

    if tenant is None:
        license_profile = license_profile or tenant_license_profile_for_login(
            tenant_code
        )
        tenant_code = tenant_code.strip()
        if len(tenant_code) > 32:
            raise serializers.ValidationError(
                {"tenant_code": "Tenant code cannot exceed 32 characters."}
            )
        if getattr(settings, "CENTRAL_CURRENCY_SYNC_ENABLED", True):
            from apps.platform_admin.views import (
                _register_tenant_currency,
                _registration_failure,
            )

            registration = _register_tenant_currency(tenant_code, "INR")
            if registration["status"] == "failed":
                raise _registration_failure(registration["detail"])

    with transaction.atomic():
        tenant_created = False
        if tenant is None:
            matches = list(
                Tenant.objects.select_for_update()
                .filter(code__iexact=tenant_code)
                .order_by("id")[:2]
            )
            if len(matches) > 1:
                raise TixeliseAPIException(
                    detail="This tenant code matches multiple local organizations.",
                    code="TENANT_CODE_CONFLICT",
                    status_code=409,
                )
            if matches:
                tenant = matches[0]
            else:
                tenant, tenant_created = Tenant.objects.get_or_create(
                    code=tenant_code,
                    defaults={
                        "name": license_profile["name"],
                        "status": Tenant.Status.ACTIVE,
                        "timezone": "UTC",
                        "currency": "INR",
                    },
                )

        if tenant.status != Tenant.Status.ACTIVE:
            if tenant.status == Tenant.Status.SUSPENDED:
                from apps.core.exceptions import TenantSuspended

                raise TenantSuspended()
            from apps.core.exceptions import TenantInactive

            raise TenantInactive()

        user_created = False
        if not user:
            user, user_created = User.objects.get_or_create(
                username=central_user["username"],
                defaults={
                    "email": central_user["email"],
                    "first_name": central_user["first_name"],
                    "last_name": central_user["last_name"],
                },
            )
            if user_created:
                user.set_password(password)
                user.save(update_fields=["password"])

        if not user.is_active:
            raise serializers.ValidationError(
                {"detail": "This account is disabled."}, code="user_inactive"
            )

        membership_created = False
        if membership is None:
            membership, membership_created = TenantMembership.objects.get_or_create(
                tenant=tenant,
                user=user,
                defaults={
                    "role": central_role,
                    "status": TenantMembership.Status.ACTIVE,
                    "central_user_id": central_user_id,
                },
            )
        if membership.status != TenantMembership.Status.ACTIVE:
            from apps.core.exceptions import MembershipInactive

            raise MembershipInactive()

        if central_user_id:
            if membership.central_user_id and membership.central_user_id != central_user_id:
                raise TixeliseAPIException(
                    detail="This local membership is linked to a different central account.",
                    code="CENTRAL_USER_CONFLICT",
                    status_code=409,
                )
            if not membership.central_user_id:
                membership.central_user_id = central_user_id
                membership.save(update_fields=["central_user_id", "updated_at"])

        if central_user and central_role == TenantMembership.Role.POS_STAFF:
            display_name = " ".join(
                part
                for part in (central_user["first_name"], central_user["last_name"])
                if part
            ) or central_user["username"]
            staff_code = "C" + hashlib.sha256(
                f"{tenant.code}:{central_user_id}".encode("utf-8")
            ).hexdigest()[:20].upper()
            StaffProfile.objects.get_or_create(
                tenant=tenant,
                user=user,
                defaults={
                    "staff_code": staff_code,
                    "display_name": display_name,
                    "phone": central_user["phone_number"],
                    "email": central_user["email"],
                },
            )

    return tenant, user, membership, (
        tenant_created or user_created or membership_created
    )


class LoginSerializer(serializers.Serializer):
    tenant_code = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        username = attrs["username"]
        password = attrs["password"]
        tenant_code = (attrs.get("tenant_code") or "").strip()

        if tenant_code:
            tenants = list(
                Tenant.objects.filter(code__iexact=tenant_code).order_by("id")[:2]
            )
            if len(tenants) > 1:
                raise TixeliseAPIException(
                    detail="This tenant code matches multiple local organizations.",
                    code="TENANT_CODE_CONFLICT",
                    status_code=409,
                )
            tenant = tenants[0] if tenants else None

            if tenant and _check_license_expired(tenant.code):
                raise TixeliseAPIException(
                    detail="License expired.",
                    code="LICENSE_EXPIRED",
                    status_code=403,
                )
            if tenant and tenant.status != Tenant.Status.ACTIVE:
                if tenant.status == Tenant.Status.SUSPENDED:
                    from apps.core.exceptions import TenantSuspended

                    raise TenantSuspended()
                from apps.core.exceptions import TenantInactive

                raise TenantInactive()

            if not authenticate_central_tenant_user(tenant_code, username, password):
                raise serializers.ValidationError(
                    {"detail": "Invalid credentials."}, code="authentication_failed"
                )

            license_profile = (
                tenant_license_profile_for_login(tenant_code) if tenant is None else None
            )
            tenant, user, membership, provisioned = _provision_central_tenant_user(
                tenant,
                tenant_code,
                username,
                password,
                license_profile=license_profile,
            )
            attrs["tenant"] = tenant
            attrs["role"] = membership.role
            attrs["central_user_provisioned"] = provisioned
        else:
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

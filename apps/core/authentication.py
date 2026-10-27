from rest_framework_simplejwt.authentication import JWTAuthentication

from .context import set_tenant_context
from .exceptions import (
    TenantSuspended,
    TenantInactive,
    MembershipInactive,
    InvalidToken as CoreInvalidToken,
)


class TenantJWTAuthentication(JWTAuthentication):
    """
    Standard JWT authentication that also restores the tenant context from
    verified token claims and sets it in thread-local storage so
    TenantManager can auto-scope every queryset.

    Active tenant/membership/role state is re-checked on every request so a
    signed token alone can never preserve revoked access indefinitely.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, validated_token = result
        claims = validated_token.payload
        tenant_id = claims.get("tenant_id")
        role = claims.get("role")
        set_tenant_context(tenant_id, role=role, user_id=user.id)

        if tenant_id is not None:
            from apps.tenancy.models import Tenant, TenantMembership

            try:
                tenant = Tenant.objects.get(pk=tenant_id)
            except Tenant.DoesNotExist:
                raise CoreInvalidToken("Tenant no longer exists.")
            if tenant.status == Tenant.Status.SUSPENDED:
                raise TenantSuspended()
            if tenant.status != Tenant.Status.ACTIVE:
                raise TenantInactive()

            try:
                membership = TenantMembership.objects.get(
                    tenant_id=tenant_id, user_id=user.id
                )
            except TenantMembership.DoesNotExist:
                raise MembershipInactive("Membership no longer exists.")
            if membership.status != TenantMembership.Status.ACTIVE:
                raise MembershipInactive()
            if membership.role != role:
                raise CoreInvalidToken("Token role no longer matches membership.")

        return user, validated_token

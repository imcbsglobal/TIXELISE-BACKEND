from rest_framework.permissions import BasePermission

from .context import get_current_role, get_current_tenant_id
from .exceptions import (
    NotPlatformAdmin,
    NotTenantAdmin,
    NotPOSSStaff,
    TenantSuspended,
    MembershipInactive,
)


class TenantScopedPermission(BasePermission):
    """
    Base for all tenant-scoped endpoints. Requires an authenticated identity
    carrying a valid, active tenant membership.
    """

    required_role = None

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        role = get_current_role()
        tenant_id = get_current_tenant_id()
        if tenant_id is None or role is None:
            return False

        from apps.tenancy.models import Tenant, TenantMembership

        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            return False
        if tenant.status == Tenant.Status.SUSPENDED:
            raise TenantSuspended()
        if tenant.status != Tenant.Status.ACTIVE:
            return False

        try:
            membership = TenantMembership.objects.get(tenant=tenant, user=user)
        except TenantMembership.DoesNotExist:
            return False
        if membership.status != TenantMembership.Status.ACTIVE:
            raise MembershipInactive()

        if self.required_role is not None and membership.role != self.required_role:
            return False

        request.membership = membership
        request.tenant_obj = tenant
        return True


class IsTenantAdmin(TenantScopedPermission):
    required_role = "tenant_admin"


class IsPOSSStaff(TenantScopedPermission):
    required_role = "pos_staff"


class IsTenantAdminOrPOSSStaff(TenantScopedPermission):
    required_role = None  # any active tenant role

    def has_permission(self, request, view):
        role = get_current_role()
        if role not in ("tenant_admin", "pos_staff"):
            return False
        return super().has_permission(request, view)


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if not user.is_platform_admin or get_current_tenant_id() is not None:
            raise NotPlatformAdmin()
        return True

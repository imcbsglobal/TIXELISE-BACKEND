from django.db import models

from .context import get_current_tenant_id


class TenantManager(models.Manager):
    """Auto-scopes querysets to the authenticated tenant context."""

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = get_current_tenant_id()
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        return qs


class TenantOwnedModel(models.Model):
    """Base for every tenant-owned record (MD §5.3)."""

    tenant = models.ForeignKey(
        "tenancy.Tenant", on_delete=models.PROTECT, related_name="%(class)ss"
    )

    objects = TenantManager()

    class Meta:
        abstract = True

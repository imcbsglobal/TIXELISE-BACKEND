from django.conf import settings
from django.db import models


class Tenant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        INACTIVE = "inactive", "Inactive"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    timezone = models.CharField(max_length=64, default="UTC")
    currency = models.CharField(max_length=8, default="INR")
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenancy_tenant_tixelise"
        verbose_name = "tenant"
        verbose_name_plural = "tenants"

    def __str__(self):
        return f"{self.code} ({self.name})"


class TenantMembership(models.Model):
    class Role(models.TextChoices):
        TENANT_ADMIN = "tenant_admin", "Tenant Admin"
        POS_STAFF = "pos_staff", "POS Staff"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=32, choices=Role.choices)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenancy_tenantmembership_tixelise"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user"], name="uniq_tenant_membership"
            )
        ]

    def __str__(self):
        return f"{self.user} @ {self.tenant.code} [{self.role}]"

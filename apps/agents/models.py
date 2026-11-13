from django.db import models

from apps.core.models import TenantOwnedModel


class Agent(TenantOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    place = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_agents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tixelise_agents_agent"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="uniq_tenant_agent_code"
            )
        ]
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"

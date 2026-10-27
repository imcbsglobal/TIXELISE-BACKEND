from django.db import models

from apps.core.models import TenantOwnedModel


class TicketCategory(TenantOwnedModel):
    """Tenant-level reusable category (Adult, Child, VIP...)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_ticketcategory_tixelise"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="uniq_tenant_category_code"
            )
        ]
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class EventPrice(TenantOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="eventprices"
    )
    category = models.ForeignKey(
        TicketCategory, on_delete=models.PROTECT, related_name="eventprices"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default="INR")
    effective_from = models.DateTimeField(null=True, blank=True)
    effective_to = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_eventprice_tixelise"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "event", "category"], name="uniq_tenant_event_category_price"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name="price_amount_non_negative"
            ),
        ]

    def is_currently_effective(self, when=None):
        from django.utils import timezone

        when = when or timezone.now()
        if self.effective_from and when < self.effective_from:
            return False
        if self.effective_to and when > self.effective_to:
            return False
        return True


class TicketTemplate(TenantOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=100)
    config = models.JSONField(default=dict, blank=True)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_tickettemplate_tixelise"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} v{self.version}"

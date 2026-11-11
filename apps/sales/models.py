from django.db import models

from apps.core.models import TenantOwnedModel


class Sale(TenantOwnedModel):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        VOIDED = "voided", "Voided"
        REFUNDED = "refunded", "Refunded"

    class Source(models.TextChoices):
        POS = "pos", "POS"
        MANUAL = "manual", "Manual"

    sale_reference = models.CharField(max_length=64)
    event = models.ForeignKey(
        "events.Event", on_delete=models.PROTECT, related_name="sales"
    )
    staff = models.ForeignKey(
        "staff.StaffProfile", on_delete=models.PROTECT, related_name="sales"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.COMPLETED, db_index=True
    )
    source = models.CharField(
        max_length=16, choices=Source.choices, default=Source.POS, db_index=True
    )
    gross_total = models.DecimalField(max_digits=12, decimal_places=2)
    refund_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default="INR")
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_sales"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tixelise_sales_sale"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "sale_reference"], name="uniq_tenant_sale_reference"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return self.sale_reference


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    category = models.ForeignKey(
        "catalog.TicketCategory", on_delete=models.PROTECT, related_name="sale_items"
    )
    quantity = models.PositiveIntegerField()
    unit_price_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "tixelise_sales_saleitem"
        ordering = ["id"]


class IdempotencyRecord(TenantOwnedModel):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"

    actor = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="idempotency_records"
    )
    idempotency_key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    sale = models.ForeignKey(
        Sale, null=True, blank=True, on_delete=models.SET_NULL, related_name="idempotency_records"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.COMPLETED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "tixelise_sales_idempotencyrecord"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "actor", "idempotency_key"],
                name="uniq_tenant_actor_idempotency_key",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "actor", "idempotency_key"]),
        ]

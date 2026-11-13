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
    agent = models.ForeignKey(
        "agents.Agent",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sales",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.COMPLETED, db_index=True
    )
    source = models.CharField(
        max_length=16, choices=Source.choices, default=Source.POS, db_index=True
    )
    gross_total = models.DecimalField(max_digits=12, decimal_places=2)
    refund_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Tax collected on top of (or already inside) gross_total. Zero on every
    # sale created before tax was enabled, which keeps old totals identical.
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
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
    # Taxable amount of this line. With tax off it is unit_price * quantity.
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    # Frozen tax, exactly like unit_price_snapshot: editing the rate later must
    # never rewrite what a past sale was charged.
    tax_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_code = models.CharField(max_length=20, blank=True, default="")
    tax_name = models.CharField(max_length=100, blank=True, default="")
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    hsn_code = models.CharField(max_length=20, blank=True, default="")

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

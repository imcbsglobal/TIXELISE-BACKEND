from decimal import Decimal

from django.db import models

from apps.core.models import TenantOwnedModel


class TaxSetting(TenantOwnedModel):
    """The tax that applies to this tenant's ticket sales.

    One row per tenant, holding a *copy* of one record from the central tax
    master — never a live reference. The master is a third-party host, so a sale
    must never depend on it being reachable, and editing a rate upstream must
    never rewrite history: every sale keeps its own snapshot on the sale line.

    ``enabled`` is the custom on/off switch. With it off (the default) nothing
    changes anywhere: totals equal the price the administrator configured.
    """

    class Kind(models.TextChoices):
        INDIA = "india", "India (GST)"
        OTHER = "other", "Other countries"

    enabled = models.BooleanField(default=False)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.INDIA)
    # Primary key of the record in the central tax master.
    tax_master_id = models.CharField(max_length=32, blank=True, default="")
    code = models.CharField(max_length=20, blank=True, default="")
    name = models.CharField(max_length=100, blank=True, default="")
    # The single rate Tixelise charges: `gst` for India, `tax` for other kinds.
    rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    # India's components are shown on the printed ticket only; they are never
    # summed to build the rate (real rows on the master disagree with each other).
    cgst = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    sgst = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    igst = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # False (the default) charges price + tax. True treats the configured price
    # as tax-inclusive and reports the tax it already contains.
    prices_include_tax = models.BooleanField(default=False)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tixelise_taxation_taxsetting"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="uniq_tenant_tax_setting")
        ]

    def __str__(self):
        state = "on" if self.enabled else "off"
        return f"{self.tenant_id}: {self.code or 'no tax'} {self.rate}% [{state}]"

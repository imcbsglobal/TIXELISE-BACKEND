from datetime import date, datetime

from django.db import models

from apps.core.models import TenantOwnedModel


class Event(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class EventType(models.TextChoices):
        REGULAR = "regular", "Regular"
        PERIODICAL = "periodical", "Periodical"

    class TaxMode(models.TextChoices):
        INHERIT = "inherit", "Use company tax setting"
        EVENT = "event", "Charge tax for this event"
        DISABLED = "disabled", "No tax for this event"

    # Existing rows keep the old behaviour; new events opt in explicitly.
    event_type = models.CharField(
        max_length=16,
        choices=EventType.choices,
        default=EventType.PERIODICAL,
        db_index=True,
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    venue = models.CharField(max_length=255, blank=True, default="")
    address = models.CharField(max_length=500, blank=True, default="")
    start_at = models.DateTimeField()
    # A regular event never ends, so `end_at` is the only nullable boundary.
    end_at = models.DateTimeField(null=True, blank=True)
    sales_start_at = models.DateTimeField(null=True, blank=True)
    sales_end_at = models.DateTimeField(null=True, blank=True)
    # The daily program window: time of day only, independent of the event's
    # date range. Both are set together and only describe the programme; they
    # do not gate POS sales (that is what the sales window above is for).
    program_start_time = models.TimeField(null=True, blank=True)
    program_end_time = models.TimeField(null=True, blank=True)
    # Tax for ticket sales. "inherit" keeps the company-wide TaxSetting; the
    # other modes let one event charge its own rate (or no tax at all) without
    # touching the company default for every other event.
    tax_mode = models.CharField(
        max_length=16, choices=TaxMode.choices, default=TaxMode.INHERIT, db_index=True
    )
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    hsn_code = models.CharField(max_length=20, blank=True, default="")
    prices_include_tax = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_events"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tixelise_events_event"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="uniq_tenant_event_code"
            ),
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="event_end_after_start",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(program_start_time__isnull=True)
                    | models.Q(program_end_time__isnull=True)
                    | models.Q(program_end_time__gt=models.F("program_start_time"))
                ),
                name="event_program_end_after_start",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(tax_rate__isnull=True)
                    | models.Q(tax_rate__gte=0, tax_rate__lte=100)
                ),
                name="event_tax_rate_range",
            ),
        ]
        ordering = ["-start_at"]

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def is_regular(self):
        return self.event_type == self.EventType.REGULAR

    @property
    def program_duration_minutes(self):
        """Minutes between the program start and end, or None when unset."""
        if self.program_start_time is None or self.program_end_time is None:
            return None
        start = datetime.combine(date.min, self.program_start_time)
        end = datetime.combine(date.min, self.program_end_time)
        return int((end - start).total_seconds() // 60)

    def is_within_sales_window(self, when=None):
        from django.utils import timezone

        when = when or timezone.now()
        if self.sales_start_at and when < self.sales_start_at:
            return False
        if self.sales_end_at and when > self.sales_end_at:
            return False
        return True

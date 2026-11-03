from django.db import models

from apps.core.models import TenantOwnedModel


class Event(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    venue = models.CharField(max_length=255, blank=True, default="")
    address = models.CharField(max_length=500, blank=True, default="")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    sales_start_at = models.DateTimeField(null=True, blank=True)
    sales_end_at = models.DateTimeField(null=True, blank=True)
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
        ]
        ordering = ["-start_at"]

    def __str__(self):
        return f"{self.code} — {self.name}"

    def is_within_sales_window(self, when=None):
        from django.utils import timezone

        when = when or timezone.now()
        if self.sales_start_at and when < self.sales_start_at:
            return False
        if self.sales_end_at and when > self.sales_end_at:
            return False
        return True

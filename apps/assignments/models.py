from django.db import models

from apps.core.models import TenantOwnedModel


class StaffEventAssignment(TenantOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    staff = models.ForeignKey(
        "staff.StaffProfile", on_delete=models.CASCADE, related_name="assignments"
    )
    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="assignments"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    allowed_categories = models.ManyToManyField(
        "catalog.TicketCategory",
        blank=True,
        related_name="assignments",
        db_table="tixelise_assignments_staffeventassignment_allowed_categories",
    )
    restrict_categories = models.BooleanField(
        default=False,
        help_text="If true, only allowed_categories may be sold by this staff member.",
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_assignments"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tixelise_assignments_staffeventassignment"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "staff", "event"], name="uniq_tenant_staff_event"
            )
        ]
        ordering = ["-created_at"]

    def is_usable_at(self, when=None):
        from django.utils import timezone

        if self.status != self.Status.ACTIVE:
            return False
        when = when or timezone.now()
        if self.valid_from and when < self.valid_from:
            return False
        if self.valid_until and when > self.valid_until:
            return False
        return True

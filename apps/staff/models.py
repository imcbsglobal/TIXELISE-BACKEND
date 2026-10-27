from django.db import models

from apps.core.models import TenantOwnedModel


class StaffProfile(TenantOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    user = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="staff_profiles"
    )
    staff_code = models.CharField(max_length=32)
    display_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_staff_profiles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "staff_staffprofile_tixelise"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "staff_code"], name="uniq_tenant_staff_code"
            ),
            models.UniqueConstraint(
                fields=["tenant", "user"], name="uniq_tenant_staff_user"
            ),
        ]
        ordering = ["staff_code"]

    def __str__(self):
        return f"{self.staff_code} — {self.display_name}"

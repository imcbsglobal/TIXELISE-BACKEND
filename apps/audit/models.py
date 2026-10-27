from django.db import models


class AuditLog(models.Model):
    """
    Append-only audit trail (MD §7.11). Never logs passwords or tokens.
    tenant is nullable only for explicitly platform-wide events.
    """

    tenant = models.ForeignKey(
        "tenancy.Tenant", null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    actor = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events"
    )
    actor_label = models.CharField(max_length=255, blank=True, default="")
    action = models.CharField(max_length=100, db_index=True)
    target_type = models.CharField(max_length=100, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    correlation_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_auditlog_tixelise"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M:%S}"

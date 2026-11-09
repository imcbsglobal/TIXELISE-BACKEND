from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import AuditLog

BATCH_SIZE = 500


def prune_audit_logs(days=None, *, dry_run=False):
    """Delete audit rows older than the retention window.

    Only ``AuditLog`` rows are touched; nothing else in the database is
    affected. Returns the number of rows deleted (or that would be deleted
    when ``dry_run`` is true). Small batches keep locks short.
    """
    window = settings.AUDIT_LOG_RETENTION_DAYS if days is None else int(days)
    if window < 1:
        raise ValueError("retention days must be at least 1")

    cutoff = timezone.now() - timedelta(days=window)
    queryset = AuditLog.objects.filter(created_at__lt=cutoff)

    if dry_run:
        return queryset.count()

    total = 0
    while True:
        ids = list(queryset.values_list("pk", flat=True)[:BATCH_SIZE])
        if not ids:
            break
        deleted, _ = AuditLog.objects.filter(pk__in=ids).delete()
        total += deleted
        if len(ids) < BATCH_SIZE:
            break
    return total

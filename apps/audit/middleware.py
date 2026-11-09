from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from .retention import prune_audit_logs

_last_run_date = None


def maybe_prune():
    """Prune at most once per calendar day per process; never raise."""
    global _last_run_date
    today = timezone.localdate()
    if _last_run_date == today:
        return
    _last_run_date = today
    try:
        prune_audit_logs()
    except Exception:
        # Retention must never break a request.
        pass


class AuditRetentionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        maybe_prune()

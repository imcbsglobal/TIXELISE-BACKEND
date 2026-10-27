from apps.core.context import get_correlation_id

from .models import AuditLog

_SENSITIVE_KEYS = {
    "password",
    "token",
    "access",
    "refresh",
    "secret",
    "password_hash",
}


def _scrub(metadata):
    if not isinstance(metadata, dict):
        return {}
    return {k: v for k, v in metadata.items() if k.lower() not in _SENSITIVE_KEYS}


def record_audit(*, action, actor=None, tenant=None, target_type="", target_id="", metadata=None):
    """Best-effort audit write; never raises into the request path."""
    try:
        return AuditLog.objects.create(
            tenant=tenant,
            actor=actor,
            actor_label=getattr(actor, "username", "") or "",
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id not in (None, "") else "",
            correlation_id=get_correlation_id() or "",
            metadata=_scrub(metadata or {}),
        )
    except Exception:
        return None

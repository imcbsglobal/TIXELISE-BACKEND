"""Developer tools for a tenant: what exists, and a deliberate hard delete.

Only a tenant admin can use these; the tenant comes from the JWT, never from the
request body, so one organization can never wipe another's data.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.exceptions import ValidationError
from apps.core.permissions import IsTenantAdmin

from .purge import SCOPES, purge, summarize


def _summary(tenant):
    return {**summarize(tenant), "tenant_code": tenant.code, "tenant_name": tenant.name}


class DeveloperDataSummaryView(APIView):
    """Counts of what the delete tool would remove, for the current tenant only."""

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        return Response(_summary(request.tenant_obj))


class DeveloperPurgeView(APIView):
    """Permanently delete the ticked kinds of data for the current tenant.

    The typed confirmation is checked here, not only in the browser: an
    accidental or replayed call with the wrong tenant code deletes nothing.
    """

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def post(self, request):
        tenant = request.tenant_obj
        data = request.data or {}
        if not isinstance(data, dict):
            raise ValidationError("Body must be a JSON object.")

        unknown = sorted(set(data) - {"scopes", "confirm"})
        if unknown:
            raise ValidationError(f"Unknown fields: {', '.join(unknown)}")

        scopes = data.get("scopes")
        if not isinstance(scopes, list):
            raise ValidationError({"scopes": "Send a list of what to delete."})
        scopes = [str(scope).strip().lower() for scope in scopes]
        invalid = sorted(set(scopes) - set(SCOPES))
        if invalid:
            raise ValidationError(
                {"scopes": f"Unknown scope(s): {', '.join(invalid)}. "
                           f"Choose from: {', '.join(SCOPES)}."}
            )
        if not scopes:
            raise ValidationError({"scopes": "Select at least one kind of data."})

        confirm = str(data.get("confirm") or "").strip()
        if not tenant.code or confirm.casefold() != tenant.code.casefold():
            raise ValidationError(
                {"confirm": f"Type {tenant.code} to confirm the deletion."}
            )

        result = purge(tenant, scopes)

        record_audit(
            actor=request.user,
            tenant=tenant,
            action="developer.data_purged",
            target_type="tenant",
            target_id=tenant.code,
            metadata={
                "scopes": scopes,
                "implied": result["implied"],
                "deleted": result["deleted"],
            },
        )

        return Response({**result, "summary": _summary(tenant)})

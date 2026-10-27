from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import IsTenantAdmin

from .models import AuditLog


class AuditLogListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get_queryset(self):
        qs = AuditLog.objects.exclude(tenant=None)
        params = self.request.query_params
        if params.get("action"):
            qs = qs.filter(action=params["action"])
        if params.get("actor"):
            qs = qs.filter(actor_id=params["actor"])
        if params.get("target_type"):
            qs = qs.filter(target_type=params["target_type"])
        return qs.select_related("actor", "tenant")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        data = [
            {
                "id": log.id,
                "action": log.action,
                "actor": log.actor_label,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "metadata": log.metadata,
                "correlation_id": log.correlation_id,
                "created_at": log.created_at.isoformat(),
            }
            for log in page or []
        ]
        return self.get_paginated_response(data)

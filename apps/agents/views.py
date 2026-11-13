from django.db.models import ProtectedError, Q
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.context import get_current_tenant_id
from apps.core.exceptions import Conflict, NotFound
from apps.core.permissions import IsTenantAdmin

from .models import Agent
from .serializers import AgentSerializer, AgentStatusSerializer


class AgentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = AgentSerializer

    def get_queryset(self):
        qs = Agent.objects.all()
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        search = (params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(code__icontains=search)
                | Q(name__icontains=search)
                | Q(place__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        agent = serializer.save(
            tenant_id=get_current_tenant_id(), created_by=self.request.user
        )
        record_audit(
            actor=self.request.user,
            tenant=agent.tenant,
            action="agent.created",
            target_type="agent",
            target_id=agent.id,
            metadata={"code": agent.code, "place": agent.place},
        )
        return agent


class AgentDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = AgentSerializer

    def get_queryset(self):
        return Agent.objects.all()

    def perform_update(self, serializer):
        agent = serializer.save()
        record_audit(
            actor=self.request.user,
            tenant=agent.tenant,
            action="agent.updated",
            target_type="agent",
            target_id=agent.id,
            metadata={"code": agent.code, "place": agent.place},
        )

    def delete(self, request, pk):
        try:
            agent = Agent.objects.get(pk=pk)
        except Agent.DoesNotExist:
            raise NotFound("Agent not found.")

        code = agent.code
        tenant = agent.tenant
        agent_id = agent.id
        if agent.sales.exists():
            raise Conflict(
                f"{code} already has ticket sales, so it cannot be permanently "
                "deleted. Deactivate it instead to keep the sales history."
            )

        try:
            agent.delete()
        except ProtectedError:
            raise Conflict(
                f"{code} already has ticket sales, so it cannot be permanently "
                "deleted. Deactivate it instead to keep the sales history."
            )

        record_audit(
            actor=request.user,
            tenant=tenant,
            action="agent.deleted",
            target_type="agent",
            target_id=agent_id,
            metadata={"code": code},
        )
        return Response({"deleted": True, "code": code})


class AgentStatusView(APIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def post(self, request, pk):
        try:
            agent = Agent.objects.get(pk=pk)
        except Agent.DoesNotExist:
            raise NotFound("Agent not found.")

        serializer = AgentStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        status = serializer.validated_data["status"]

        agent.status = status
        agent.save(update_fields=["status", "updated_at"])
        record_audit(
            actor=request.user,
            tenant=agent.tenant,
            action=f"agent.{status}",
            target_type="agent",
            target_id=agent.id,
            metadata={"code": agent.code},
        )
        return Response(AgentSerializer(agent).data)

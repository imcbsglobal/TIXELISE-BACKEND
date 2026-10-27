from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.context import get_current_tenant_id
from apps.core.exceptions import NotFound
from apps.core.permissions import IsTenantAdmin

from .models import StaffEventAssignment
from .serializers import AssignmentSerializer


class AssignmentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        qs = StaffEventAssignment.objects.select_related("staff", "event")
        params = self.request.query_params
        if params.get("staff"):
            qs = qs.filter(staff_id=params["staff"])
        if params.get("event"):
            qs = qs.filter(event_id=params["event"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant_id"] = get_current_tenant_id()
        return ctx

    def perform_create(self, serializer):
        obj = serializer.save(
            tenant_id=get_current_tenant_id(), created_by=self.request.user
        )
        record_audit(
            actor=self.request.user,
            tenant=obj.tenant,
            action="assignment.created",
            target_type="staff_event_assignment",
            target_id=obj.id,
            metadata={"staff": obj.staff.staff_code, "event": obj.event.code},
        )


class AssignmentDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        return StaffEventAssignment.objects.select_related("staff", "event")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant_id"] = get_current_tenant_id()
        return ctx

    def perform_update(self, serializer):
        previous_staff_code = serializer.instance.staff.staff_code
        assignment = serializer.save()
        record_audit(
            actor=self.request.user,
            tenant=assignment.tenant,
            action="assignment.updated",
            target_type="staff_event_assignment",
            target_id=assignment.id,
            metadata={
                "previous_staff": previous_staff_code,
                "staff": assignment.staff.staff_code,
                "event": assignment.event.code,
            },
        )


class AssignmentRevokeView(APIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def post(self, request, pk):
        try:
            assignment = StaffEventAssignment.objects.get(pk=pk)
        except StaffEventAssignment.DoesNotExist:
            raise NotFound("Assignment not found.")

        if assignment.status == StaffEventAssignment.Status.REVOKED:
            return Response(
                {"error": {"code": "ALREADY_REVOKED", "message": "Assignment already revoked."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        assignment.status = StaffEventAssignment.Status.REVOKED
        assignment.save(update_fields=["status", "updated_at"])
        record_audit(
            actor=request.user,
            tenant=assignment.tenant,
            action="assignment.revoked",
            target_type="staff_event_assignment",
            target_id=assignment.id,
            metadata={"staff": assignment.staff.staff_code, "event": assignment.event.code},
        )
        return Response({"id": assignment.id, "status": assignment.status})

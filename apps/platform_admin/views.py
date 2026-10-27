from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.exceptions import NotFound, TixeliseAPIException
from apps.core.permissions import IsPlatformAdmin
from apps.tenancy.models import Tenant

from .serializers import TenantCreateSerializer, TenantSerializer


class TenantListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    queryset = Tenant.objects.all().order_by("code")
    serializer_class = TenantSerializer

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TenantCreateSerializer
        return TenantSerializer

    def perform_create(self, serializer):
        admin_username = serializer.validated_data.get("admin_username")
        tenant = serializer.save()
        record_audit(
            actor=self.request.user,
            tenant=None,
            action="platform.tenant.created",
            target_type="tenant",
            target_id=tenant.id,
            metadata={"code": tenant.code, "name": tenant.name, "admin": admin_username},
        )


class TenantDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = TenantSerializer

    def get_queryset(self):
        return Tenant.objects.all()

    def perform_update(self, serializer):
        tenant = serializer.save()
        record_audit(
            actor=self.request.user,
            tenant=None,
            action="platform.tenant.updated",
            target_type="tenant",
            target_id=tenant.id,
            metadata={"code": tenant.code},
        )


class TenantStatusActionView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    allowed_transition = None
    audit_action = None

    def post(self, request, pk):
        try:
            tenant = Tenant.objects.get(pk=pk)
        except Tenant.DoesNotExist:
            raise NotFound("Tenant not found.")

        if tenant.status == self.allowed_transition:
            raise TixeliseAPIException(
                detail=f"Tenant is already {self.allowed_transition}.",
                code="ALREADY_IN_STATE",
            )

        tenant.status = self.allowed_transition
        tenant.save(update_fields=["status", "updated_at"])
        record_audit(
            actor=request.user,
            tenant=None,
            action=self.audit_action,
            target_type="tenant",
            target_id=tenant.id,
            metadata={"code": tenant.code, "status": tenant.status},
        )
        return Response(
            {"id": tenant.id, "code": tenant.code, "status": tenant.status},
            status=status.HTTP_200_OK,
        )


class TenantActivateView(TenantStatusActionView):
    allowed_transition = Tenant.Status.ACTIVE
    audit_action = "platform.tenant.activated"


class TenantSuspendView(TenantStatusActionView):
    allowed_transition = Tenant.Status.SUSPENDED
    audit_action = "platform.tenant.suspended"


class TenantDeactivateView(TenantStatusActionView):
    allowed_transition = Tenant.Status.INACTIVE
    audit_action = "platform.tenant.deactivated"

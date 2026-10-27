from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.context import get_current_tenant_id
from apps.core.exceptions import NotFound
from apps.core.permissions import IsTenantAdmin
from apps.tenancy.models import TenantMembership

from .models import StaffProfile
from .serializers import StaffCreateSerializer, StaffProfileSerializer


class StaffListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return StaffCreateSerializer
        return StaffProfileSerializer

    def get_queryset(self):
        return StaffProfile.objects.select_related("user")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant_id"] = get_current_tenant_id()
        ctx["tenant"] = self.request.tenant_obj
        ctx["actor"] = self.request.user
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        record_audit(
            actor=request.user,
            tenant=profile.tenant,
            action="staff.created",
            target_type="staff_profile",
            target_id=profile.id,
            metadata={"staff_code": profile.staff_code, "username": profile.user.username},
        )
        return Response(
            StaffProfileSerializer(profile).data, status=status.HTTP_201_CREATED
        )


class StaffDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    serializer_class = StaffProfileSerializer

    def get_queryset(self):
        return StaffProfile.objects.select_related("user")

    def perform_update(self, serializer):
        obj = serializer.save()
        record_audit(
            actor=self.request.user,
            tenant=obj.tenant,
            action="staff.updated",
            target_type="staff_profile",
            target_id=obj.id,
            metadata={"staff_code": obj.staff_code},
        )


class StaffDeactivateView(APIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def post(self, request, pk):
        try:
            profile = StaffProfile.objects.get(pk=pk)
        except StaffProfile.DoesNotExist:
            raise NotFound("Staff not found.")

        profile.status = StaffProfile.Status.INACTIVE
        profile.save(update_fields=["status", "updated_at"])
        TenantMembership.objects.filter(tenant=profile.tenant, user=profile.user).update(
            status=TenantMembership.Status.INACTIVE
        )
        record_audit(
            actor=request.user,
            tenant=profile.tenant,
            action="staff.deactivated",
            target_type="staff_profile",
            target_id=profile.id,
            metadata={"staff_code": profile.staff_code},
        )
        return Response({"id": profile.id, "status": profile.status})


class StaffResetPasswordView(APIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def post(self, request, pk):
        from django.contrib.auth.password_validation import validate_password

        try:
            profile = StaffProfile.objects.get(pk=pk)
        except StaffProfile.DoesNotExist:
            raise NotFound("Staff not found.")

        password = request.data.get("password")
        if not password:
            return Response(
                {"error": {"code": "VALIDATION_ERROR", "message": "password is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        validate_password(password)
        profile.user.set_password(password)
        profile.user.save(update_fields=["password"])
        record_audit(
            actor=request.user,
            tenant=profile.tenant,
            action="staff.password_reset",
            target_type="staff_profile",
            target_id=profile.id,
        )
        return Response({"detail": "Password updated."})

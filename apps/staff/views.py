from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import unscoped_username
from apps.audit.services import record_audit
from apps.core.context import get_current_tenant_id
from apps.core.exceptions import Conflict, NotFound
from apps.core.permissions import IsTenantAdmin
from apps.platform_admin.views import _delete_central_users
from apps.sales.models import Sale
from apps.tenancy.models import TenantMembership
from apps.ticketing.models import Ticket

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
        registration = getattr(profile, "central_user_registration", None)
        record_audit(
            actor=request.user,
            tenant=profile.tenant,
            action="staff.created",
            target_type="staff_profile",
            target_id=profile.id,
            metadata={
                "staff_code": profile.staff_code,
                "username": unscoped_username(profile.user.username),
                "central_user": (registration or {}).get("status", ""),
            },
        )
        payload = StaffProfileSerializer(profile).data
        if registration is not None:
            payload["central_user_registration"] = registration
        return Response(payload, status=status.HTTP_201_CREATED)


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

    def delete(self, request, *args, **kwargs):
        """Remove a staff member who never sold anything.

        Sales and tickets are financial and printed records, so they are never
        cascaded. As soon as one exists the member can only be deactivated.
        """
        profile = self.get_object()
        if profile.user_id == request.user.id:
            raise Conflict(detail="You cannot delete your own staff profile.")
        sales = Sale.objects.filter(staff=profile).count()
        tickets = Ticket.objects.filter(staff=profile).count()
        if sales or tickets:
            raise Conflict(
                detail=(
                    f"{profile.staff_code} has {tickets} ticket(s) and {sales} sale(s). "
                    "Deactivate this staff member instead: sales and tickets are "
                    "financial records and are never deleted."
                )
            )

        tenant = profile.tenant
        user = profile.user
        membership = TenantMembership.objects.filter(tenant=tenant, user=user).first()
        staff_pk = profile.pk
        staff_code = profile.staff_code
        username = unscoped_username(user.username)
        assignment_count = profile.assignments.count()

        # Best effort, before the local rows go: only the membership holds the id
        # a retry would need.
        central_status = ""
        if membership and membership.central_user_id:
            results = _delete_central_users(tenant.code, [membership.central_user_id])
            central_status = results[0].get("status", "") if results else ""

        with transaction.atomic():
            profile.assignments.all().delete()
            if membership:
                membership.delete()
            profile.delete()
            # The account may still serve another organization.
            if not TenantMembership.objects.filter(user=user).exists():
                user.delete()

        record_audit(
            actor=request.user,
            tenant=tenant,
            action="staff.deleted",
            target_type="staff_profile",
            target_id=staff_pk,
            metadata={
                "staff_code": staff_code,
                "username": username,
                "assignments_removed": assignment_count,
                "central_user": central_status,
            },
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


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

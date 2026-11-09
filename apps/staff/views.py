from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.core.context import get_current_tenant_id
from apps.core.exceptions import Conflict, NotFound
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
        registration = getattr(profile, "central_user_registration", None)
        record_audit(
            actor=request.user,
            tenant=profile.tenant,
            action="staff.created",
            target_type="staff_profile",
            target_id=profile.id,
            metadata={
                "staff_code": profile.staff_code,
                "username": profile.user.username,
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

    def delete(self, request, pk):
        """Permanently remove a staff member who has never sold a ticket.

        Sales and tickets PROTECT the staff row because the history points at
        it, so anyone with sales must be deactivated instead. Deletion also
        removes the POS membership and the login identity when nothing else
        still points at it, mirroring tenant deletion.
        """
        try:
            profile = StaffProfile.objects.get(pk=pk)
        except StaffProfile.DoesNotExist:
            raise NotFound("Staff not found.")

        if profile.tickets.exists() or profile.sales.exists():
            raise Conflict(
                f"{profile.staff_code} already has sales or issued tickets, so it cannot "
                "be permanently deleted. Deactivate it instead to keep the sales history."
            )

        staff_code = profile.staff_code
        tenant = profile.tenant
        user = profile.user
        username = user.username
        profile_id = profile.id
        assignments_removed = profile.assignments.count()
        membership = TenantMembership.objects.filter(tenant=tenant, user=user).first()
        central_id = membership.central_user_id if membership else ""

        with transaction.atomic():
            # Assignments cascade with the profile; memberships do not.
            TenantMembership.objects.filter(tenant=tenant, user=user).delete()
            profile.delete()

            # An identity dies only when nothing else still points at it.
            User = get_user_model()
            orphaned = (
                User.objects.filter(
                    pk=user.pk, is_platform_admin=False, is_superuser=False
                )
                .filter(memberships__isnull=True, staff_profiles__isnull=True)
                .exists()
            )
            if orphaned:
                user.delete()

        # After the local delete and never fatal: a stale account would block
        # reusing this username or phone under the same client later on.
        central = []
        if central_id and getattr(settings, "CENTRAL_USER_SYNC_ENABLED", True):
            from apps.platform_admin.views import _delete_central_users

            central = _delete_central_users(tenant.code, [central_id])

        record_audit(
            actor=request.user,
            tenant=tenant,
            action="staff.deleted",
            target_type="staff_profile",
            target_id=profile_id,
            metadata={
                "staff_code": staff_code,
                "username": username,
                "assignments_removed": assignments_removed,
                "user_deleted": orphaned,
                "central_users": central,
            },
        )
        return Response(
            {
                "deleted": True,
                "staff_code": staff_code,
                "assignments_removed": assignments_removed,
                "user_deleted": orphaned,
                "central_users": central,
            }
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


class StaffActivateView(APIView):
    """Re-enables a deactivated staff member and their POS membership.

    Mirrors StaffDeactivateView: the profile status and the tenant membership
    have to move together, otherwise the login would stay blocked.
    """

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def post(self, request, pk):
        try:
            profile = StaffProfile.objects.get(pk=pk)
        except StaffProfile.DoesNotExist:
            raise NotFound("Staff not found.")

        profile.status = StaffProfile.Status.ACTIVE
        profile.save(update_fields=["status", "updated_at"])
        TenantMembership.objects.filter(tenant=profile.tenant, user=profile.user).update(
            status=TenantMembership.Status.ACTIVE
        )
        record_audit(
            actor=request.user,
            tenant=profile.tenant,
            action="staff.activated",
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

from datetime import timedelta

from django.utils import timezone

from apps.accounts.models import User
from apps.assignments.models import StaffEventAssignment
from apps.audit.models import AuditLog
from apps.catalog.models import EventPrice, TicketCategory
from apps.events.models import Event
from apps.sales.models import IdempotencyRecord, Sale
from apps.staff.models import StaffProfile
from apps.tenancy.models import Tenant, TenantMembership
from apps.ticketing.models import Ticket, TicketSequence

from .base import APITestBase


class TenantDeletionTests(APITestBase):
    def delete_url(self, tenant):
        return f"/api/v1/platform/tenants/{tenant.id}/"

    def test_platform_can_delete_empty_tenant(self):
        tenant = Tenant.objects.create(code="EMPTY001", name="Empty Tenant")
        self.login_platform()

        response = self.client.delete(self.delete_url(tenant))

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Tenant.objects.filter(pk=tenant.id).exists())

    def test_platform_can_delete_tenant_with_only_an_event(self):
        tenant = Tenant.objects.create(code="TEST002", name="Tenant With Event")
        now = timezone.now()
        event = Event.objects.create(
            tenant=tenant,
            code="EV004",
            name="Music Fest 2026",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=1),
        )
        self.login_platform()

        response = self.client.delete(self.delete_url(tenant))

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Tenant.objects.filter(pk=tenant.id).exists())
        self.assertFalse(Event.objects.filter(pk=event.id).exists())
        self.assertTrue(
            AuditLog.objects.filter(
                action="platform.tenant.deleted", target_id=str(tenant.id)
            ).exists()
        )

    def test_platform_can_delete_tenant_with_full_data(self):
        self.login_staff_a()
        sale = self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": 2}],
        )
        self.assertEqual(sale.status_code, 201, sale.content)

        tenant_id = self.tenant_a.id
        admin_id = self.admin_a_user.id
        staff_user_id = self.staff_a_user.id
        tenant_audit_ids = list(
            AuditLog.objects.filter(tenant_id=tenant_id).values_list("id", flat=True)
        )
        self.assertTrue(tenant_audit_ids)

        self.login_platform()
        response = self.client.delete(self.delete_url(self.tenant_a))

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Tenant.objects.filter(pk=tenant_id).exists())

        for model in (
            Event,
            TicketCategory,
            EventPrice,
            StaffProfile,
            StaffEventAssignment,
            Ticket,
            TicketSequence,
            Sale,
            IdempotencyRecord,
            TenantMembership,
        ):
            self.assertFalse(
                model._base_manager.filter(tenant_id=tenant_id).exists(),
                f"{model.__name__} rows still exist",
            )

        self.assertTrue(Event.objects.filter(tenant_id=self.tenant_b.id).exists())
        self.assertTrue(
            TenantMembership.objects.filter(tenant_id=self.tenant_b.id).exists()
        )

        self.assertTrue(User.objects.filter(pk=admin_id).exists())
        self.assertTrue(User.objects.filter(pk=staff_user_id).exists())

        preserved = AuditLog.objects.filter(id__in=tenant_audit_ids)
        self.assertEqual(preserved.count(), len(tenant_audit_ids))
        self.assertFalse(preserved.exclude(tenant__isnull=True).exists())

        self.assertTrue(
            AuditLog.objects.filter(
                action="platform.tenant.deleted", target_id=str(tenant_id)
            ).exists()
        )

    def test_tenant_admin_cannot_delete_tenant(self):
        self.login_admin_a()

        response = self.client.delete(self.delete_url(self.tenant_a))

        self.assertEqual(response.status_code, 403, response.content)
        self.assertTrue(Tenant.objects.filter(pk=self.tenant_a.id).exists())

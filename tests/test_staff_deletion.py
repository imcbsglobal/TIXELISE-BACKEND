from unittest.mock import patch

from django.test import override_settings

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.sales.models import Sale
from apps.staff.models import StaffProfile
from apps.tenancy.models import TenantMembership
from apps.ticketing.models import Ticket
from tests.base import APITestBase


class StaffDeletionTests(APITestBase):
    """A staff member can be deleted only while they have no sales and no tickets."""

    def test_deletes_a_staff_member_without_sales_or_tickets(self):
        self.login_admin_a()
        staff_id = self.staff_a.id
        user_id = self.staff_a_user.id

        response = self.client.delete(f"/api/v1/admin/staff/{staff_id}/")

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(StaffProfile.objects.filter(pk=staff_id).exists())
        self.assertFalse(TenantMembership.objects.filter(user_id=user_id).exists())
        self.assertFalse(User.objects.filter(pk=user_id).exists())

    def test_refuses_when_the_staff_member_has_a_sale(self):
        self.login_staff_a()
        sold = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(sold.status_code, 201, sold.content)

        self.login_admin_a()
        response = self.client.delete(f"/api/v1/admin/staff/{self.staff_a.id}/")

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.data["error"]["code"], "CONFLICT")
        message = response.data["error"]["message"]
        self.assertIn("1 sale(s)", message)
        self.assertIn("1 ticket(s)", message)
        self.assertIn("Deactivate", message)
        self.assertTrue(StaffProfile.objects.filter(pk=self.staff_a.pk).exists())

    def test_the_sale_and_its_tickets_survive_the_refusal(self):
        self.login_staff_a()
        self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 2}])

        self.login_admin_a()
        self.client.delete(f"/api/v1/admin/staff/{self.staff_a.id}/")

        self.assertEqual(Sale.objects.filter(tenant=self.tenant_a).count(), 1)
        self.assertEqual(Ticket.objects.filter(tenant=self.tenant_a).count(), 2)

    def test_another_tenant_cannot_delete_the_staff_member(self):
        self.login_admin_b()
        response = self.client.delete(f"/api/v1/admin/staff/{self.staff_a.id}/")

        self.assertEqual(response.status_code, 404, response.content)
        self.assertTrue(StaffProfile.objects.filter(pk=self.staff_a.pk).exists())

    def test_an_admin_cannot_delete_their_own_staff_profile(self):
        own = StaffProfile.objects.create(
            tenant=self.tenant_a,
            user=self.admin_a_user,
            staff_code="ST901",
            display_name="Admin A",
        )

        self.login_admin_a()
        response = self.client.delete(f"/api/v1/admin/staff/{own.id}/")

        self.assertEqual(response.status_code, 409, response.content)
        self.assertTrue(StaffProfile.objects.filter(pk=own.id).exists())

    def test_pos_staff_cannot_delete(self):
        self.login_staff_a()
        response = self.client.delete(f"/api/v1/admin/staff/{self.staff_a.id}/")

        self.assertEqual(response.status_code, 403, response.content)
        self.assertTrue(StaffProfile.objects.filter(pk=self.staff_a.pk).exists())

    def test_an_account_shared_with_another_tenant_is_kept(self):
        shared = User.objects.create_user(username="bbbb::shared", password="StaffPass123!")
        TenantMembership.objects.create(tenant=self.tenant_a, user=shared, role="pos_staff")
        TenantMembership.objects.create(tenant=self.tenant_b, user=shared, role="pos_staff")
        profile = StaffProfile.objects.create(
            tenant=self.tenant_a,
            user=shared,
            staff_code="ST900",
            display_name="Shared Person",
        )

        self.login_admin_a()
        response = self.client.delete(f"/api/v1/admin/staff/{profile.id}/")

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(StaffProfile.objects.filter(pk=profile.id).exists())
        self.assertTrue(User.objects.filter(pk=shared.pk).exists())
        self.assertTrue(
            TenantMembership.objects.filter(tenant=self.tenant_b, user=shared).exists()
        )

    @override_settings(CENTRAL_USER_SYNC_ENABLED=True)
    @patch("apps.staff.views._delete_central_users", return_value=[{"status": "deleted"}])
    def test_removes_the_central_account_and_audits_the_delete(self, fake_delete):
        membership = TenantMembership.objects.get(
            tenant=self.tenant_a, user=self.staff_a_user
        )
        membership.central_user_id = "42"
        membership.save(update_fields=["central_user_id"])

        self.login_admin_a()
        response = self.client.delete(f"/api/v1/admin/staff/{self.staff_a.id}/")

        self.assertEqual(response.status_code, 204, response.content)
        fake_delete.assert_called_once_with("AAAA", ["42"])

        audit = AuditLog.objects.get(action="staff.deleted")
        self.assertEqual(audit.metadata["staff_code"], "ST012")
        self.assertEqual(audit.metadata["central_user"], "deleted")
        self.assertEqual(audit.metadata["assignments_removed"], 1)

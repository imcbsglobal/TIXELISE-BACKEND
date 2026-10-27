from datetime import timedelta

from django.utils import timezone

from apps.assignments.models import StaffEventAssignment
from apps.events.models import Event

from .base import APITestBase


class AuthorizationTests(APITestBase):
    def test_pos_staff_cannot_access_admin_endpoints(self):
        self.login_staff_a()
        for url in [
            "/api/v1/admin/events/",
            "/api/v1/admin/staff/",
            "/api/v1/admin/assignments/",
            "/api/v1/admin/sales/",
            "/api/v1/admin/reports/daily/",
            "/api/v1/admin/audit-logs/",
            "/api/v1/admin/dashboard/",
        ]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, f"{url} -> {response.status_code}")

    def test_tenant_admin_cannot_access_platform_endpoints(self):
        self.login_admin_a()
        response = self.client.get("/api/v1/platform/tenants/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "NOT_PLATFORM_ADMIN")

    def test_pos_staff_cannot_create_events(self):
        self.login_staff_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {
                "code": "HACK1",
                "name": "Hack",
                "start_at": timezone.now().isoformat(),
                "end_at": timezone.now().isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_pos_staff_cannot_sell_unassigned_event(self):
        event = Event.objects.create(
            tenant=self.tenant_a,
            code="EV099",
            name="Unassigned",
            start_at=timezone.now(),
            end_at=timezone.now(),
            status=Event.Status.ACTIVE,
        )
        self.login_staff_a()
        response = self.sell(event.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "ASSIGNMENT_REQUIRED")

    def test_revoked_assignment_blocks_new_sales(self):
        self.login_staff_a()
        ok = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(ok.status_code, 201, ok.content)

        self.assignment_a.status = StaffEventAssignment.Status.REVOKED
        self.assignment_a.save(update_fields=["status", "updated_at"])

        blocked = self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": 1}],
            idempotency_key="key-2",
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.data["error"]["code"], "ASSIGNMENT_REQUIRED")

    def test_deactivated_staff_cannot_sell(self):
        self.login_staff_a()
        self.staff_a.status = "inactive"
        self.staff_a.save(update_fields=["status", "updated_at"])
        from apps.tenancy.models import TenantMembership

        TenantMembership.objects.filter(user=self.staff_a_user).update(status="inactive")
        response = self.client.post(
            "/api/v1/pos/sales/",
            {"event": self.event_a.id, "items": [{"category": self.cat_a_adult.id, "quantity": 1}]},
            format="json",
            headers={"Idempotency-Key": "k1"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "MEMBERSHIP_INACTIVE")

    def test_expired_assignment_blocks_sales(self):
        now = timezone.now()
        self.assignment_a.valid_until = now - timedelta(hours=1)
        self.assignment_a.save(update_fields=["valid_until", "updated_at"])
        self.login_staff_a()
        response = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "ASSIGNMENT_REQUIRED")

    def test_category_restriction_enforced(self):
        self.assignment_a.restrict_categories = True
        self.assignment_a.allowed_categories.set([self.cat_a_child])
        self.assignment_a.save()

        self.login_staff_a()
        denied = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["error"]["code"], "CATEGORY_NOT_ALLOWED")

        allowed = self.sell(self.event_a.id, [{"category": self.cat_a_child.id, "quantity": 1}])
        self.assertEqual(allowed.status_code, 201, allowed.content)

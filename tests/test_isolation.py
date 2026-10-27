from apps.assignments.models import StaffEventAssignment
from apps.events.models import Event

from .base import APITestBase


class CrossTenantIsolationTests(APITestBase):
    """Tenant A must never read or mutate Tenant B (MD §15)."""

    def test_admin_a_cannot_list_tenant_b_events(self):
        self.login_admin_a()
        response = self.client.get("/api/v1/admin/events/")
        self.assertEqual(response.status_code, 200)
        results = response.data["results"]
        names = {e["name"] for e in results}
        self.assertIn("Music Fest A", names)
        self.assertNotIn("Music Fest B", names)
        self.assertEqual(len(results), 1)

    def test_admin_a_cannot_read_tenant_b_event_detail(self):
        self.login_admin_a()
        response = self.client.get(f"/api/v1/admin/events/{self.event_b.id}/")
        self.assertEqual(response.status_code, 404)

    def test_admin_a_cannot_update_tenant_b_event(self):
        self.login_admin_a()
        response = self.client.patch(
            f"/api/v1/admin/events/{self.event_b.id}/", {"name": "hacked"}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        self.event_b.refresh_from_db()
        self.assertNotEqual(self.event_b.name, "hacked")

    def test_admin_a_cannot_create_cross_tenant_assignment(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/assignments/",
            {"staff": self.staff_b.id, "event": self.event_a.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_a_cannot_price_with_tenant_b_category(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/prices/",
            {
                "event": self.event_a.id,
                "category": self.cat_b_adult.id,
                "amount": "1.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_a_cannot_list_tenant_b_staff(self):
        self.login_admin_a()
        response = self.client.get("/api/v1/admin/staff/")
        self.assertEqual(response.status_code, 200)
        codes = {s["staff_code"] for s in response.data["results"]}
        self.assertIn("ST012", codes)
        self.assertNotIn("ST001", codes)

    def test_admin_a_cannot_see_tenant_b_sales_or_tickets(self):
        StaffEventAssignment.objects.create(
            tenant=self.tenant_b, staff=self.staff_b, event=self.event_b
        )
        self.login("ravi_b", "StaffPass123!", "BBBB")
        sale = self.sell(
            self.event_b.id, [{"category": self.cat_b_adult.id, "quantity": 1}]
        )
        self.assertEqual(sale.status_code, 201, sale.content)

        self.login_admin_a()
        sales = self.client.get("/api/v1/admin/sales/")
        self.assertEqual(len(sales.data["results"]), 0)
        tickets = self.client.get("/api/v1/admin/tickets/")
        self.assertEqual(len(tickets.data["results"]), 0)

    def test_duplicate_event_code_allowed_across_tenants(self):
        self.assertEqual(Event.objects.filter(code="EV004").count(), 2)

    def test_pos_staff_b_cannot_see_tenant_a_events(self):
        StaffEventAssignment.objects.create(
            tenant=self.tenant_b, staff=self.staff_b, event=self.event_b
        )
        self.login("ravi_b", "StaffPass123!", "BBBB")
        response = self.client.get("/api/v1/pos/events/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Music Fest B")

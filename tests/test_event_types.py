from decimal import Decimal

from apps.assignments.models import StaffEventAssignment
from apps.catalog.models import EventPrice

from .base import APITestBase


class EventTypeTests(APITestBase):
    """Regular events are schedule-free; periodical events keep the old rules."""

    def test_regular_event_starts_now_and_has_no_end(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {"code": "EV777", "name": "Walk-in counter", "event_type": "regular"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["event_type"], "regular")
        self.assertIsNone(response.data["end_at"])
        self.assertIsNone(response.data["sales_end_at"])
        self.assertIsNotNone(response.data["start_at"])
        self.assertIsNotNone(response.data["sales_start_at"])

    def test_periodical_event_requires_start_and_end(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {"code": "EV778", "name": "No schedule", "event_type": "periodical"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_periodical_event_still_rejects_end_before_start(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {
                "code": "EV779",
                "name": "Backwards",
                "event_type": "periodical",
                "start_at": "2026-12-02T18:00:00Z",
                "end_at": "2026-12-01T18:00:00Z",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_switching_regular_to_periodical_requires_end(self):
        self.login_admin_a()
        created = self.client.post(
            "/api/v1/admin/events/",
            {"code": "EV780", "name": "Switch", "event_type": "regular"},
            format="json",
        )
        response = self.client.patch(
            f"/api/v1/admin/events/{created.data['id']}/",
            {"event_type": "periodical"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_regular_event_sells_without_dates(self):
        self.login_admin_a()
        created = self.client.post(
            "/api/v1/admin/events/",
            {"code": "EV781", "name": "Walk-in sales", "event_type": "regular"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        event_id = created.data["id"]

        EventPrice.objects.create(
            tenant=self.tenant_a,
            event_id=event_id,
            category=self.cat_a_adult,
            amount=Decimal("100.00"),
            currency="INR",
        )
        StaffEventAssignment.objects.create(
            tenant=self.tenant_a,
            staff=self.staff_a,
            event_id=event_id,
            created_by=self.admin_a_user,
        )

        activate = self.client.post(f"/api/v1/admin/events/{event_id}/active/")
        self.assertEqual(activate.status_code, 200, activate.content)

        self.login_staff_a()
        sale = self.sell(
            event_id, [{"category": self.cat_a_adult.id, "quantity": 1}], "regular-1"
        )
        self.assertEqual(sale.status_code, 201, sale.content)

"""Issued-date filtering on the admin ticket list (the Tickets page's date filter)."""

from datetime import date, timedelta

from .base import APITestBase

URL = "/api/v1/admin/tickets/"


class TicketDateFilterTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.login_staff_a()
        response = self.sell(
            self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 2}]
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.login_admin_a()

    def get(self, **params):
        query = "&".join(f"{key}={value}" for key, value in params.items())
        return self.client.get(f"{URL}?{query}" if query else URL)

    def test_without_bounds_everything_is_listed(self):
        self.assertEqual(self.get().data["count"], 2)

    def test_today_includes_the_tickets_just_issued(self):
        today = date.today().isoformat()
        self.assertEqual(self.get(date_from=today, date_to=today).data["count"], 2)

    def test_bounds_cover_whole_days(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.assertEqual(self.get(date_to=yesterday).data["count"], 0)
        self.assertEqual(self.get(date_from=tomorrow).data["count"], 0)

    def test_one_bound_alone_works(self):
        today = date.today().isoformat()
        self.assertEqual(self.get(date_from=today).data["count"], 2)

    def test_invalid_date_is_rejected(self):
        self.assertEqual(self.get(date_from="nope").status_code, 400)

    def test_pos_staff_can_use_the_same_filter(self):
        # This endpoint is shared with the POS, which does not go through
        # TenantScopedPermission - the tenant still has to resolve there.
        self.login_staff_a()
        today = date.today().isoformat()
        self.assertEqual(self.get(date_from=today).data["count"], 2)

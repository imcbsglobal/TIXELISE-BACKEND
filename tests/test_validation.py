from decimal import Decimal

from .base import APITestBase


class DuplicateConstraintTests(APITestBase):
    """DB unique constraints must surface as 400 VALIDATION_ERROR, not 500."""

    def test_duplicate_event_code_rejected(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {
                "code": "ev004",
                "name": "Duplicate event",
                "start_at": "2026-12-01T18:00:00Z",
                "end_at": "2026-12-02T00:00:00Z",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_duplicate_category_code_rejected(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/categories/",
            {"code": "adult", "name": "Adult again"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_duplicate_price_for_event_category_rejected(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/prices/",
            {
                "event": self.event_a.id,
                "category": self.cat_a_adult.id,
                "amount": Decimal("599.00"),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_duplicate_staff_code_rejected(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/staff/",
            {
                "staff_code": "st012",
                "display_name": "Another Ravi",
                "username": "ravi2",
                "email": "ravi2@example.com",
                "phone": "+919876500022",
                "password": "StaffPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_duplicate_assignment_rejected(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/assignments/",
            {"staff": self.staff_a.id, "event": self.event_a.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_assignment_staff_can_be_changed(self):
        from apps.accounts.models import User
        from apps.staff.models import StaffProfile

        user = User.objects.create_user(
            username="staff_a2",
            password="StaffPass123!",
        )
        replacement = StaffProfile.objects.create(
            tenant=self.tenant_a,
            user=user,
            staff_code="ST013",
            display_name="Anita Kumar",
        )

        self.login_admin_a()
        response = self.client.patch(
            f"/api/v1/admin/assignments/{self.assignment_a.id}/",
            {"staff": replacement.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assignment_a.refresh_from_db()
        self.assertEqual(self.assignment_a.staff_id, replacement.id)
        self.assertEqual(response.data["event"], self.event_a.id)

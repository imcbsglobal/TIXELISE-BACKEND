from decimal import Decimal

from .base import APITestBase


class CategoryDeleteTests(APITestBase):
    """Deleting a category soft deletes it.

    A category is never removed from the database: prices, tickets and past
    sales point at it and must keep working. Deleting hides it from the POS
    catalogue and blocks new prices; restoring brings it back.
    """

    def status_url(self, category):
        return f"/api/v1/admin/categories/{category.id}/status/"

    def test_tenant_admin_can_delete_category(self):
        self.login_admin_a()
        response = self.client.post(
            self.status_url(self.cat_a_adult),
            {"status": "inactive"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["status"], "inactive")
        self.cat_a_adult.refresh_from_db()
        self.assertEqual(self.cat_a_adult.status, "inactive")

    def test_deleted_category_can_be_restored(self):
        self.login_admin_a()
        self.client.post(
            self.status_url(self.cat_a_child),
            {"status": "inactive"},
            format="json",
        )
        response = self.client.post(
            self.status_url(self.cat_a_child),
            {"status": "active"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["status"], "active")
        self.cat_a_child.refresh_from_db()
        self.assertEqual(self.cat_a_child.status, "active")

    def test_deleted_category_keeps_existing_prices(self):
        self.login_admin_a()
        self.client.post(
            self.status_url(self.cat_a_adult),
            {"status": "inactive"},
            format="json",
        )
        self.price_a_adult.refresh_from_db()
        self.assertEqual(self.price_a_adult.status, "active")

    def test_new_price_rejected_for_deleted_category(self):
        self.login_admin_a()
        self.client.post(
            self.status_url(self.cat_a_child),
            {"status": "inactive"},
            format="json",
        )
        response = self.client.post(
            "/api/v1/admin/prices/",
            {
                "event": self.event_a.id,
                "category": self.cat_a_child.id,
                "amount": Decimal("249.00"),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_deleted_category_leaves_pos_catalogue(self):
        self.login_admin_a()
        self.client.post(
            self.status_url(self.cat_a_adult),
            {"status": "inactive"},
            format="json",
        )
        self.login_staff_a()
        response = self.client.get(f"/api/v1/pos/events/{self.event_a.id}/categories/")
        self.assertEqual(response.status_code, 200, response.content)
        codes = [c["code"] for c in response.data]
        self.assertNotIn("ADULT", codes)
        self.assertIn("CHILD", codes)

    def test_pos_staff_cannot_delete_category(self):
        self.login_staff_a()
        response = self.client.post(
            self.status_url(self.cat_a_adult),
            {"status": "inactive"},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.cat_a_adult.refresh_from_db()
        self.assertEqual(self.cat_a_adult.status, "active")

    def test_tenant_admin_cannot_delete_other_tenant_category(self):
        self.login_admin_b()
        response = self.client.post(
            self.status_url(self.cat_a_adult),
            {"status": "inactive"},
            format="json",
        )
        self.assertEqual(response.status_code, 404, response.content)
        self.cat_a_adult.refresh_from_db()
        self.assertEqual(self.cat_a_adult.status, "active")

    def test_unknown_status_rejected(self):
        self.login_admin_a()
        response = self.client.post(
            self.status_url(self.cat_a_adult),
            {"status": "deleted"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.cat_a_adult.refresh_from_db()
        self.assertEqual(self.cat_a_adult.status, "active")

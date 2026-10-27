from apps.events.models import Event

from .base import APITestBase


class EventDeletionTests(APITestBase):
    def detail_url(self, event):
        return f"/api/v1/admin/events/{event.id}/"

    def test_tenant_admin_can_permanently_delete_unused_event(self):
        event_id = self.event_a.id
        self.login_admin_a()

        response = self.client.delete(self.detail_url(self.event_a))

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data, {"deleted": True, "code": "EV004"})
        self.assertFalse(Event.objects.filter(pk=event_id).exists())
        self.assertFalse(self.price_a_adult.__class__.objects.filter(pk=self.price_a_adult.id).exists())
        self.assertFalse(self.assignment_a.__class__.objects.filter(pk=self.assignment_a.id).exists())

    def test_event_with_sales_cannot_be_permanently_deleted(self):
        self.login_staff_a()
        sale = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(sale.status_code, 201, sale.content)

        self.login_admin_a()
        response = self.client.delete(self.detail_url(self.event_a))

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.data["error"]["code"], "CONFLICT")
        self.assertTrue(Event.objects.filter(pk=self.event_a.id).exists())

    def test_tenant_admin_cannot_delete_another_tenants_event(self):
        self.login_admin_b()

        response = self.client.delete(self.detail_url(self.event_a))

        self.assertEqual(response.status_code, 404, response.content)
        self.login_admin_a()
        self.assertTrue(Event.objects.filter(pk=self.event_a.id).exists())

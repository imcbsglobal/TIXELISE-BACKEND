from datetime import timedelta

from django.utils import timezone

from apps.events.models import Event

from .base import APITestBase


class ReportingTests(APITestBase):
    def _make_sale(self, quantity=2):
        self.login_staff_a()
        response = self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": quantity}],
        )
        assert response.status_code == 201, response.content
        return response.data

    def test_dashboard_counts_today(self):
        self._make_sale(2)
        self.login_admin_a()
        response = self.client.get("/api/v1/admin/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tickets_sold_today"], 2)
        self.assertEqual(response.data["completed_sales_today"], 1)
        self.assertEqual(response.data["gross_sales_today"], "998.00")
        self.assertEqual(response.data["active_events"], 1)
        self.assertEqual(response.data["active_staff"], 1)

    def test_daily_report_breakdowns(self):
        self._make_sale(2)
        self.login_admin_a()
        response = self.client.get("/api/v1/admin/reports/daily/")
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data["tickets_sold"], 2)
        self.assertEqual(data["transactions"], 1)
        self.assertEqual(data["gross_sales"], "998.00")
        self.assertEqual(len(data["by_event"]), 1)
        self.assertEqual(data["by_event"][0]["tickets"], 2)
        self.assertEqual(len(data["by_category"]), 1)
        self.assertEqual(len(data["by_staff"]), 1)
        self.assertEqual(data["by_staff"][0]["staff_code"], "ST012")

    def test_invalid_date_rejected(self):
        self.login_admin_a()
        response = self.client.get("/api/v1/admin/reports/daily/?date=not-a-date")
        self.assertEqual(response.status_code, 400)


class PlatformTenantLifecycleTests(APITestBase):
    def test_platform_can_create_tenant(self):
        self.login_platform()
        response = self.client.post(
            "/api/v1/platform/tenants/",
            {
                "code": "CCCC",
                "name": "Tenant C",
                "timezone": "Asia/Kolkata",
                "currency": "INR",
                "admin_username": "c_admin",
                "admin_password": "CadminPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "active")

    def test_created_tenant_admin_can_login_immediately(self):
        self.login_platform()
        response = self.client.post(
            "/api/v1/platform/tenants/",
            {
                "code": "DDDD",
                "name": "Tenant D",
                "admin_username": "d_admin",
                "admin_password": "DadminPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        self.client.credentials()
        data = self.login("d_admin", "DadminPass123!", "DDDD")
        self.assertEqual(data["role"], "tenant_admin")
        self.assertEqual(data["tenant"]["code"], "DDDD")

        dashboard = self.client.get("/api/v1/admin/dashboard/")
        self.assertEqual(dashboard.status_code, 200)

    def test_tenant_creation_requires_admin_credentials(self):
        self.login_platform()
        response = self.client.post(
            "/api/v1/platform/tenants/",
            {"code": "EEEE", "name": "Tenant E"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_tenant_creation_rejects_taken_admin_username(self):
        self.login_platform()
        response = self.client.post(
            "/api/v1/platform/tenants/",
            {
                "code": "FFFF",
                "name": "Tenant F",
                "admin_username": "admin_a",
                "admin_password": "FadminPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_tenant_creation_rejects_weak_admin_password(self):
        self.login_platform()
        response = self.client.post(
            "/api/v1/platform/tenants/",
            {
                "code": "GGGG",
                "name": "Tenant G",
                "admin_username": "g_admin",
                "admin_password": "123",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_platform_suspend_and_activate(self):
        self.login_platform()
        suspend = self.client.post(f"/api/v1/platform/tenants/{self.tenant_a.id}/suspend/")
        self.assertEqual(suspend.status_code, 200)
        self.tenant_a.refresh_from_db()
        self.assertEqual(self.tenant_a.status, "suspended")

        activate = self.client.post(f"/api/v1/platform/tenants/{self.tenant_a.id}/activate/")
        self.assertEqual(activate.status_code, 200)
        self.tenant_a.refresh_from_db()
        self.assertEqual(self.tenant_a.status, "active")

    def test_tenant_admin_cannot_suspend_tenant(self):
        self.login_admin_a()
        response = self.client.post(f"/api/v1/platform/tenants/{self.tenant_a.id}/suspend/")
        self.assertEqual(response.status_code, 403)


class EventLifecycleTests(APITestBase):
    def test_admin_can_create_event_via_api(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {
                "code": "EV999",
                "name": "New Show",
                "description": "desc",
                "venue": "Hall",
                "start_at": "2026-12-01T18:00:00Z",
                "end_at": "2026-12-02T00:00:00Z",
                "sales_start_at": "2026-11-01T00:00:00Z",
                "sales_end_at": "2026-12-01T16:00:00Z",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["status"], "draft")
        self.assertEqual(response.data["code"], "EV999")

        event = Event.objects.get(code="EV999")
        self.assertEqual(event.tenant, self.tenant_a)
        self.assertEqual(event.created_by, self.admin_a_user)

        listing = self.client.get("/api/v1/admin/events/?search=EV999")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)

    def test_create_event_validates_end_after_start(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {
                "code": "EV998",
                "name": "Bad times",
                "start_at": "2026-12-02T18:00:00Z",
                "end_at": "2026-12-01T18:00:00Z",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_create_event_rejects_duplicate_code_in_tenant(self):
        self.login_admin_a()
        payload = {
            "code": "EV004",
            "name": "Duplicate",
            "start_at": "2026-12-01T18:00:00Z",
            "end_at": "2026-12-02T00:00:00Z",
        }
        response = self.client.post("/api/v1/admin/events/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_cannot_activate_event_without_price(self):
        event = Event.objects.create(
            tenant=self.tenant_a,
            code="EV100",
            name="No price yet",
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=1),
            status=Event.Status.DRAFT,
        )
        self.login_admin_a()
        response = self.client.post(f"/api/v1/admin/events/{event.id}/active/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "CONFIGURATION_INCOMPLETE")

    def test_activation_and_completion_flow(self):
        self.login_admin_a()
        activate = self.client.post(f"/api/v1/admin/events/{self.event_a.id}/active/")
        self.assertEqual(activate.status_code, 400)  # already active
        complete = self.client.post(f"/api/v1/admin/events/{self.event_a.id}/completed/")
        self.assertEqual(complete.status_code, 200)
        self.event_a.refresh_from_db()
        self.assertEqual(self.event_a.status, "completed")

    def test_invalid_transition_rejected(self):
        self.event_a.status = Event.Status.DRAFT
        self.event_a.save()
        self.login_admin_a()
        response = self.client.post(f"/api/v1/admin/events/{self.event_a.id}/completed/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "INVALID_TRANSITION")

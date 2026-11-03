from datetime import timedelta

from django.utils import timezone

from apps.accounts.models import User
from apps.events.models import Event
from apps.sales.models import Sale
from apps.staff.models import StaffProfile
from apps.tenancy.models import TenantMembership

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


class StaffReportTests(APITestBase):
    def _make_sale(self, quantity=2, idempotency_key="staff-key-1"):
        self.login_staff_a()
        response = self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": quantity}],
            idempotency_key=idempotency_key,
        )
        assert response.status_code == 201, response.content
        return response.data

    def _add_staff(self, code="ST020", name="Asha"):
        user = User.objects.create_user(
            username=f"user-{code.lower()}", password="StaffPass123!"
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a, user=user, role="pos_staff"
        )
        return StaffProfile.objects.create(
            tenant=self.tenant_a,
            user=user,
            staff_code=code,
            display_name=name,
        )

    def test_lists_every_staff_member_with_totals(self):
        self._make_sale(2)
        self._add_staff()
        self.login_admin_a()
        response = self.client.get("/api/v1/admin/reports/staff/")
        self.assertEqual(response.status_code, 200)

        rows = {row["staff_code"]: row for row in response.data["staff"]}
        self.assertEqual(set(rows), {"ST012", "ST020"})

        earner = rows["ST012"]
        self.assertEqual(earner["transactions"], 1)
        self.assertEqual(earner["tickets"], 2)
        self.assertEqual(earner["gross"], "998.00")
        self.assertEqual(earner["net"], "998.00")
        self.assertEqual(earner["avg_ticket_value"], "499.00")
        self.assertIsNotNone(earner["last_sale_at"])

        idle = rows["ST020"]
        self.assertEqual(idle["transactions"], 0)
        self.assertEqual(idle["gross"], "0.00")
        self.assertIsNone(idle["avg_ticket_value"])

        self.assertEqual(response.data["totals"]["staff_with_sales"], 1)
        self.assertEqual(response.data["totals"]["transactions"], 1)
        self.assertEqual(response.data["totals"]["tickets"], 2)
        self.assertEqual(response.data["totals"]["net"], "998.00")
        self.assertEqual(response.data["currency"], "INR")

    def test_by_event_split(self):
        self._make_sale(1)
        self.login_admin_a()
        response = self.client.get("/api/v1/admin/reports/staff/")
        row = response.data["staff"][0]
        self.assertEqual(len(row["by_event"]), 1)
        self.assertEqual(row["by_event"][0]["event_code"], "EV004")
        self.assertEqual(row["by_event"][0]["tickets"], 1)

    def test_other_tenant_staff_are_not_listed(self):
        self.login_admin_a()
        response = self.client.get("/api/v1/admin/reports/staff/")
        self.assertEqual(
            [row["staff_code"] for row in response.data["staff"]], ["ST012"]
        )

    def test_date_range_excludes_sales_outside_window(self):
        self._make_sale(1)
        self.login_admin_a()
        response = self.client.get(
            "/api/v1/admin/reports/staff/?date_from=2020-01-01&date_to=2020-01-02"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["staff"][0]["transactions"], 0)
        self.assertEqual(response.data["totals"]["gross"], "0.00")

    def test_voided_sale_is_flagged_but_still_counts_as_gross(self):
        self._make_sale(1)
        Sale.objects.filter(tenant=self.tenant_a).update(status=Sale.Status.VOIDED)
        self.login_admin_a()
        response = self.client.get("/api/v1/admin/reports/staff/")
        row = response.data["staff"][0]
        self.assertEqual(row["transactions"], 1)
        self.assertEqual(row["voided_transactions"], 1)
        self.assertEqual(row["gross"], "499.00")

    def test_event_filter_scopes_the_totals(self):
        self._make_sale(1)
        self.login_admin_a()
        response = self.client.get(
            f"/api/v1/admin/reports/staff/?event={self.event_b.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["totals"]["transactions"], 0)

    def test_invalid_date_rejected(self):
        self.login_admin_a()
        response = self.client.get("/api/v1/admin/reports/staff/?date_from=oops")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_date_from_after_date_to_rejected(self):
        self.login_admin_a()
        response = self.client.get(
            "/api/v1/admin/reports/staff/?date_from=2026-10-10&date_to=2026-10-01"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")


class AdminSaleDateFilterTests(APITestBase):
    def _make_sale(self):
        self.login_staff_a()
        response = self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": 1}],
            idempotency_key="date-key-1",
        )
        assert response.status_code == 201, response.content

    def test_date_range_filters_sales(self):
        self._make_sale()
        self.login_admin_a()

        inside = self.client.get(
            "/api/v1/admin/sales/?date_from=2020-01-01&date_to=2100-01-01"
        )
        self.assertEqual(inside.status_code, 200)
        self.assertEqual(inside.data["count"], 1)

        outside = self.client.get(
            "/api/v1/admin/sales/?date_from=2020-01-01&date_to=2020-01-02"
        )
        self.assertEqual(outside.data["count"], 0)

    def test_existing_filters_still_work(self):
        self._make_sale()
        self.login_admin_a()
        response = self.client.get(f"/api/v1/admin/sales/?staff={self.staff_a.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_invalid_date_rejected(self):
        self.login_admin_a()
        response = self.client.get("/api/v1/admin/sales/?date_from=nope")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")


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
                "phone": "+91 98765 43210",
                "admin_username": "c_admin",
                "admin_password": "CadminPass123!",
                "admin_email": "c_admin@example.com",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "active")
        self.assertEqual(response.data["phone"], "+91 98765 43210")
        # Central syncs are disabled for tests, so both report as skipped.
        self.assertEqual(response.data["currency_registration"]["status"], "skipped")
        self.assertEqual(response.data["central_user_registration"]["status"], "skipped")

    def test_created_tenant_admin_can_login_immediately(self):
        self.login_platform()
        response = self.client.post(
            "/api/v1/platform/tenants/",
            {
                "code": "DDDD",
                "name": "Tenant D",
                "phone": "+91 90000 00001",
                "admin_username": "d_admin",
                "admin_password": "DadminPass123!",
                "admin_email": "d_admin@example.com",
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

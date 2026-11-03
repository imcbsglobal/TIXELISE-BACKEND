from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.assignments.models import StaffEventAssignment
from apps.catalog.models import EventPrice, TicketCategory
from apps.events.models import Event
from apps.staff.models import StaffProfile
from apps.tenancy.models import Tenant, TenantMembership


# Tests must never write to the central master services.
@override_settings(
    CENTRAL_CURRENCY_SYNC_ENABLED=False,
    CENTRAL_USER_SYNC_ENABLED=False,
)
class APITestBase(APITestCase):
    """Builds a complete tenant world (A + B) for isolation and flow tests."""

    def setUp(self):
        self.platform_user = User.objects.create_user(
            username="plat", password="PlatPass123!", is_platform_admin=True
        )

        self.tenant_a = Tenant.objects.create(code="AAAA", name="Tenant A", timezone="UTC")
        self.tenant_b = Tenant.objects.create(code="BBBB", name="Tenant B", timezone="UTC")

        self.admin_a_user = User.objects.create_user(
            username="admin_a", password="AdminPass123!"
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a, user=self.admin_a_user, role="tenant_admin"
        )

        self.admin_b_user = User.objects.create_user(
            username="admin_b", password="AdminPass123!"
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b, user=self.admin_b_user, role="tenant_admin"
        )

        self.staff_a_user = User.objects.create_user(
            username="ravi", password="StaffPass123!"
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a, user=self.staff_a_user, role="pos_staff"
        )
        self.staff_a = StaffProfile.objects.create(
            tenant=self.tenant_a,
            user=self.staff_a_user,
            staff_code="ST012",
            display_name="Ravi Kumar",
        )

        self.staff_b_user = User.objects.create_user(
            username="ravi_b", password="StaffPass123!"
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b, user=self.staff_b_user, role="pos_staff"
        )
        self.staff_b = StaffProfile.objects.create(
            tenant=self.tenant_b,
            user=self.staff_b_user,
            staff_code="ST001",
            display_name="Ravi B",
        )

        now = timezone.now()
        self.event_a = Event.objects.create(
            tenant=self.tenant_a,
            code="EV004",
            name="Music Fest A",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=1),
            sales_start_at=now - timedelta(hours=1),
            sales_end_at=now + timedelta(days=1),
            status=Event.Status.ACTIVE,
            created_by=self.admin_a_user,
        )
        self.event_b = Event.objects.create(
            tenant=self.tenant_b,
            code="EV004",
            name="Music Fest B",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=1),
            status=Event.Status.ACTIVE,
            created_by=self.admin_b_user,
        )

        self.cat_a_adult = TicketCategory.objects.create(
            tenant=self.tenant_a, code="ADULT", name="Adult"
        )
        self.cat_a_child = TicketCategory.objects.create(
            tenant=self.tenant_a, code="CHILD", name="Child"
        )
        self.cat_b_adult = TicketCategory.objects.create(
            tenant=self.tenant_b, code="ADULT", name="Adult"
        )

        self.price_a_adult = EventPrice.objects.create(
            tenant=self.tenant_a,
            event=self.event_a,
            category=self.cat_a_adult,
            amount=Decimal("499.00"),
            currency="INR",
        )
        self.price_a_child = EventPrice.objects.create(
            tenant=self.tenant_a,
            event=self.event_a,
            category=self.cat_a_child,
            amount=Decimal("199.00"),
            currency="INR",
        )
        EventPrice.objects.create(
            tenant=self.tenant_b,
            event=self.event_b,
            category=self.cat_b_adult,
            amount=Decimal("999.00"),
            currency="INR",
        )

        self.assignment_a = StaffEventAssignment.objects.create(
            tenant=self.tenant_a,
            staff=self.staff_a,
            event=self.event_a,
            created_by=self.admin_a_user,
        )

    def login(self, username, password, tenant_code=None):
        payload = {"username": username, "password": password}
        if tenant_code is not None:
            payload["tenant_code"] = tenant_code
        response = self.client.post("/api/v1/auth/login/", payload, format="json")
        assert response.status_code == 200, response.content
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return response.data

    def login_admin_a(self):
        return self.login("admin_a", "AdminPass123!", "AAAA")

    def login_admin_b(self):
        return self.login("admin_b", "AdminPass123!", "BBBB")

    def login_staff_a(self):
        return self.login("ravi", "StaffPass123!", "AAAA")

    def login_platform(self):
        return self.login("plat", "PlatPass123!", None)

    def sell(self, event_id, items, idempotency_key="key-1"):
        return self.client.post(
            "/api/v1/pos/sales/",
            {"event": event_id, "items": items},
            format="json",
            headers={"Idempotency-Key": idempotency_key},
        )

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.tenancy.models import Tenant

from .base import APITestBase

User = get_user_model()


class AuthTests(APITestBase):
    def test_tenant_admin_login_returns_jwt_with_tenant_claims(self):
        data = self.login_admin_a()
        self.assertEqual(data["role"], "tenant_admin")
        self.assertEqual(data["tenant"]["code"], "AAAA")

    def test_pos_staff_login(self):
        data = self.login_staff_a()
        self.assertEqual(data["role"], "pos_staff")

    def test_platform_login_without_tenant_code(self):
        data = self.login_platform()
        self.assertEqual(data["role"], "platform_admin")
        self.assertIsNone(data["tenant"])

    def test_superuser_automatically_gets_platform_admin_flag(self):
        su = User.objects.create_superuser("root", "root@example.com", "RootPass123!")
        su.refresh_from_db()
        self.assertTrue(su.is_platform_admin)

        regular = User.objects.create_user("plain", password="PlainPass123!")
        self.assertFalse(regular.is_platform_admin)

    def test_platform_login_requires_flag(self):
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "admin_a", "password": "AdminPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_bad_password_rejected(self):
        response = self.client.post(
            "/api/v1/auth/login/",
            {"tenant_code": "AAAA", "username": "admin_a", "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_unknown_tenant_rejected(self):
        response = self.client.post(
            "/api/v1/auth/login/",
            {"tenant_code": "ZZZZ", "username": "admin_a", "password": "AdminPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_user_without_membership_rejected(self):
        User.objects.create_user(username="loner", password="LonerPass123!")
        response = self.client.post(
            "/api/v1/auth/login/",
            {"tenant_code": "AAAA", "username": "loner", "password": "LonerPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_me_returns_memberships(self):
        self.login_admin_a()
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "admin_a")
        self.assertEqual(len(response.data["memberships"]), 1)

    def test_unauthenticated_requests_rejected(self):
        response = self.client.get("/api/v1/admin/events/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED")

    def test_suspended_tenant_login_and_token_blocked(self):
        self.login_admin_a()
        self.tenant_a.status = Tenant.Status.SUSPENDED
        self.tenant_a.save()

        # Login blocked
        response = self.client.post(
            "/api/v1/auth/login/",
            {"tenant_code": "AAAA", "username": "admin_a", "password": "AdminPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "TENANT_SUSPENDED")

        # Existing token also blocked mid-lifecycle (MD §13.2)
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "TENANT_SUSPENDED")

    def test_deactivated_membership_blocked(self):
        self.login_admin_a()
        self.tenant_a.memberships.filter(user=self.admin_a_user).update(status="inactive")
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "MEMBERSHIP_INACTIVE")

    def test_refresh_preserves_tenant_claims(self):
        data = self.login_admin_a()
        response = self.client.post(
            "/api/v1/auth/refresh/", {"refresh": data["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {response.data['access']}"
        )
        me = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me.status_code, 200)

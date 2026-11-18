import json
from io import BytesIO
from unittest import mock
from urllib.error import HTTPError

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.services import authenticate_central_tenant_user
from apps.core.exceptions import CentralMasterUnavailable
from apps.staff.models import StaffProfile
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

    def test_tenant_login_checks_central_service_every_time(self):
        with mock.patch(
            "apps.accounts.serializers.authenticate_central_tenant_user",
            return_value=True,
        ) as central_login:
            for _ in range(2):
                response = self.client.post(
                    "/api/v1/auth/login/",
                    {
                        "tenant_code": "AAAA",
                        "username": "admin_a",
                        "password": "AdminPass123!",
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(central_login.call_count, 2)

    def test_central_rejection_prevents_login(self):
        with mock.patch(
            "apps.accounts.serializers.authenticate_central_tenant_user",
            return_value=False,
        ), mock.patch(
            "apps.accounts.serializers.central_user_profile_for_login"
        ) as get_profile:
            response = self.client.post(
                "/api/v1/auth/login/",
                {
                    "tenant_code": "AAAA",
                    "username": "admin_a",
                    "password": "AdminPass123!",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        get_profile.assert_not_called()

    def test_central_outage_fails_closed(self):
        with mock.patch(
            "apps.accounts.serializers.authenticate_central_tenant_user",
            side_effect=CentralMasterUnavailable(),
        ):
            response = self.client.post(
                "/api/v1/auth/login/",
                {
                    "tenant_code": "AAAA",
                    "username": "admin_a",
                    "password": "AdminPass123!",
                },
                format="json",
            )

        self.assertEqual(
            response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE
        )

    def test_verified_central_admin_is_created_locally_on_first_login(self):
        central_user = {
            "id": "42",
            "client_id": "AAAA",
            "username": "central_admin",
            "first_name": "Central",
            "last_name": "Admin",
            "email": "central-admin@example.com",
            "user_role": "ADMIN",
            "status": "ACTIVE",
            "tixelise": True,
        }
        with mock.patch(
            "apps.accounts.serializers.authenticate_central_tenant_user",
            return_value=True,
        ), mock.patch(
            "apps.accounts.serializers.central_user_profile_for_login",
            return_value=central_user,
        ):
            response = self.client.post(
                "/api/v1/auth/login/",
                {
                    "tenant_code": "AAAA",
                    "username": "central_admin",
                    "password": "CentralPass123!",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "tenant_admin")
        user = User.objects.get(username="central_admin")
        self.assertTrue(user.check_password("CentralPass123!"))
        membership = self.tenant_a.memberships.get(user=user)
        self.assertEqual(membership.central_user_id, "42")
        self.assertEqual(membership.role, "tenant_admin")

    def test_verified_login_bootstraps_missing_tenant_and_user(self):
        central_user = {
            "id": "44",
            "client_id": "NewOrg",
            "username": "new_admin",
            "first_name": "New",
            "last_name": "Admin",
            "email": "new-admin@example.com",
            "user_role": "ADMIN",
            "status": "ACTIVE",
            "tixelise": True,
        }
        with mock.patch(
            "apps.accounts.serializers.authenticate_central_tenant_user",
            return_value=True,
        ), mock.patch(
            "apps.accounts.serializers.tenant_license_profile_for_login",
            return_value={"code": "NewOrg", "name": "New Organization"},
        ), mock.patch(
            "apps.accounts.serializers.central_user_profile_for_login",
            return_value=central_user,
        ):
            response = self.client.post(
                "/api/v1/auth/login/",
                {
                    "tenant_code": "NewOrg",
                    "username": "new_admin",
                    "password": "NewAdminPass123!",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "tenant_admin")
        self.assertEqual(response.data["tenant"]["code"], "NewOrg")
        tenant = Tenant.objects.get(code="NewOrg")
        self.assertEqual(tenant.name, "New Organization")
        self.assertEqual(tenant.currency, "INR")
        self.assertEqual(tenant.timezone, "UTC")
        user = User.objects.get(username="new_admin")
        self.assertTrue(user.check_password("NewAdminPass123!"))
        membership = tenant.memberships.get(user=user)
        self.assertEqual(membership.central_user_id, "44")
        self.assertEqual(membership.role, "tenant_admin")

    def test_verified_central_staff_gets_local_staff_profile(self):
        central_user = {
            "id": "43",
            "client_id": "AAAA",
            "username": "central_staff",
            "first_name": "Central",
            "last_name": "Staff",
            "email": "central-staff@example.com",
            "phone_number": "+919876543210",
            "user_role": "USER",
            "status": "ACTIVE",
            "tixelise": True,
        }
        with mock.patch(
            "apps.accounts.serializers.authenticate_central_tenant_user",
            return_value=True,
        ), mock.patch(
            "apps.accounts.serializers.central_user_profile_for_login",
            return_value=central_user,
        ):
            response = self.client.post(
                "/api/v1/auth/login/",
                {
                    "tenant_code": "AAAA",
                    "username": "central_staff",
                    "password": "CentralPass123!",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(username="central_staff")
        profile = StaffProfile.objects.get(tenant=self.tenant_a, user=user)
        self.assertEqual(profile.display_name, "Central Staff")
        self.assertEqual(profile.email, "central-staff@example.com")
        self.assertEqual(profile.phone, "+919876543210")

    def test_central_login_request_matches_documented_contract(self):
        central_response = mock.MagicMock()
        central_response.read.return_value = json.dumps(
            {
                "success": True,
                "project": "tixelise",
                "project_enabled": True,
            }
        ).encode("utf-8")
        central_response.__enter__.return_value = central_response

        with mock.patch(
            "apps.accounts.services.request.urlopen",
            return_value=central_response,
        ) as urlopen:
            result = authenticate_central_tenant_user(
                "AAAA", "admin_a", "AdminPass123!"
            )

        self.assertTrue(result)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            request.full_url,
            "https://centralmastermanagement.imcbs.com/api/user-login/",
        )
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {
                "client_id": "AAAA",
                "username": "admin_a",
                "password": "AdminPass123!",
                "project": "tixelise",
            },
        )

    def test_central_invalid_credentials_are_rejected(self):
        error = HTTPError(
            "https://centralmastermanagement.imcbs.com/api/user-login/",
            401,
            "Unauthorized",
            None,
            BytesIO(b'{"success": false, "message": "Invalid credentials."}'),
        )
        with mock.patch(
            "apps.accounts.services.request.urlopen", side_effect=error
        ):
            self.assertFalse(
                authenticate_central_tenant_user("AAAA", "admin_a", "wrong")
            )

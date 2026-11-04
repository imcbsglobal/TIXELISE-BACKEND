from apps.accounts.models import User
from apps.accounts.services import scoped_username
from apps.staff.models import StaffProfile
from tests.base import APITestBase


class StaffUsernameScopeTests(APITestBase):
    """A staff username has to be unique inside its tenant, not platform-wide."""

    def _payload(self, **overrides):
        payload = {
            "staff_code": "ST500",
            "display_name": "Priya Nair",
            "username": "priya",
            "email": "priya@example.com",
            "phone": "+919876500099",
            "password": "StaffPass123!",
        }
        payload.update(overrides)
        return payload

    def _create(self, **overrides):
        return self.client.post(
            "/api/v1/admin/staff/", self._payload(**overrides), format="json"
        )

    def test_the_same_username_is_accepted_by_two_tenants(self):
        self.login_admin_a()
        first = self._create()
        self.assertEqual(first.status_code, 201, first.content)

        self.login_admin_b()
        second = self._create(staff_code="ST501")
        self.assertEqual(second.status_code, 201, second.content)

        keys = set(
            User.objects.filter(username__endswith="priya").values_list(
                "username", flat=True
            )
        )
        self.assertEqual(keys, {scoped_username("AAAA", "priya"), scoped_username("BBBB", "priya")})

    def test_the_same_username_is_rejected_in_the_same_tenant(self):
        self.login_admin_a()
        self.assertEqual(self._create().status_code, 201)
        response = self._create(staff_code="ST502", email="other@example.com", phone="+919876500098")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("already taken in this organization", response.data["error"]["message"])

    def test_stored_key_is_scoped_while_the_api_takes_the_plain_username(self):
        self.login_admin_a()
        self.assertEqual(self._create().status_code, 201)

        profile = StaffProfile.objects.get(staff_code="ST500")
        self.assertEqual(profile.user.username, "aaaa::priya")

        # The staff member signs in with the plain name and sees it echoed back.
        self.login("priya", "StaffPass123!", "AAAA")
        me = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me.status_code, 200, me.content)
        self.assertEqual(me.data["username"], "priya")

    def test_scoped_staff_can_log_in_with_their_tenant_code(self):
        self.login_admin_a()
        self.assertEqual(self._create().status_code, 201)

        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "priya", "password": "StaffPass123!", "tenant_code": "AAAA"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["role"], "pos_staff")

    def test_scoped_staff_cannot_log_in_against_another_tenant(self):
        self.login_admin_a()
        self.assertEqual(self._create().status_code, 201)

        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "priya", "password": "StaffPass123!", "tenant_code": "BBBB"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("Invalid credentials", response.data["error"]["message"])

    def test_legacy_plain_usernames_still_log_in(self):
        # tests/base.py creates "ravi" without a tenant prefix, like accounts
        # that existed before usernames were scoped.
        data = self.login_staff_a()
        self.assertEqual(data["role"], "pos_staff")

    def test_email_and_phone_are_unique_inside_the_tenant_only(self):
        self.login_admin_a()
        self.assertEqual(self._create().status_code, 201)

        duplicate_email = self._create(staff_code="ST503", phone="+919876500097")
        self.assertEqual(duplicate_email.status_code, 400, duplicate_email.content)
        self.assertIn("email is already used", duplicate_email.data["error"]["message"])

        duplicate_phone = self._create(staff_code="ST504", email="other@example.com")
        self.assertEqual(duplicate_phone.status_code, 400, duplicate_phone.content)
        self.assertIn("phone is already used", duplicate_phone.data["error"]["message"])

        self.login_admin_b()
        allowed = self._create(staff_code="ST505")
        self.assertEqual(allowed.status_code, 201, allowed.content)

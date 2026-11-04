import io
import json
from contextlib import contextmanager
from unittest import mock
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.platform_admin import views
from apps.staff.models import StaffProfile
from apps.tenancy.models import Tenant, TenantMembership

from .base import APITestBase

User = get_user_model()

USER_MASTER = "https://centralmastermanagement.imcbs.com/api/user-master/"
TENANT_CODE = "OCUWOT7VR8YJU"


@contextmanager
def fake_network(opener):
    """Patch the outbound calls and skip the retry back-off."""
    with mock.patch.object(views, "urlopen", opener), mock.patch.object(
        views.time, "sleep"
    ):
        yield opener


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self._body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Routes central-master calls by method and records every request.

    Mirrors the documented contract: a create answers with a bare message and
    no id, so the caller has to read the id back from the user list.
    """

    def __init__(
        self,
        existing=None,
        created_id=42,
        record=None,
        detail_status=200,
        delete_status=204,
        down=False,
        post_status=201,
        post_body=None,
        post_error=None,
        post_failures=0,
        store_created=True,
    ):
        self.existing = list(existing) if existing is not None else []
        self.created_id = created_id
        self.record = record or {}
        self.detail_status = detail_status
        self.delete_status = delete_status
        self.down = down
        self.post_status = post_status
        self.post_body = (
            post_body if post_body is not None else {"message": "User created successfully."}
        )
        self.post_error = post_error
        self.post_failures = post_failures
        self.store_created = store_created
        self.requests = []

    def _store(self, body):
        """Record a created account so a later read-back can find it."""
        if not self.store_created or not isinstance(body, dict):
            return
        self.existing.append(
            {
                "id": self.created_id,
                "client_id": body.get("client_id"),
                "username": body.get("username"),
            }
        )

    def __call__(self, request, timeout=None):
        if self.down:
            raise URLError("central master down")
        method = request.get_method()
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        self.requests.append({"method": method, "url": request.full_url, "body": body})
        if method == "GET" and request.full_url == USER_MASTER:
            return FakeResponse(self.existing)
        if method == "GET":
            missing = self.detail_status == 404
            return FakeResponse(None if missing else self.record, status=self.detail_status)
        if method == "POST":
            if self.post_failures:
                self.post_failures -= 1
                self._store(body)
                raise URLError("the read operation timed out")
            if self.post_error is not None:
                self._store(body)
                raise self.post_error
            if self.post_status >= 400:
                raise HTTPError(
                    request.full_url,
                    self.post_status,
                    "rejected",
                    None,
                    io.BytesIO(json.dumps(self.post_body).encode("utf-8")),
                )
            self._store(body)
            return FakeResponse(self.post_body, status=self.post_status)
        if method == "DELETE":
            return FakeResponse(None, status=self.delete_status)
        raise AssertionError(f"unexpected method {method}")

    def methods(self):
        return [call["method"] for call in self.requests]

    def body_of(self, method):
        return [call["body"] for call in self.requests if call["method"] == method][0]


class CentralUserRegistrationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            code=TENANT_CODE, name="Dreams Events", currency="INR", phone="9876543210"
        )
        self.user = User.objects.create_user(
            username="john.doe",
            password="Secret123!",
            email="john.doe@example.com",
            first_name="John",
            last_name="Doe",
        )
        self.membership = TenantMembership.objects.create(
            tenant=self.tenant, user=self.user, role=TenantMembership.Role.TENANT_ADMIN
        )

    def test_posts_documented_payload(self):
        opener = FakeOpener()
        with fake_network(opener):
            result = views._register_central_user(self.tenant, self.membership, "Secret123!")

        self.assertEqual(
            opener.requests[-1]["url"],
            USER_MASTER,
        )
        self.assertEqual(
            opener.body_of("POST"),
            {
                "client_id": TENANT_CODE,
                "first_name": "John",
                "last_name": "Doe",
                "username": "john.doe",
                "password": "Secret123!",
                "email": "john.doe@example.com",
                "phone_number": "9876543210",
                "user_role": "ADMIN",
                "trellisco": False,
                "claudius": False,
                "melone": False,
                "tixelise": True,
                "trellisco_crm": False,
                "melone_stay": False,
                "trellisco_books": False,
                "status": "ACTIVE",
            },
        )
        # The create response carries no id, so exactly one read-back follows.
        self.assertEqual(opener.methods(), ["POST", "GET"])
        self.assertEqual(result["status"], "registered")
        self.assertEqual(result["central_user_id"], "42")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.central_user_id, "42")

    def test_missing_names_fall_back_to_username_and_placeholder(self):
        self.user.first_name = ""
        self.user.last_name = ""
        self.user.save(update_fields=["first_name", "last_name"])
        opener = FakeOpener()
        with fake_network(opener):
            views._register_central_user(self.tenant, self.membership, "Secret123!")
        body = opener.body_of("POST")
        self.assertEqual(body["first_name"], "john.doe")
        self.assertEqual(body["last_name"], "-")

    def test_recovers_an_existing_central_user_without_posting(self):
        opener = FakeOpener(
            existing=[{"id": 7, "client_id": "ocuwot7vr8yju", "username": "John.Doe"}]
        )
        with fake_network(opener):
            result = views._register_central_user(
                self.tenant, self.membership, "Secret123!", check_existing=True
            )
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["central_user_id"], "7")
        self.assertNotIn("POST", opener.methods())
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.central_user_id, "7")

    def test_skips_when_already_linked(self):
        self.membership.central_user_id = "11"
        self.membership.save(update_fields=["central_user_id"])
        opener = FakeOpener()
        with fake_network(opener):
            result = views._register_central_user(self.tenant, self.membership, "Secret123!")
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(opener.requests, [])

    def test_requires_a_password_when_no_central_record_exists(self):
        opener = FakeOpener(existing=[])
        with fake_network(opener):
            result = views._register_central_user(
                self.tenant, self.membership, "", check_existing=True
            )
        self.assertEqual(result["status"], "failed")
        self.assertIn("password", result["detail"].lower())
        self.assertNotIn("POST", opener.methods())

    def test_reports_failure_when_the_master_is_unreachable(self):
        opener = FakeOpener(down=True)
        with fake_network(opener):
            result = views._register_central_user(self.tenant, self.membership, "Secret123!")
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("Secret123!", result["detail"])
        # The exception type is named so an outage can actually be diagnosed.
        self.assertIn("URLError", result["detail"])

    def test_does_not_post_when_the_duplicate_check_could_not_run(self):
        # A blind POST here would risk a second account for the same admin.
        opener = FakeOpener(down=True)
        with fake_network(opener):
            result = views._register_central_user(
                self.tenant, self.membership, "Secret123!", check_existing=True
            )
        self.assertEqual(result["status"], "failed")
        self.assertIn("could not read", result["detail"].lower())
        self.assertEqual(opener.requests, [])
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.central_user_id, "")

    def test_confirms_a_write_whose_response_was_lost(self):
        # The classic false negative: the account was created but the reply
        # never arrived. It must be reported as registered, not as an outage.
        opener = FakeOpener(post_error=URLError("the read operation timed out"))
        with fake_network(opener):
            result = views._register_central_user(self.tenant, self.membership, "Secret123!")
        self.assertEqual(result["status"], "registered")
        self.assertEqual(result["central_user_id"], "42")
        self.assertIn("confirmed", result["detail"].lower())
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.central_user_id, "42")

    def test_retries_once_after_a_transport_failure(self):
        opener = FakeOpener(post_failures=1)
        with fake_network(opener):
            result = views._register_central_user(self.tenant, self.membership, "Secret123!")
        self.assertEqual(result["status"], "registered")
        self.assertEqual(opener.methods().count("POST"), 2)

    def test_rejection_reports_the_offending_field(self):
        opener = FakeOpener(
            post_status=400,
            post_body={"phone_number": ["violates the unique constraint."]},
            store_created=False,
        )
        with fake_network(opener):
            result = views._register_central_user(self.tenant, self.membership, "Secret123!")
        self.assertEqual(result["status"], "failed")
        self.assertIn("phone_number", result["detail"])
        self.assertNotIn("Secret123!", result["detail"])


class CentralUserDeletionTests(TestCase):
    def test_deletes_the_matching_record(self):
        opener = FakeOpener(record={"id": 9, "client_id": TENANT_CODE, "tixelise": True})
        with fake_network(opener):
            results = views._delete_central_users(TENANT_CODE, ["9"])
        self.assertEqual(results[0]["status"], "deleted")
        self.assertIn("DELETE", opener.methods())

    def test_refuses_a_record_from_another_client(self):
        opener = FakeOpener(record={"id": 9, "client_id": "SOMEONEELSE01", "tixelise": True})
        with fake_network(opener):
            results = views._delete_central_users(TENANT_CODE, ["9"])
        self.assertEqual(results[0]["status"], "skipped")
        self.assertNotIn("DELETE", opener.methods())

    def test_refuses_a_record_from_another_product(self):
        opener = FakeOpener(record={"id": 9, "client_id": TENANT_CODE, "tixelise": False})
        with fake_network(opener):
            results = views._delete_central_users(TENANT_CODE, ["9"])
        self.assertEqual(results[0]["status"], "skipped")
        self.assertNotIn("DELETE", opener.methods())

    def test_an_already_missing_record_is_not_an_error(self):
        opener = FakeOpener(detail_status=404)
        with fake_network(opener):
            results = views._delete_central_users(TENANT_CODE, ["9"])
        self.assertEqual(results[0]["status"], "gone")

    def test_an_outage_is_reported_instead_of_raised(self):
        with fake_network(FakeOpener(down=True)):
            results = views._delete_central_users(TENANT_CODE, ["9"])
        self.assertEqual(results[0]["status"], "failed")


class CentralSyncEndpointTests(TestCase):
    def setUp(self):
        self.platform = User.objects.create_user(
            username="plat", password="PlatPass123!", is_platform_admin=True
        )
        self.tenant = Tenant.objects.create(
            code=TENANT_CODE, name="Dreams Events", currency="INR", phone="9876543210"
        )
        self.admin = User.objects.create_user(
            username="john.doe",
            password="Secret123!",
            email="john.doe@example.com",
            first_name="John",
            last_name="Doe",
        )
        self.membership = TenantMembership.objects.create(
            tenant=self.tenant, user=self.admin, role=TenantMembership.Role.TENANT_ADMIN
        )
        self.client = APIClient()
        self.client.force_authenticate(self.platform)

    def test_sync_registers_the_admin_and_stores_the_link(self):
        opener = FakeOpener(existing=[], created_id=55)
        with fake_network(opener):
            response = self.client.post(
                f"/api/v1/platform/tenants/{self.tenant.id}/sync-central/",
                {"password": "Secret123!"},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["user"]["status"], "registered")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.central_user_id, "55")

    def test_sync_without_a_password_reports_the_reason(self):
        opener = FakeOpener(existing=[])
        with fake_network(opener):
            response = self.client.post(
                f"/api/v1/platform/tenants/{self.tenant.id}/sync-central/",
                {},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["user"]["status"], "failed")
        self.assertIn("password", response.data["user"]["detail"].lower())

    def test_deleting_the_tenant_removes_the_central_account(self):
        self.membership.central_user_id = "9"
        self.membership.save(update_fields=["central_user_id"])
        opener = FakeOpener(record={"id": 9, "client_id": TENANT_CODE, "tixelise": True})
        with fake_network(opener):
            response = self.client.delete(f"/api/v1/platform/tenants/{self.tenant.id}/")
        self.assertEqual(response.status_code, 204, response.content)
        self.assertIn("DELETE", opener.methods())
        self.assertFalse(Tenant.objects.filter(pk=self.tenant.id).exists())

    def test_deletion_still_succeeds_when_the_master_is_down(self):
        self.membership.central_user_id = "9"
        self.membership.save(update_fields=["central_user_id"])
        with fake_network(FakeOpener(down=True)):
            response = self.client.delete(f"/api/v1/platform/tenants/{self.tenant.id}/")
        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Tenant.objects.filter(pk=self.tenant.id).exists())


@override_settings(CENTRAL_USER_SYNC_ENABLED=True)
class StaffCentralRegistrationTests(APITestBase):
    """A tenant creates POS staff through the same master as its own admin."""

    def _create(self, **overrides):
        payload = {
            "staff_code": "ST900",
            "display_name": "Anita Kumar",
            "username": "anita",
            "email": "anita@example.com",
            "phone": "+919876500011",
            "password": "StaffPass123!",
        }
        payload.update(overrides)
        return self.client.post("/api/v1/admin/staff/", payload, format="json")

    def test_posts_a_staff_role_account(self):
        self.login_admin_a()
        opener = FakeOpener(existing=[], created_id=77)
        with fake_network(opener):
            response = self._create()

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(
            opener.body_of("POST"),
            {
                "client_id": "AAAA",
                "first_name": "Anita",
                "last_name": "Kumar",
                "username": "anita",
                "password": "StaffPass123!",
                "email": "anita@example.com",
                # The staff member's own number, not the tenant's.
                "phone_number": "+919876500011",
                "user_role": "USER",
                "trellisco": False,
                "claudius": False,
                "melone": False,
                "tixelise": True,
                "trellisco_crm": False,
                "melone_stay": False,
                "trellisco_books": False,
                "status": "ACTIVE",
            },
        )
        self.assertEqual(response.data["central_user_registration"]["status"], "registered")
        # The stored key is tenant-scoped ("aaaa::anita"); the master sees "anita".
        membership = TenantMembership.objects.get(
            tenant=self.tenant_a, user__username__endswith="anita"
        )
        self.assertEqual(membership.central_user_id, "77")

    def test_an_outage_does_not_block_staff_creation(self):
        self.login_admin_a()
        with fake_network(FakeOpener(down=True)):
            response = self._create()

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["central_user_registration"]["status"], "failed")
        self.assertTrue(
            StaffProfile.objects.filter(tenant=self.tenant_a, staff_code="ST900").exists()
        )

    def test_email_and_phone_are_required(self):
        self.login_admin_a()
        opener = FakeOpener()
        with fake_network(opener):
            response = self._create(email="", phone="")

        self.assertEqual(response.status_code, 400, response.content)
        message = response.data["error"]["message"]
        self.assertIn("email", message)
        self.assertIn("phone", message)
        # Nothing reaches the master when the local row was never written.
        self.assertEqual(opener.requests, [])

from apps.catalog.models import TicketTemplate

from .base import APITestBase


class POSTicketPrintProfileTests(APITestBase):
    """`/api/v1/pos/ticket-print/` — POS staff read + edit, tenant scoped."""

    URL = "/api/v1/pos/ticket-print/"

    def test_defaults_to_tenant_name_when_unset(self):
        self.login_staff_a()
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"header": "Tenant A", "footer": "", "customized": False},
        )
        self.assertFalse(
            TicketTemplate.objects.filter(tenant=self.tenant_a, name="POS Print").exists()
        )

    def test_staff_can_set_header_and_footer(self):
        self.login_staff_a()
        response = self.client.patch(
            self.URL, {"header": "Dreams Events", "footer": "Thank you!"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"header": "Dreams Events", "footer": "Thank you!", "customized": True},
        )

        template = TicketTemplate.objects.get(tenant=self.tenant_a, name="POS Print")
        self.assertEqual(template.config["header"], "Dreams Events")
        self.assertEqual(template.config["footer"], "Thank you!")

    def test_patch_leaves_omitted_field_untouched(self):
        self.login_staff_a()
        self.client.patch(self.URL, {"header": "Dreams", "footer": "Bye"}, format="json")
        response = self.client.patch(self.URL, {"header": "Dreams 2026"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["header"], "Dreams 2026")
        self.assertEqual(response.data["footer"], "Bye")

    def test_blank_header_falls_back_to_tenant_name(self):
        self.login_staff_a()
        self.client.patch(self.URL, {"header": "Dreams"}, format="json")
        response = self.client.patch(self.URL, {"header": ""}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["header"], "Tenant A")
        self.assertEqual(response.data["customized"], False)

    def test_validation_guards(self):
        self.login_staff_a()
        too_long = self.client.patch(self.URL, {"header": "x" * 81}, format="json")
        self.assertEqual(too_long.status_code, 400)

        too_long_footer = self.client.patch(self.URL, {"footer": "x" * 201}, format="json")
        self.assertEqual(too_long_footer.status_code, 400)

        unknown = self.client.patch(self.URL, {"logo_url": "x"}, format="json")
        self.assertEqual(unknown.status_code, 400)

        not_a_string = self.client.patch(self.URL, {"header": 5}, format="json")
        self.assertEqual(not_a_string.status_code, 400)

    def test_tenant_admin_is_not_allowed_on_pos_route(self):
        self.login_admin_a()
        self.assertEqual(self.client.get(self.URL).status_code, 403)
        self.assertEqual(
            self.client.patch(self.URL, {"header": "x"}, format="json").status_code, 403
        )

    def test_profile_is_per_tenant(self):
        TicketTemplate.objects.create(
            tenant=self.tenant_b, name="POS Print", config={"header": "Tenant B Brand"}
        )
        self.login_staff_a()
        self.assertEqual(self.client.get(self.URL).data["header"], "Tenant A")

        self.login("ravi_b", "StaffPass123!", "BBBB")
        self.assertEqual(self.client.get(self.URL).data["header"], "Tenant B Brand")

    def test_requires_authentication(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        self.assertEqual(
            self.client.patch(self.URL, {"header": "x"}, format="json").status_code, 401
        )

    def test_admin_endpoint_and_pos_endpoint_share_storage(self):
        self.login_staff_a()
        self.client.patch(self.URL, {"header": "Shared Brand"}, format="json")

        self.login_admin_a()
        response = self.client.get("/api/v1/admin/ticket-print/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["header"], "Shared Brand")

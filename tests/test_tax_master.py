"""The tax master pass-through.

Nothing here touches the shared production master: every central call is
replaced, and the assertions are about the exact payload that would have gone
out. That matters because the module's whole job is to decide what leaves the
building - the client ID, the fixed calculation method, and the complete record
PUT requires.
"""

from unittest.mock import patch

from .base import APITestBase

INDIA_COLLECTION = "https://centralmastermanagement.imcbs.com/api/tax-master/india/"
OTHER_COLLECTION = "https://centralmastermanagement.imcbs.com/api/tax-master/other/"

OURS = {
    "id": 7,
    "client_id": "AAAA",
    "code": "GST18",
    "name": "GST 18%",
    "type": "GST",
    "cgst": "9.00",
    "sgst": "9.00",
    "igst": "18.00",
    "gst": "18.00",
    "cal_method": "PERCENTAGE",
    "status": "ACTIVE",
}
THEIRS = {
    "id": 99,
    "client_id": "BBBB",
    "code": "GST5",
    "name": "GST 5%",
    "type": "GST",
    "cgst": "2.50",
    "sgst": "2.50",
    "igst": "5.00",
    "gst": "5.00",
    "cal_method": "PERCENTAGE",
    "status": "ACTIVE",
}


def kind_of(url):
    return "india" if "/india/" in url else "other"


class TaxMasterProxyTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.calls = []

    def _patch_central(self, rows, detail_rows=None):
        """Replace the transport and record what it was asked to send."""
        detail_rows = detail_rows or {}

        def fake(method, url, payload=None, **_kwargs):
            self.calls.append((method, url, payload))
            # Both the collection and the detail URL end in a slash, so the last
            # segment is what tells them apart.
            tail = url.rstrip("/").split("/")[-1]
            if method == "GET" and not tail.isdigit():
                return True, 200, rows.get(kind_of(url), []), ""
            if method == "GET":
                row = detail_rows.get((kind_of(url), int(tail)))
                return (True, 200, row, "") if row else (False, 404, None, "Not found.")
            if method == "DELETE":
                return True, 204, None, ""
            return True, 201, payload, ""

        return patch("apps.platform_admin.tax_master._central_request", side_effect=fake)

    def test_list_is_filtered_to_this_client(self):
        with self._patch_central({"india": [OURS, THEIRS], "other": []}):
            self.login_admin_a()
            response = self.client.get("/api/v1/admin/tax-master/india/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["client_id"], "AAAA")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual([row["id"] for row in response.data["results"]], [7])
        # Both tenants default to INR, so India is the tab this page opens on.
        self.assertEqual(response.data["suggested_kind"], "india")

    def test_create_injects_client_id_and_fixes_the_method(self):
        with self._patch_central({"india": [], "other": []}):
            self.login_admin_a()
            response = self.client.post(
                "/api/v1/admin/tax-master/india/",
                {
                    "code": "gst18",
                    "name": "GST 18%",
                    "type": "GST",
                    "cgst": "9",
                    "sgst": 9,
                    "igst": "18.00",
                    "gst": "18",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201, response.content)
        method, url, sent = self.calls[-1]
        self.assertEqual((method, url), ("POST", INDIA_COLLECTION))
        self.assertEqual(
            sent,
            {
                "client_id": "AAAA",
                "cal_method": "PERCENTAGE",
                "status": "ACTIVE",
                "code": "gst18",
                "name": "GST 18%",
                "type": "GST",
                "cgst": "9.00",
                "sgst": "9.00",
                "igst": "18.00",
                "gst": "18.00",
            },
        )

    def test_a_sent_client_id_is_never_forwarded(self):
        with self._patch_central({"india": [], "other": []}):
            self.login_admin_a()
            self.client.post(
                "/api/v1/admin/tax-master/india/",
                {"client_id": "BBBB", "code": "X1", "name": "X"},
                format="json",
            )

        self.assertEqual(self.calls[-1][2]["client_id"], "AAAA")

    def test_cal_method_cannot_be_chosen(self):
        with self._patch_central({"india": [], "other": []}):
            self.login_admin_a()
            response = self.client.post(
                "/api/v1/admin/tax-master/india/",
                {"code": "X1", "name": "X", "cal_method": "FLAT"},
                format="json",
            )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("cal_method", response.data["error"]["message"])

    def test_rates_outside_a_percentage_range_are_rejected(self):
        with self._patch_central({"india": [], "other": []}):
            self.login_admin_a()
            response = self.client.post(
                "/api/v1/admin/tax-master/india/",
                {"code": "X1", "name": "X", "cgst": "150"},
                format="json",
            )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("cgst", response.data["error"]["message"])

    def test_zero_rate_is_allowed_because_exempt_supply_is_real(self):
        with self._patch_central({"india": [], "other": []}):
            self.login_admin_a()
            response = self.client.post(
                "/api/v1/admin/tax-master/other/",
                {"code": "VAT0", "name": "VAT 0%", "tax": "0"},
                format="json",
            )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.calls[-1][2]["tax"], "0.00")

    def test_other_country_sends_one_rate_and_no_type(self):
        with self._patch_central({"india": [], "other": []}):
            self.login_admin_a()
            response = self.client.post(
                "/api/v1/admin/tax-master/other/",
                {"code": "VAT20", "name": "VAT 20%", "tax": "20", "type": "GST"},
                format="json",
            )

        # `type` does not exist on this endpoint, so it is refused rather than
        # quietly dropped - a caller must not think it was written.
        self.assertEqual(response.status_code, 400, response.content)

    def test_update_puts_the_complete_merged_record_to_the_collection_url(self):
        with self._patch_central({"india": [OURS]}, detail_rows={("india", 7): OURS}):
            self.login_admin_a()
            response = self.client.patch(
                "/api/v1/admin/tax-master/india/7/",
                {"name": "GST 18% Standard"},
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.content)
        method, url, sent = self.calls[-1]
        self.assertEqual((method, url), ("PUT", INDIA_COLLECTION))
        self.assertEqual(sent["id"], 7)
        self.assertEqual(sent["name"], "GST 18% Standard")
        # Untouched fields carry their stored values, which is the whole point of
        # loading the row first: a PUT with holes would blank them upstream.
        self.assertEqual(sent["code"], "GST18")
        self.assertEqual(sent["cgst"], "9.00")
        self.assertEqual(sent["gst"], "18.00")
        self.assertEqual(sent["client_id"], "AAAA")
        self.assertEqual(sent["cal_method"], "PERCENTAGE")

    def test_another_clients_row_is_reported_as_missing(self):
        with self._patch_central({"india": [OURS]}, detail_rows={("india", 99): THEIRS}):
            self.login_admin_a()
            got = self.client.get("/api/v1/admin/tax-master/india/99/")
            patched = self.client.patch(
                "/api/v1/admin/tax-master/india/99/", {"name": "Hijacked"}, format="json"
            )
            deleted = self.client.delete("/api/v1/admin/tax-master/india/99/")

        # 404, not 403: the record's existence is not disclosed either.
        for response in (got, patched, deleted):
            self.assertEqual(response.status_code, 404, response.content)
        self.assertNotIn("PUT", [call[0] for call in self.calls])
        self.assertNotIn("DELETE", [call[0] for call in self.calls])

    def test_delete_succeeds_after_the_ownership_check(self):
        with self._patch_central({"india": [OURS]}, detail_rows={("india", 7): OURS}):
            self.login_admin_a()
            response = self.client.delete("/api/v1/admin/tax-master/india/7/")

        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(self.calls[-1][:2], ("DELETE", f"{INDIA_COLLECTION}7/"))

    def test_only_the_two_real_kinds_are_accepted(self):
        with self._patch_central({"india": [], "other": []}):
            self.login_admin_a()
            response = self.client.get("/api/v1/admin/tax-master/india;DROP/")

        self.assertEqual(response.status_code, 400, response.content)

    def test_pos_staff_cannot_reach_it(self):
        with self._patch_central({"india": [], "other": []}):
            self.login_staff_a()
            response = self.client.get("/api/v1/admin/tax-master/india/")

        self.assertEqual(response.status_code, 403, response.content)

    def test_upstream_outage_is_not_reported_as_our_failure(self):
        def down(method, url, payload=None, **_kwargs):
            return False, None, None, "Connection refused."

        with patch("apps.platform_admin.tax_master._central_request", side_effect=down):
            self.login_admin_a()
            response = self.client.get("/api/v1/admin/tax-master/other/")

        self.assertEqual(response.status_code, 503, response.content)
        self.assertEqual(response.data["error"]["code"], "SERVICE_UNAVAILABLE")

    def test_writes_are_audited(self):
        audited = []
        with self._patch_central({"india": [], "other": []}):
            with patch(
                "apps.platform_admin.tax_master.record_audit",
                side_effect=lambda **kwargs: audited.append(kwargs),
            ):
                self.login_admin_a()
                self.client.post(
                    "/api/v1/admin/tax-master/other/",
                    {"code": "VAT5", "name": "VAT 5%", "tax": "5"},
                    format="json",
                )

        self.assertEqual(len(audited), 1)
        entry = audited[0]
        self.assertEqual(entry["action"], "tax_master.created")
        self.assertEqual(entry["target_type"], "central.tax")
        self.assertEqual(entry["metadata"]["kind"], "other")
        self.assertEqual(entry["tenant"], self.tenant_a)

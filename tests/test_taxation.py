"""Tax on ticket sales: calculation, snapshotting and reporting.

The tax *records* live in a third-party master, so every test here fakes that
host; no test performs network I/O.
"""

from decimal import Decimal
from unittest.mock import patch

from apps.sales.models import Sale, SaleItem
from apps.taxation.models import TaxSetting
from apps.taxation.services import apply_tax_to_line, rate_from_master_row

from .base import APITestBase

TAX_SETTINGS_URL = "/api/v1/admin/tax-settings/"

INDIA_18 = {
    "id": 7,
    "client_id": "AAAA",
    "code": "GST18",
    "name": "GST 18%",
    "type": "GST",
    # Deliberately inconsistent, as real rows on the master are.
    "cgst": "9.00",
    "sgst": "9.00",
    "igst": "0.00",
    "gst": "18.00",
    "cal_method": "PERCENTAGE",
    "status": "ACTIVE",
}

OTHER_20 = {
    "id": 3,
    "client_id": "AAAA",
    "code": "VAT20",
    "name": "VAT 20%",
    "tax": "20.00",
    "cal_method": "PERCENTAGE",
    "status": "ACTIVE",
}


def _master(*rows):
    """Fake the central master transport: always succeeds with `rows`."""

    def fake(*args, **kwargs):
        return True, 200, list(rows), ""

    return patch("apps.platform_admin.tax_master._central_request", side_effect=fake)


class TaxArithmeticTests(APITestBase):
    """Pure functions - no request, no database row needed for the maths."""

    def test_rate_uses_india_gst_total_not_component_sum(self):
        self.assertEqual(rate_from_master_row("india", INDIA_18), Decimal("18.00"))

    def test_rate_uses_flat_tax_for_other_countries(self):
        self.assertEqual(rate_from_master_row("other", OTHER_20), Decimal("20.00"))

    def test_rate_is_clamped_and_normalised(self):
        self.assertEqual(rate_from_master_row("other", {"tax": "150"}), Decimal("0.00"))
        self.assertEqual(rate_from_master_row("other", {"tax": "nonsense"}), Decimal("0.00"))
        self.assertEqual(rate_from_master_row("other", {"tax": "5"}), Decimal("5.00"))

    def test_no_tax_returns_price_untouched(self):
        total, tax = apply_tax_to_line(
            unit_price=Decimal("499.00"), quantity=2, tax=None
        )
        self.assertEqual(total, Decimal("998.00"))
        self.assertEqual(tax, Decimal("0.00"))

    def test_exclusive_tax_is_added_per_line(self):
        setting = TaxSetting(rate=Decimal("18.00"), prices_include_tax=False)
        total, tax = apply_tax_to_line(
            unit_price=Decimal("499.00"), quantity=2, tax=setting
        )
        self.assertEqual(total, Decimal("998.00"))
        self.assertEqual(tax, Decimal("179.64"))

    def test_inclusive_tax_is_extracted_from_the_price(self):
        setting = TaxSetting(rate=Decimal("18.00"), prices_include_tax=True)
        total, tax = apply_tax_to_line(
            unit_price=Decimal("499.00"), quantity=1, tax=setting
        )
        self.assertEqual(tax, Decimal("76.12"))
        self.assertEqual(total + tax, Decimal("499.00"))

    def test_paise_are_rounded_half_up(self):
        setting = TaxSetting(rate=Decimal("18.00"), prices_include_tax=False)
        _total, tax = apply_tax_to_line(
            unit_price=Decimal("123.45"), quantity=1, tax=setting
        )
        self.assertEqual(tax, Decimal("22.22"))  # 22.221 -> 22.22
        _total, tax = apply_tax_to_line(
            unit_price=Decimal("17.50"), quantity=1, tax=setting
        )
        self.assertEqual(tax, Decimal("3.15"))


class TaxSettingApiTests(APITestBase):
    def test_defaults_to_disabled_and_unconfigured(self):
        self.login_admin_a()
        response = self.client.get(TAX_SETTINGS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["enabled"])
        self.assertFalse(response.data["configured"])
        self.assertEqual(response.data["rate"], "0.00")

    def test_enabling_requires_a_selected_record(self):
        self.login_admin_a()
        response = self.client.patch(
            TAX_SETTINGS_URL, {"enabled": True}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(TaxSetting.objects.filter(tenant=self.tenant_a).exists())

    def test_selecting_a_record_snapshots_the_rate(self):
        self.login_admin_a()
        with _master(INDIA_18):
            response = self.client.patch(
                TAX_SETTINGS_URL,
                {"enabled": True, "kind": "india", "tax_master_id": "7"},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["enabled"])
        self.assertEqual(response.data["code"], "GST18")
        self.assertEqual(response.data["rate"], "18.00")
        self.assertEqual(response.data["cgst"], "9.00")
        self.assertIsNotNone(response.data["synced_at"])

    def test_selecting_a_record_before_anything_is_saved(self):
        """The first action a tenant takes is picking a record, not enabling.

        No setting row exists yet, so this must not assume one does.
        """
        self.login_admin_a()
        with _master(INDIA_18):
            response = self.client.patch(
                TAX_SETTINGS_URL,
                {"kind": "india", "tax_master_id": "7"},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["configured"])
        self.assertEqual(response.data["code"], "GST18")
        # Selecting a record must not switch tax on by itself.
        self.assertFalse(response.data["enabled"])

    def test_inclusive_toggle_before_anything_is_saved(self):
        self.login_admin_a()
        response = self.client.patch(
            TAX_SETTINGS_URL, {"prices_include_tax": True}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["prices_include_tax"])
        self.assertFalse(response.data["enabled"])

    def test_a_record_from_another_client_is_refused(self):
        self.login_admin_a()
        foreign = dict(INDIA_18, client_id="SOMEONE_ELSE")
        with _master(foreign):
            response = self.client.patch(
                TAX_SETTINGS_URL,
                {"enabled": True, "kind": "india", "tax_master_id": "7"},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("tax_master_id", response.data["error"]["message"])

    def test_pos_staff_cannot_change_the_setting(self):
        self.login_staff_a()
        response = self.client.get(TAX_SETTINGS_URL)
        self.assertEqual(response.status_code, 403)

    def test_refresh_flags_a_record_that_disappeared(self):
        self.login_admin_a()
        with _master(INDIA_18):
            self.client.patch(
                TAX_SETTINGS_URL,
                {"enabled": True, "kind": "india", "tax_master_id": "7"},
                format="json",
            )
        with _master():
            response = self.client.post(f"{TAX_SETTINGS_URL}refresh/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["found"])
        self.assertIn("warning", response.data)
        # The last known rate stays, so sales keep working.
        self.assertEqual(response.data["rate"], "18.00")


class TaxOnSaleTests(APITestBase):
    def _enable(self, row=INDIA_18, kind="india", inclusive=False):
        self.login_admin_a()
        with _master(row):
            response = self.client.patch(
                TAX_SETTINGS_URL,
                {
                    "enabled": True,
                    "kind": kind,
                    "tax_master_id": str(row["id"]),
                    "prices_include_tax": inclusive,
                },
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)

    def test_tax_off_leaves_every_figure_unchanged(self):
        self.login_staff_a()
        sale = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 2}])
        self.assertEqual(sale.status_code, 201, sale.content)
        self.assertEqual(sale.data["gross_total"], "998.00")
        self.assertEqual(sale.data["tax_total"], "0.00")
        self.assertEqual(sale.data["total_payable"], "998.00")

    def test_enabled_tax_is_added_to_each_ticket(self):
        self._enable()
        self.login_staff_a()
        sale = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 2}])
        self.assertEqual(sale.status_code, 201, sale.content)
        self.assertEqual(sale.data["gross_total"], "998.00")
        self.assertEqual(sale.data["tax_total"], "179.64")
        self.assertEqual(sale.data["total_payable"], "1177.64")

        item = sale.data["items"][0]
        self.assertEqual(item["tax_rate_snapshot"], "18.00")
        self.assertEqual(item["tax_code"], "GST18")
        self.assertEqual(item["tax_amount"], "179.64")
        # Sale total is exactly the sum of its lines.
        self.assertEqual(
            sum(Decimal(i["tax_amount"]) for i in sale.data["items"]),
            Decimal(sale.data["tax_total"]),
        )

    def test_india_components_are_not_summed_into_the_rate(self):
        self._enable()
        self.login_staff_a()
        sale = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        # 18%, not 9 + 9 + 0.
        self.assertEqual(sale.data["tax_total"], "89.82")

    def test_other_country_uses_the_flat_rate(self):
        self._enable(row=OTHER_20, kind="other")
        self.login_staff_a()
        sale = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(sale.data["tax_total"], "99.80")
        self.assertEqual(sale.data["total_payable"], "598.80")

    def test_mixed_lines_sum_per_line_tax(self):
        self._enable()
        self.login_staff_a()
        sale = self.sell(
            self.event_a.id,
            [
                {"category": self.cat_a_adult.id, "quantity": 2},
                {"category": self.cat_a_child.id, "quantity": 1},
            ],
        )
        self.assertEqual(sale.data["gross_total"], "1197.00")
        self.assertEqual(sale.data["tax_total"], "215.46")  # 179.64 + 35.82
        self.assertEqual(sale.data["total_payable"], "1412.46")

    def test_inclusive_pricing_keeps_the_total_the_same(self):
        self._enable(inclusive=True)
        self.login_staff_a()
        sale = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(sale.data["gross_total"], "422.88")
        self.assertEqual(sale.data["tax_total"], "76.12")
        self.assertEqual(sale.data["total_payable"], "499.00")

    def test_disabling_tax_stops_charging_it(self):
        self._enable()
        self.login_admin_a()
        response = self.client.patch(
            TAX_SETTINGS_URL, {"enabled": False}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["enabled"])

        self.login_staff_a()
        sale = self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": 1}],
            idempotency_key="after-off",
        )
        self.assertEqual(sale.data["tax_total"], "0.00")

    def test_rate_change_never_rewrites_a_past_sale(self):
        self._enable()
        self.login_staff_a()
        sale = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(sale.data["tax_total"], "89.82")

        raised = dict(INDIA_18, gst="28.00", code="GST28", name="GST 28%")
        self.login_admin_a()
        with _master(raised):
            self.client.patch(
                TAX_SETTINGS_URL,
                {"kind": "india", "tax_master_id": "7"},
                format="json",
            )

        detail = self.client.get(f"/api/v1/admin/sales/{sale.data['id']}/")
        self.assertEqual(detail.data["tax_total"], "89.82")
        self.assertEqual(detail.data["items"][0]["tax_rate_snapshot"], "18.00")

        # A new sale does pick up the new rate.
        self.login_staff_a()
        newer = self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": 1}],
            idempotency_key="new-rate",
        )
        self.assertEqual(newer.data["tax_total"], "139.72")

    def test_replay_does_not_charge_tax_twice(self):
        self._enable()
        self.login_staff_a()
        payload = [{"category": self.cat_a_adult.id, "quantity": 1}]
        first = self.sell(self.event_a.id, payload, idempotency_key="tax-key")
        replay = self.sell(self.event_a.id, payload, idempotency_key="tax-key")
        self.assertEqual(first.data["tax_total"], "89.82")
        self.assertEqual(replay.data["tax_total"], "89.82")
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(SaleItem.objects.count(), 1)

    def test_complimentary_tickets_are_never_taxed(self):
        self._enable()
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/tickets/manual/",
            {
                "event": self.event_a.id,
                "staff": self.staff_a.id,
                "items": [{"category": self.cat_a_adult.id, "quantity": 2}],
            },
            format="json",
            headers={"Idempotency-Key": "comp-1"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["gross_total"], "0.00")
        self.assertEqual(response.data["tax_total"], "0.00")
        self.assertEqual(response.data["total_payable"], "0.00")


class TaxReportingTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.login_admin_a()
        with _master(INDIA_18):
            self.client.patch(
                TAX_SETTINGS_URL,
                {"enabled": True, "kind": "india", "tax_master_id": "7"},
                format="json",
            )
        self.login_staff_a()
        self.sell(
            self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 2}]
        )
        self.login_admin_a()

    def test_dashboard_reports_tax_and_total(self):
        data = self.client.get("/api/v1/admin/dashboard/").data
        self.assertEqual(data["gross_sales_today"], "998.00")
        self.assertEqual(data["tax_sales_today"], "179.64")
        self.assertEqual(data["total_sales_today"], "1177.64")
        self.assertEqual(data["net_sales_today"], "998.00")

    def test_daily_report_reports_tax_and_total(self):
        data = self.client.get("/api/v1/admin/reports/daily/").data
        self.assertEqual(data["gross_sales"], "998.00")
        self.assertEqual(data["tax_sales"], "179.64")
        self.assertEqual(data["total_sales"], "1177.64")
        event_row = data["by_event"][0]
        self.assertEqual(event_row["amount"], "998.00")
        self.assertEqual(event_row["tax"], "179.64")
        self.assertEqual(event_row["total"], "1177.64")

    def test_staff_report_reports_tax_and_total(self):
        data = self.client.get("/api/v1/admin/reports/staff/").data
        self.assertEqual(data["totals"]["gross"], "998.00")
        self.assertEqual(data["totals"]["tax"], "179.64")
        self.assertEqual(data["totals"]["total"], "1177.64")
        row = next(r for r in data["staff"] if r["tickets"])
        self.assertEqual(row["tax"], "179.64")
        self.assertEqual(row["total"], "1177.64")

    def test_staff_summary_reports_tax_and_total(self):
        data = self.client.get("/api/v1/admin/reports/staff-summary/").data
        self.assertEqual(data["totals"]["amount"], "998.00")
        self.assertEqual(data["totals"]["tax"], "179.64")
        self.assertEqual(data["totals"]["total"], "1177.64")

    def test_staff_sales_detail_reports_tax_per_sale(self):
        data = self.client.get("/api/v1/admin/reports/staff-sales/").data
        self.assertEqual(data["totals"]["tax"], "179.64")
        self.assertEqual(data["totals"]["total"], "1177.64")
        sale = data["sales"][0]
        self.assertEqual(sale["tax_total"], "179.64")
        self.assertEqual(sale["total_payable"], "1177.64")

    def test_pos_catalogue_shows_the_rate(self):
        self.login_staff_a()
        data = self.client.get(
            f"/api/v1/pos/events/{self.event_a.id}/categories/"
        ).data
        adult = next(row for row in data if row["code"] == "ADULT")
        self.assertEqual(adult["tax_rate"], "18.00")
        self.assertEqual(adult["price_with_tax"], "588.82")

    def test_ticket_print_payload_carries_the_snapshot(self):
        sale = self.client.get("/api/v1/admin/sales/").data["results"][0]
        ticket_id = sale["tickets"][0]["id"]
        data = self.client.get(f"/api/v1/admin/tickets/{ticket_id}/print/").data
        self.assertEqual(data["ticket"]["unit_price"], "499.00")
        self.assertEqual(data["ticket"]["tax_rate"], "18.00")
        self.assertEqual(data["ticket"]["tax_amount"], "89.82")
        self.assertEqual(data["ticket"]["total"], "588.82")

from decimal import Decimal

from apps.events.models import Event
from apps.sales.models import SaleItem
from apps.taxation.models import TaxSetting

from .base import APITestBase

EVENT_TAX = {
    "tax_mode": Event.TaxMode.EVENT,
    "tax_rate": "12.50",
    "hsn_code": "9983",
    "prices_include_tax": False,
}


class EventTaxApiTests(APITestBase):
    def _patch_event(self, **payload):
        self.login_admin_a()
        return self.client.patch(
            f"/api/v1/admin/events/{self.event_a.id}/", payload, format="json"
        )

    def _company_tax(self, rate="18.00", inclusive=False):
        return TaxSetting.objects.create(
            tenant=self.tenant_a,
            enabled=True,
            kind=TaxSetting.Kind.INDIA,
            tax_master_id="7",
            code="GST18",
            name="GST 18%",
            rate=Decimal(rate),
            prices_include_tax=inclusive,
        )

    def test_create_event_with_event_tax(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {
                "code": "TAXEV",
                "name": "Taxed Event",
                "event_type": "regular",
                "status": "active",
                **EVENT_TAX,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["tax_mode"], "event")
        self.assertEqual(response.data["tax_rate"], "12.50")
        self.assertEqual(response.data["hsn_code"], "9983")
        self.assertFalse(response.data["prices_include_tax"])

    def test_event_tax_requires_rate_and_hsn(self):
        response = self._patch_event(tax_mode="event")
        self.assertEqual(response.status_code, 400)
        message = response.data["error"]["message"]
        self.assertIn("tax_rate", message)
        self.assertIn("hsn_code", message)

    def test_event_tax_rejects_out_of_range_rate(self):
        response = self._patch_event(tax_mode="event", tax_rate="150", hsn_code="9983")
        self.assertEqual(response.status_code, 400)
        self.assertIn("tax_rate", response.data["error"]["message"])

    def test_event_tax_rejects_bad_hsn(self):
        response = self._patch_event(tax_mode="event", tax_rate="12.50", hsn_code="12AB")
        self.assertEqual(response.status_code, 400)
        self.assertIn("hsn_code", response.data["error"]["message"])

    def test_inherit_and_disabled_do_not_require_event_tax_fields(self):
        inherited = self._patch_event(tax_mode="inherit")
        self.assertEqual(inherited.status_code, 200, inherited.content)
        disabled = self._patch_event(tax_mode="disabled")
        self.assertEqual(disabled.status_code, 200, disabled.content)

    def test_event_tax_overrides_company_tax(self):
        self._company_tax()
        response = self._patch_event(**EVENT_TAX)
        self.assertEqual(response.status_code, 200, response.content)

        self.login_staff_a()
        sale = self.sell(
            self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 2}]
        )
        self.assertEqual(sale.status_code, 201, sale.content)
        self.assertEqual(sale.data["gross_total"], "998.00")
        self.assertEqual(sale.data["tax_total"], "124.75")
        self.assertEqual(sale.data["total_payable"], "1122.75")
        self.assertEqual(sale.data["items"][0]["tax_rate_snapshot"], "12.50")
        self.assertEqual(sale.data["items"][0]["hsn_code"], "9983")

    def test_event_tax_off_beats_company_tax(self):
        self._company_tax()
        response = self._patch_event(tax_mode="disabled")
        self.assertEqual(response.status_code, 200, response.content)

        self.login_staff_a()
        sale = self.sell(
            self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}]
        )
        self.assertEqual(sale.status_code, 201, sale.content)
        self.assertEqual(sale.data["tax_total"], "0.00")
        self.assertEqual(sale.data["items"][0]["hsn_code"], "")

    def test_inherit_still_uses_company_tax(self):
        self._company_tax()
        self.login_staff_a()
        sale = self.sell(
            self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}]
        )
        self.assertEqual(sale.status_code, 201, sale.content)
        self.assertEqual(sale.data["tax_total"], "89.82")
        self.assertEqual(sale.data["items"][0]["tax_code"], "GST18")

    def test_inclusive_event_tax_is_extracted_from_the_price(self):
        response = self._patch_event(**{**EVENT_TAX, "prices_include_tax": True})
        self.assertEqual(response.status_code, 200, response.content)

        self.login_staff_a()
        sale = self.sell(
            self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}]
        )
        self.assertEqual(sale.status_code, 201, sale.content)
        self.assertEqual(sale.data["gross_total"], "422.88")
        self.assertEqual(sale.data["tax_total"], "76.12")
        self.assertEqual(sale.data["total_payable"], "499.00")

    def test_pos_catalogue_uses_event_tax(self):
        self._company_tax()
        self._patch_event(**EVENT_TAX)
        self.login_staff_a()
        data = self.client.get(
            f"/api/v1/pos/events/{self.event_a.id}/categories/"
        ).data
        adult = next(row for row in data if row["code"] == "ADULT")
        self.assertEqual(adult["tax_rate"], "12.50")
        self.assertEqual(adult["hsn_code"], "9983")
        self.assertEqual(adult["price_with_tax"], "561.38")

    def test_ticket_print_carries_event_hsn(self):
        self._patch_event(**EVENT_TAX)
        self.login_staff_a()
        sale = self.sell(
            self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}]
        )
        self.login_admin_a()
        data = self.client.get(
            f"/api/v1/admin/tickets/{sale.data['tickets'][0]['id']}/print/"
        ).data
        self.assertEqual(data["ticket"]["tax_rate"], "12.50")
        self.assertEqual(data["ticket"]["hsn_code"], "9983")

    def test_event_rate_change_does_not_rewrite_a_past_sale(self):
        self._patch_event(**EVENT_TAX)
        self.login_staff_a()
        sale = self.sell(
            self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}]
        )
        self.assertEqual(sale.data["tax_total"], "62.38")

        self._patch_event(tax_rate="28.00")
        self.login_admin_a()
        detail = self.client.get(f"/api/v1/admin/sales/{sale.data['id']}/")
        self.assertEqual(detail.data["items"][0]["tax_rate_snapshot"], "12.50")
        self.assertEqual(detail.data["items"][0]["hsn_code"], "9983")

        self.login_staff_a()
        newer = self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": 1}],
            idempotency_key="event-new-rate",
        )
        self.assertEqual(newer.data["tax_total"], "139.72")
        self.assertEqual(
            SaleItem.objects.filter(sale_id=sale.data["id"]).count(), 1
        )

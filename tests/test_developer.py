"""The developer delete tool: scoping, confirmation and what survives."""

from apps.audit.models import AuditLog
from apps.assignments.models import StaffEventAssignment
from apps.catalog.models import EventPrice, TicketCategory
from apps.events.models import Event
from apps.sales.models import IdempotencyRecord, Sale, SaleItem
from apps.staff.models import StaffProfile
from apps.taxation.models import TaxSetting
from apps.ticketing.models import Ticket, TicketSequence

from .base import APITestBase

SUMMARY_URL = "/api/v1/admin/developer/data-summary/"
DELETE_URL = "/api/v1/admin/developer/delete-data/"


def _all(model, tenant):
    """Unscoped counts: the tenant context must not hide the other tenant."""
    if model is SaleItem:
        # The line belongs to its sale; there is no tenant column to filter on.
        return SaleItem._base_manager.filter(sale__tenant=tenant)
    return model._base_manager.filter(tenant=tenant)


class DeveloperSummaryTests(APITestBase):
    def test_counts_only_the_current_tenant(self):
        self.login_staff_a()
        self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": 2}],
        )
        self.login("ravi_b", "StaffPass123!", "BBBB")
        self.sell(self.event_b.id, [{"category": self.cat_b_adult.id, "quantity": 1}])

        self.login_admin_a()
        response = self.client.get(SUMMARY_URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["tenant_code"], "AAAA")
        self.assertEqual(response.data["tickets"], 2)
        self.assertEqual(response.data["sales"], 1)
        self.assertEqual(response.data["sale_items"], 1)
        self.assertEqual(response.data["sequences"], 1)
        self.assertEqual(response.data["pos_sales"], 1)
        self.assertEqual(response.data["manual_sales"], 0)
        # Master data is counted too, so the UI can offer it without a second call.
        self.assertEqual(response.data["events"], 1)
        self.assertEqual(response.data["categories"], 2)
        self.assertEqual(response.data["prices"], 2)
        self.assertEqual(response.data["assignments"], 1)

    def test_pos_staff_cannot_see_the_tool(self):
        self.login_staff_a()
        self.assertEqual(self.client.get(SUMMARY_URL).status_code, 403)


class DeveloperDeleteRefusalTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.login_staff_a()
        self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.login_admin_a()

    def test_pos_staff_cannot_delete(self):
        self.login_staff_a()
        response = self.client.post(
            DELETE_URL, {"scopes": ["tickets"], "confirm": "AAAA"}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(_all(Ticket, self.tenant_a).count(), 1)

    def test_wrong_confirmation_deletes_nothing(self):
        response = self.client.post(
            DELETE_URL, {"scopes": ["tickets", "sales"], "confirm": "BBBB"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(_all(Ticket, self.tenant_a).count(), 1)
        self.assertEqual(_all(Sale, self.tenant_a).count(), 1)

    def test_missing_confirmation_deletes_nothing(self):
        response = self.client.post(DELETE_URL, {"scopes": ["tickets"]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(_all(Ticket, self.tenant_a).count(), 1)

    def test_confirmation_is_case_insensitive(self):
        response = self.client.post(
            DELETE_URL, {"scopes": ["tickets"], "confirm": "aaaa"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_empty_scopes_is_refused(self):
        response = self.client.post(
            DELETE_URL, {"scopes": [], "confirm": "AAAA"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(_all(Ticket, self.tenant_a).count(), 1)

    def test_unknown_scope_is_refused(self):
        response = self.client.post(
            DELETE_URL, {"scopes": ["tickets", "events"], "confirm": "AAAA"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(_all(Ticket, self.tenant_a).count(), 1)
        self.assertEqual(Event._base_manager.filter(tenant=self.tenant_a).count(), 1)

    def test_malformed_body_is_refused(self):
        response = self.client.post(
            DELETE_URL, {"scopes": "tickets", "confirm": "AAAA"}, format="json"
        )
        self.assertEqual(response.status_code, 400)


class DeveloperDeleteTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.login_staff_a()
        self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 2}])
        self.sell(
            self.event_a.id,
            [{"category": self.cat_a_child.id, "quantity": 1}],
            "key-2",
        )
        # Tenant B also trades, so "only A was touched" is a real assertion.
        # Its staff must be assigned to its event, exactly as a POS sale needs.
        StaffEventAssignment.objects.create(
            tenant=self.tenant_b,
            staff=self.staff_b,
            event=self.event_b,
            created_by=self.admin_b_user,
        )
        self.login("ravi_b", "StaffPass123!", "BBBB")
        self.sell(self.event_b.id, [{"category": self.cat_b_adult.id, "quantity": 3}])
        self.login_admin_a()

    def purge(self, scopes, confirm="AAAA"):
        return self.client.post(
            DELETE_URL, {"scopes": scopes, "confirm": confirm}, format="json"
        )

    def test_tickets_only_keeps_sales_and_numbering(self):
        response = self.purge(["tickets"])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["deleted"]["tickets"], 3)
        self.assertEqual(_all(Ticket, self.tenant_a).count(), 0)
        self.assertEqual(_all(Sale, self.tenant_a).count(), 2)
        self.assertEqual(_all(SaleItem, self.tenant_a).count(), 2)
        self.assertEqual(_all(TicketSequence, self.tenant_a).count(), 1)
        self.assertEqual(response.data["deleted"]["sequences"], 0)
        self.assertEqual(response.data["skipped"]["masters"], 1)

    def test_sales_carries_tickets_with_it(self):
        response = self.purge(["sales"])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["implied"], ["tickets"])
        self.assertEqual(response.data["deleted"]["sales"], 2)
        self.assertEqual(response.data["deleted"]["tickets"], 3)
        self.assertEqual(response.data["deleted"]["sale_items"], 2)
        self.assertEqual(_all(Sale, self.tenant_a).count(), 0)
        self.assertEqual(_all(Ticket, self.tenant_a).count(), 0)
        self.assertEqual(_all(IdempotencyRecord, self.tenant_a).count(), 0)
        # Numbering was not ticked, so its counter is left alone.
        self.assertEqual(_all(TicketSequence, self.tenant_a).count(), 1)

    def test_sales_plus_numbering_starts_tickets_at_one_again(self):
        response = self.purge(["tickets", "sales", "numbering"])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["deleted"]["sequences"], 1)
        self.assertEqual(_all(TicketSequence, self.tenant_a).first().last_number, 0)

        self.login_staff_a()
        again = self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": 1}],
            "after-purge",
        )
        self.assertEqual(again.status_code, 201, again.content)
        ticket = Ticket._base_manager.get(tenant=self.tenant_a)
        self.assertEqual(ticket.sequence_number, 1)

    def test_numbering_alone_never_collides_with_kept_tickets(self):
        response = self.purge(["numbering"])
        self.assertEqual(response.status_code, 200, response.content)
        sequence = _all(TicketSequence, self.tenant_a).first()
        self.assertEqual(sequence.last_number, 3)

        self.login_staff_a()
        again = self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": 1}],
            "after-reset",
        )
        self.assertEqual(again.status_code, 201, again.content)
        numbers = sorted(
            _all(Ticket, self.tenant_a).values_list("sequence_number", flat=True)
        )
        self.assertEqual(numbers, [1, 2, 3, 4])

    def test_masters_alone_is_refused_while_history_exists(self):
        response = self.purge(["masters"])
        self.assertEqual(response.status_code, 400, response.content)
        # Nothing was removed on the way to that refusal.
        self.assertEqual(_all(Ticket, self.tenant_a).count(), 3)
        self.assertEqual(_all(Sale, self.tenant_a).count(), 2)
        self.assertEqual(_all(Event, self.tenant_a).count(), 1)
        self.assertEqual(_all(TicketCategory, self.tenant_a).count(), 2)
        self.assertEqual(_all(EventPrice, self.tenant_a).count(), 2)

    def test_masters_wipes_configuration_but_keeps_staff(self):
        response = self.purge(["tickets", "sales", "numbering", "masters"])
        self.assertEqual(response.status_code, 200, response.content)
        deleted = response.data["deleted"]
        self.assertEqual(deleted["events"], 1)
        self.assertEqual(deleted["categories"], 2)
        self.assertEqual(deleted["prices"], 2)
        self.assertEqual(deleted["assignments"], 1)
        self.assertEqual(deleted["sequences"], 1)

        self.assertEqual(_all(Event, self.tenant_a).count(), 0)
        self.assertEqual(_all(TicketCategory, self.tenant_a).count(), 0)
        self.assertEqual(_all(EventPrice, self.tenant_a).count(), 0)
        self.assertEqual(_all(StaffEventAssignment, self.tenant_a).count(), 0)
        self.assertEqual(_all(TicketSequence, self.tenant_a).count(), 0)
        # People and settings are not trading history.
        self.assertEqual(StaffProfile._base_manager.filter(tenant=self.tenant_a).count(), 1)

    def test_masters_are_scoped_to_the_current_tenant(self):
        self.purge(["tickets", "sales", "numbering", "masters"])
        self.assertEqual(_all(Event, self.tenant_b).count(), 1)
        self.assertEqual(_all(TicketCategory, self.tenant_b).count(), 1)
        self.assertEqual(_all(EventPrice, self.tenant_b).count(), 1)
        self.assertEqual(len(StaffEventAssignment._base_manager.filter(tenant=self.tenant_b)), 1)

    def test_the_other_tenant_is_untouched(self):
        self.purge(["tickets", "sales", "numbering"])
        self.assertEqual(_all(Ticket, self.tenant_b).count(), 3)
        self.assertEqual(_all(Sale, self.tenant_b).count(), 1)
        self.assertEqual(_all(SaleItem, self.tenant_b).count(), 1)
        self.assertEqual(_all(TicketSequence, self.tenant_b).count(), 1)
        self.assertEqual(
            _all(TicketSequence, self.tenant_b).first().last_number, 3
        )

    def test_configuration_survives(self):
        TaxSetting.objects.create(
            tenant=self.tenant_a,
            code="GST18",
            rate="18.00",
            enabled=True,
        )
        self.purge(["tickets", "sales", "numbering"])
        self.assertEqual(Event._base_manager.filter(tenant=self.tenant_a).count(), 1)
        self.assertEqual(EventPrice._base_manager.filter(tenant=self.tenant_a).count(), 2)
        self.assertEqual(StaffProfile._base_manager.filter(tenant=self.tenant_a).count(), 1)
        self.assertEqual(TaxSetting._base_manager.filter(tenant=self.tenant_a).count(), 1)

    def test_summary_after_purge_reports_zero(self):
        response = self.purge(["tickets", "sales", "numbering"])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["summary"]["tickets"], 0)
        self.assertEqual(response.data["summary"]["sales"], 0)
        self.assertEqual(response.data["summary"]["sale_items"], 0)

    def test_purge_is_audited(self):
        self.purge(["sales"])
        entry = AuditLog.objects.filter(action="developer.data_purged").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.tenant_id, self.tenant_a.id)
        self.assertEqual(entry.metadata["deleted"]["sales"], 2)
        self.assertIn("sales", entry.metadata["scopes"])

    def test_reports_are_empty_for_the_purged_tenant(self):
        self.purge(["tickets", "sales", "numbering"])
        response = self.client.get("/api/v1/admin/reports/daily/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["tickets_sold"], 0)
        self.assertEqual(response.data["transactions"], 0)
        self.assertEqual(response.data["gross_sales"], "0.00")

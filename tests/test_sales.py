from datetime import timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

from django.db import connections
from django.test import TransactionTestCase
from django.utils import timezone

from apps.assignments.models import StaffEventAssignment
from apps.catalog.models import EventPrice
from apps.events.models import Event
from apps.sales.models import IdempotencyRecord, Sale
from apps.staff.models import StaffProfile
from apps.tenancy.models import Tenant, TenantMembership
from apps.ticketing.models import Ticket, TicketSequence

from .base import APITestBase


class SaleCreationTests(APITestBase):
    def test_successful_sale_creates_tickets_with_readable_codes(self):
        self.login_staff_a()
        response = self.sell(
            self.event_a.id,
            [
                {"category": self.cat_a_adult.id, "quantity": 2},
                {"category": self.cat_a_child.id, "quantity": 1},
            ],
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.data
        self.assertEqual(data["gross_total"], "1197.00")  # 2*499 + 199
        self.assertEqual(len(data["tickets"]), 3)
        code = data["tickets"][0]["ticket_code"]
        # DREAMS-style: TENANT-STAFF-EVENT-UTCSTAMP-SEQUENCE
        parts = code.split("-")
        self.assertEqual(parts[0], "AAAA")
        self.assertEqual(parts[1], "ST012")
        self.assertEqual(parts[2], "EV004")
        self.assertTrue(parts[4].isdigit() and len(parts[4]) == 6)

    def test_sequences_increment_within_event(self):
        self.login_staff_a()
        first = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        second = self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": 2}],
            idempotency_key="key-2",
        )
        seqs = sorted(
            [t["sequence_number"] for t in first.data["tickets"] + second.data["tickets"]]
        )
        self.assertEqual(seqs, [1, 2, 3])

    def test_idempotent_replay_returns_same_sale(self):
        self.login_staff_a()
        payload = [{"category": self.cat_a_adult.id, "quantity": 2}]
        first = self.sell(self.event_a.id, payload, idempotency_key="same-key")
        self.assertEqual(first.status_code, 201)
        replay = self.sell(self.event_a.id, payload, idempotency_key="same-key")
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.data["sale_reference"], replay.data["sale_reference"])
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(Ticket.objects.count(), 2)

    def test_idempotency_key_with_different_payload_conflicts(self):
        self.login_staff_a()
        self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}], "k9")
        conflict = self.sell(
            self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 2}], "k9"
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["error"]["code"], "IDEMPOTENCY_CONFLICT")

    def test_missing_idempotency_key_rejected(self):
        self.login_staff_a()
        response = self.client.post(
            "/api/v1/pos/sales/",
            {"event": self.event_a.id, "items": [{"category": self.cat_a_adult.id, "quantity": 1}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "IDEMPOTENCY_KEY_REQUIRED")

    def test_server_side_price_used_not_client_price(self):
        self.login_staff_a()
        response = self.client.post(
            "/api/v1/pos/sales/",
            {
                "event": self.event_a.id,
                "items": [{"category": self.cat_a_adult.id, "quantity": 1, "price": "1.00"}],
            },
            format="json",
            headers={"Idempotency-Key": "cheap"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["gross_total"], "499.00")

    def test_price_snapshot_survives_price_change(self):
        self.login_staff_a()
        sale = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(sale.status_code, 201)

        self.price_a_adult.amount = Decimal("799.00")
        self.price_a_adult.save(update_fields=["amount", "updated_at"])

        self.login_admin_a()
        detail = self.client.get(f"/api/v1/admin/sales/{sale.data['id']}/")
        item = detail.data["items"][0]
        self.assertEqual(item["unit_price_snapshot"], "499.00")
        self.assertEqual(detail.data["gross_total"], "499.00")

    def test_draft_event_not_sellable(self):
        self.event_a.status = Event.Status.DRAFT
        self.event_a.save(update_fields=["status", "updated_at"])
        self.login_staff_a()
        response = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "EVENT_NOT_SELLABLE")

    def test_sales_window_closed(self):
        now = timezone.now()
        self.event_a.sales_end_at = now - timedelta(minutes=5)
        self.event_a.save(update_fields=["sales_end_at", "updated_at"])
        self.login_staff_a()
        response = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "SALES_WINDOW_CLOSED")

    def test_inactive_price_rejected(self):
        self.price_a_adult.status = EventPrice.Status.INACTIVE
        self.price_a_adult.save(update_fields=["status", "updated_at"])
        self.login_staff_a()
        response = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "PRICE_UNAVAILABLE")

    def test_reprint_does_not_create_new_ticket_or_sale(self):
        self.login_staff_a()
        sale = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        ticket_id = sale.data["tickets"][0]["id"]

        response = self.client.post(f"/api/v1/pos/tickets/{ticket_id}/reprint/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reprint_count"], 1)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(Sale.objects.count(), 1)

        again = self.client.post(f"/api/v1/pos/tickets/{ticket_id}/reprint/")
        self.assertEqual(again.data["reprint_count"], 2)

    def test_ticket_ids_never_reused_after_status_change(self):
        self.login_staff_a()
        sale = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        code = sale.data["tickets"][0]["ticket_code"]
        Ticket.objects.update(status=Ticket.Status.VOIDED)
        next_sale = self.sell(
            self.event_a.id,
            [{"category": self.cat_a_adult.id, "quantity": 1}],
            idempotency_key="after-void",
        )
        new_code = next_sale.data["tickets"][0]["ticket_code"]
        self.assertNotEqual(code, new_code)

    def test_audit_trail_recorded_for_sale(self):
        self.login_staff_a()
        sale = self.sell(self.event_a.id, [{"category": self.cat_a_adult.id, "quantity": 1}])
        self.login_admin_a()
        logs = self.client.get("/api/v1/admin/audit-logs/?action=sale.created")
        actions = [log["action"] for log in logs.data["results"]]
        self.assertIn("sale.created", actions)


class ConcurrentSaleTests(TransactionTestCase):
    """Threaded sales against the shared sequence must never collide."""

    def setUp(self):
        self.base = APITestBase()
        self.base.setUp()

    def _sell_in_thread(self, index):
        from rest_framework.test import APIClient

        client = APIClient()
        try:
            login = client.post(
                "/api/v1/auth/login/",
                {"tenant_code": "AAAA", "username": "ravi", "password": "StaffPass123!"},
                format="json",
            )
            token = login.data["access"]
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.post(
                "/api/v1/pos/sales/",
                {
                    "event": self.base.event_a.id,
                    "items": [{"category": self.base.cat_a_adult.id, "quantity": 1}],
                },
                format="json",
                headers={"Idempotency-Key": f"thread-{index}"},
            )
            return response
        finally:
            # Close this thread's DB connection so Windows can delete the
            # shared test database at teardown.
            from django.db import connections

            connections.close_all()

    def tearDown(self):
        for conn in connections.all():
            conn.close()

    def test_concurrent_sales_get_distinct_sequences(self):
        with ThreadPoolExecutor(max_workers=5) as executor:
            responses = list(executor.map(self._sell_in_thread, range(5)))

        for response in responses:
            self.assertEqual(response.status_code, 201, getattr(response, "data", None))

        tickets = Ticket.objects.order_by("sequence_number")
        seqs = [t.sequence_number for t in tickets]
        self.assertEqual(seqs, [1, 2, 3, 4, 5])
        codes = {t.ticket_code for t in tickets}
        self.assertEqual(len(codes), 5)
        sequence = TicketSequence.objects.get(
            tenant=self.base.tenant_a, event=self.base.event_a
        )
        self.assertEqual(sequence.last_number, 5)

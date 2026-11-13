from datetime import timedelta

from django.utils import timezone

from apps.accounts.models import User
from apps.events.models import Event
from apps.staff.models import StaffProfile

from .base import APITestBase

MANUAL_URL = "/api/v1/admin/tickets/manual/"


class ManualTicketTests(APITestBase):
    def issue(self, payload, key="manual-1"):
        return self.client.post(
            MANUAL_URL, payload, format="json", headers={"Idempotency-Key": key}
        )

    def test_admin_issues_as_self_without_assignment(self):
        self.login_admin_a()
        response = self.issue(
            {
                "event": self.event_a.id,
                "items": [{"category": self.cat_a_adult.id, "quantity": 2}],
            }
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["source"], "manual")
        self.assertEqual(response.data["gross_total"], "0.00")
        self.assertEqual(response.data["staff_code"], "ADMIN")
        self.assertEqual(response.data["staff_name"], "admin_a")
        self.assertEqual(len(response.data["tickets"]), 2)

        holder = StaffProfile.objects.get(tenant=self.tenant_a, user=self.admin_a_user)
        self.assertTrue(holder.is_admin_holder)
        self.assertFalse(holder.assignments.exists())

    def test_admin_can_issue_on_behalf_of_assigned_staff(self):
        self.login_admin_a()
        response = self.issue(
            {
                "event": self.event_a.id,
                "staff": self.staff_a.id,
                "items": [{"category": self.cat_a_adult.id, "quantity": 1}],
            }
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["staff_code"], "ST012")

    def test_staff_holder_still_requires_assignment(self):
        unassigned_user = User.objects.create_user(
            username="unassigned", password="Passw0rd!123"
        )
        unassigned = StaffProfile.objects.create(
            tenant=self.tenant_a,
            user=unassigned_user,
            staff_code="ST099",
            display_name="Unassigned",
        )
        self.login_admin_a()
        response = self.issue(
            {
                "event": self.event_a.id,
                "staff": unassigned.id,
                "items": [{"category": self.cat_a_adult.id, "quantity": 1}],
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "STAFF_NOT_ASSIGNED")

    def test_inactive_event_rejected_for_self_issue(self):
        now = timezone.now()
        draft = Event.objects.create(
            tenant=self.tenant_a,
            code="EVDR",
            name="Draft",
            start_at=now,
            end_at=now + timedelta(days=1),
            status=Event.Status.DRAFT,
            created_by=self.admin_a_user,
        )
        self.login_admin_a()
        response = self.issue(
            {
                "event": draft.id,
                "items": [{"category": self.cat_a_adult.id, "quantity": 1}],
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "EVENT_NOT_SELLABLE")

    def test_pos_staff_cannot_issue_manual_tickets(self):
        self.login_staff_a()
        response = self.issue(
            {
                "event": self.event_a.id,
                "items": [{"category": self.cat_a_adult.id, "quantity": 1}],
            }
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_holder_hidden_from_staff_management(self):
        self.login_admin_a()
        self.issue(
            {
                "event": self.event_a.id,
                "items": [{"category": self.cat_a_adult.id, "quantity": 1}],
            }
        )
        holder = StaffProfile.objects.get(tenant=self.tenant_a, user=self.admin_a_user)

        listing = self.client.get("/api/v1/admin/staff/")
        self.assertEqual(listing.status_code, 200)
        listed_ids = [row["id"] for row in listing.data["results"]]
        self.assertNotIn(holder.id, listed_ids)

        detail = self.client.get(f"/api/v1/admin/staff/{holder.id}/")
        self.assertEqual(detail.status_code, 404)

    def test_replay_of_self_issue_creates_no_extra_tickets(self):
        self.login_admin_a()
        payload = {
            "event": self.event_a.id,
            "items": [{"category": self.cat_a_adult.id, "quantity": 1}],
        }
        first = self.issue(payload, key="replay-key")
        replay = self.issue(payload, key="replay-key")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.data["replayed"])
        self.assertEqual(len(replay.data["tickets"]), 1)

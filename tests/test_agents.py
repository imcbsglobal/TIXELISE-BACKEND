from django.utils import timezone

from apps.agents.models import Agent
from apps.sales.models import Sale

from .base import APITestBase

AGENTS_URL = "/api/v1/admin/agents/"
MANUAL_URL = "/api/v1/admin/tickets/manual/"
REPORT_URL = "/api/v1/admin/reports/agents/"


class AgentMasterTests(APITestBase):
    def test_create_agent_uppercases_code(self):
        self.login_admin_a()
        response = self.client.post(
            AGENTS_URL,
            {"code": "ag002", "name": "Field Agent", "place": "North Town"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["code"], "AG002")
        self.assertEqual(response.data["status"], "active")
        self.assertEqual(response.data["created_by"], self.admin_a_user.id)

        agent = Agent.objects.get(pk=response.data["id"])
        self.assertEqual(agent.tenant, self.tenant_a)

    def test_duplicate_code_rejected_per_tenant(self):
        self.login_admin_a()
        response = self.client.post(
            AGENTS_URL,
            {"code": "AG001", "name": "Duplicate", "place": "North Town"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("code", response.data["error"]["message"])

    def test_agents_are_tenant_scoped(self):
        self.login_admin_a()
        listing = self.client.get(AGENTS_URL)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([row["code"] for row in listing.data["results"]], ["AG001"])
        self.assertEqual(listing.data["results"][0]["name"], "Agent A")

        detail = self.client.get(f"{AGENTS_URL}{self.agent_b.id}/")
        self.assertEqual(detail.status_code, 404)

        self.login_admin_b()
        listing = self.client.get(AGENTS_URL)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([row["name"] for row in listing.data["results"]], ["Agent B"])

    def test_status_toggle_and_filter(self):
        self.login_admin_a()
        response = self.client.post(
            f"{AGENTS_URL}{self.agent_a.id}/status/",
            {"status": "inactive"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "inactive")

        active = self.client.get(f"{AGENTS_URL}?status=active")
        self.assertEqual(active.data["results"], [])

        inactive = self.client.get(f"{AGENTS_URL}?status=inactive")
        self.assertEqual([row["id"] for row in inactive.data["results"]], [self.agent_a.id])

    def test_delete_agent_without_sales(self):
        self.login_admin_a()
        response = self.client.delete(f"{AGENTS_URL}{self.agent_a.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["deleted"])
        self.assertFalse(Agent.objects.filter(pk=self.agent_a.id).exists())

    def test_delete_agent_with_sales_blocked(self):
        self.login_admin_a()
        issued = self.client.post(
            MANUAL_URL,
            {
                "event": self.event_a.id,
                "agent": self.agent_a.id,
                "items": [{"category": self.cat_a_adult.id, "quantity": 1}],
            },
            format="json",
            headers={"Idempotency-Key": "agent-delete-sale"},
        )
        self.assertEqual(issued.status_code, 201, issued.content)

        response = self.client.delete(f"{AGENTS_URL}{self.agent_a.id}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Agent.objects.filter(pk=self.agent_a.id).exists())


class AgentReportTests(APITestBase):
    def issue(self, payload, key):
        return self.client.post(
            MANUAL_URL, payload, format="json", headers={"Idempotency-Key": key}
        )

    def test_report_counts_only_attributed_sales(self):
        self.login_admin_a()
        attributed = self.issue(
            {
                "event": self.event_a.id,
                "agent": self.agent_a.id,
                "items": [{"category": self.cat_a_adult.id, "quantity": 2}],
            },
            "agent-report-1",
        )
        self.assertEqual(attributed.status_code, 201, attributed.content)

        unattributed = self.issue(
            {
                "event": self.event_a.id,
                "items": [{"category": self.cat_a_child.id, "quantity": 1}],
            },
            "agent-report-2",
        )
        self.assertEqual(unattributed.status_code, 201, unattributed.content)

        today = timezone.localdate().isoformat()
        response = self.client.get(
            f"{REPORT_URL}?date_from={today}&date_to={today}"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["totals"]["agents_with_sales"], 1)
        self.assertEqual(response.data["totals"]["transactions"], 1)
        self.assertEqual(response.data["totals"]["tickets"], 2)
        self.assertEqual(response.data["totals"]["gross"], "998.00")
        self.assertEqual(response.data["totals"]["total"], "998.00")

        rows = {row["agent_code"]: row for row in response.data["agents"]}
        self.assertIn("AG001", rows)
        self.assertEqual(rows["AG001"]["transactions"], 1)
        self.assertEqual(rows["AG001"]["tickets"], 2)
        self.assertEqual(rows["AG001"]["gross"], "998.00")

    def test_inactive_agent_keeps_history(self):
        self.login_admin_a()
        issued = self.issue(
            {
                "event": self.event_a.id,
                "agent": self.agent_a.id,
                "items": [{"category": self.cat_a_adult.id, "quantity": 1}],
            },
            "agent-report-inactive",
        )
        self.assertEqual(issued.status_code, 201, issued.content)

        Agent.objects.filter(pk=self.agent_a.pk).update(status=Agent.Status.INACTIVE)
        today = timezone.localdate().isoformat()
        response = self.client.get(
            f"{REPORT_URL}?date_from={today}&date_to={today}"
        )
        rows = {row["agent_code"]: row for row in response.data["agents"]}
        self.assertEqual(rows["AG001"]["status"], "inactive")
        self.assertEqual(rows["AG001"]["transactions"], 1)
        self.assertEqual(Sale.objects.get(pk=issued.data["id"]).agent, self.agent_a)

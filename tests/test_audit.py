from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.retention import prune_audit_logs
from apps.events.models import Event

from .base import APITestBase


class AuditIsolationTests(APITestBase):
    def test_tenant_admin_only_sees_own_tenant_logs(self):
        AuditLog.objects.create(tenant=self.tenant_a, action="tenant_a.action")
        AuditLog.objects.create(tenant=self.tenant_b, action="tenant_b.action")
        AuditLog.objects.create(tenant=None, action="platform.action")

        self.login_admin_a()
        response = self.client.get("/api/v1/admin/audit-logs/")
        self.assertEqual(response.status_code, 200)
        actions = [row["action"] for row in response.data["results"]]
        self.assertIn("tenant_a.action", actions)
        self.assertNotIn("tenant_b.action", actions)
        self.assertNotIn("platform.action", actions)

    def test_tenant_admin_b_cannot_see_tenant_a_logs(self):
        AuditLog.objects.create(tenant=self.tenant_a, action="tenant_a.action")

        self.login_admin_b()
        response = self.client.get("/api/v1/admin/audit-logs/")
        self.assertEqual(response.status_code, 200)
        actions = [row["action"] for row in response.data["results"]]
        self.assertNotIn("tenant_a.action", actions)


class AuditRetentionTests(APITestBase):
    def _make_old(self, action="old.action", days=30):
        log = AuditLog.objects.create(tenant=self.tenant_a, action=action)
        AuditLog.objects.filter(pk=log.pk).update(
            created_at=timezone.now() - timedelta(days=days)
        )
        return log

    def test_prune_deletes_only_old_audit_rows(self):
        old = self._make_old()
        recent = AuditLog.objects.create(tenant=self.tenant_a, action="recent.action")
        events_before = Event.objects.count()

        deleted = prune_audit_logs(days=21)

        self.assertEqual(deleted, 1)
        self.assertFalse(AuditLog.objects.filter(pk=old.pk).exists())
        self.assertTrue(AuditLog.objects.filter(pk=recent.pk).exists())
        self.assertEqual(Event.objects.count(), events_before)

    def test_dry_run_reports_without_deleting(self):
        old = self._make_old()

        count = prune_audit_logs(days=21, dry_run=True)

        self.assertEqual(count, 1)
        self.assertTrue(AuditLog.objects.filter(pk=old.pk).exists())

    def test_management_command_prunes_old_rows(self):
        old = self._make_old()

        call_command("prune_audit_logs", "--days", "21", stdout=StringIO())

        self.assertFalse(AuditLog.objects.filter(pk=old.pk).exists())

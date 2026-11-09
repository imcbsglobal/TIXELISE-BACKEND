from django.conf import settings
from django.core.management.base import BaseCommand

from apps.audit.retention import prune_audit_logs


class Command(BaseCommand):
    help = "Delete audit log rows older than the retention window (default 21 days)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help=f"Retention window in days (default {settings.AUDIT_LOG_RETENTION_DAYS}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many rows would be deleted without deleting them.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        count = prune_audit_logs(days=days, dry_run=dry_run)
        window = settings.AUDIT_LOG_RETENTION_DAYS if days is None else days
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: {count} audit row(s) older than {window} day(s) would be deleted."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deleted {count} audit row(s) older than {window} day(s)."
                )
            )

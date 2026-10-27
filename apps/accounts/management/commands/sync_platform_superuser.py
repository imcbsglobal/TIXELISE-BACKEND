from django.core.management.base import BaseCommand

from apps.accounts.services import sync_platform_superuser_from_external_api


class Command(BaseCommand):
    help = "Sync the local platform superuser account with the external Tixelise superuser API."

    def handle(self, *args, **options):
        synced = sync_platform_superuser_from_external_api()
        if synced:
            self.stdout.write(self.style.SUCCESS("Platform superuser account synced successfully."))
        else:
            self.stdout.write(self.style.WARNING("No active platform superuser data was available to sync."))

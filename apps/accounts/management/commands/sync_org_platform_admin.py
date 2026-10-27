from django.core.management.base import BaseCommand

from apps.accounts.management.commands.sync_platform_superuser import Command as SyncCommand


class Command(SyncCommand, BaseCommand):
    help = "Backward-compatible alias for the platform superuser sync command."

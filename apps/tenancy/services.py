"""
Permanent tenant deletion.

Tenant-owned rows use PROTECT foreign keys to the tenant and to each other
(tickets protect sales/events/staff/categories, sales protect events/staff,
etc.), so a plain ``tenant.delete()`` raises ProtectedError as soon as any
business data exists. Delete children in dependency-safe order inside one
transaction instead.

Global User rows are identities, not tenant data, so one is removed only when
this deletion leaves it with no membership anywhere and no staff profile;
platform admins are never touched. Audit history survives with tenant=NULL and
actor=NULL — the username is already captured in ``actor_label``.
"""
from django.db import transaction
from django.db.models.deletion import ProtectedError, RestrictedError

from apps.core.exceptions import Conflict

from .models import Tenant, TenantMembership


def _purge(model, tenant):
    # Use the base manager so the thread-local tenant context can never widen
    # or narrow the query; the explicit tenant filter is the only scope.
    return model._base_manager.filter(tenant=tenant).delete()[0]


def delete_tenant(tenant):
    """Permanently delete a tenant and all tenant-owned business data.

    Returns a mapping of ``app_label.Model`` to deleted row count.
    Raises ``Conflict`` (409) if a protected relation is unexpectedly left.
    """
    from django.contrib.auth import get_user_model

    from apps.assignments.models import StaffEventAssignment
    from apps.catalog.models import EventPrice, TicketCategory, TicketTemplate
    from apps.events.models import Event
    from apps.sales.models import IdempotencyRecord, Sale
    from apps.staff.models import StaffProfile
    from apps.ticketing.models import Ticket, TicketSequence

    counts = {}
    try:
        with transaction.atomic():
            locked = Tenant.objects.select_for_update().get(pk=tenant.pk)

            # Read the links first: memberships are the only edge from a tenant
            # to the identities it introduced, and they are purged below.
            member_ids = list(
                TenantMembership._base_manager.filter(tenant=locked).values_list(
                    "user_id", flat=True
                )
            )

            # Order matters: rows that PROTECT other rows must go first.
            for model in (
                Ticket,
                Sale,
                TicketSequence,
                StaffEventAssignment,
                EventPrice,
                TicketTemplate,
                StaffProfile,
                TicketCategory,
                Event,
                IdempotencyRecord,
            ):
                counts[model._meta.label] = _purge(model, locked)

            counts[TenantMembership._meta.label] = _purge(TenantMembership, locked)
            locked.delete()

            # An identity dies with the tenant only when nothing else still
            # points at it. Its memberships are gone by now, so any surviving
            # one belongs to another tenant; StaffProfile.user is PROTECT, so a
            # leftover profile would abort the whole deletion.
            User = get_user_model()
            orphaned = (
                User.objects.filter(
                    pk__in=member_ids, is_platform_admin=False, is_superuser=False
                )
                .filter(memberships__isnull=True, staff_profiles__isnull=True)
                .distinct()
            )
            counts[User._meta.label] = orphaned.delete()[0]
    except (ProtectedError, RestrictedError) as exc:
        raise Conflict(
            "Tenant still has protected records and could not be deleted. "
            "Please contact support."
        ) from exc

    return counts

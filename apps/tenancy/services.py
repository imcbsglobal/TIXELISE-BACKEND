"""
Permanent tenant deletion.

Tenant-owned rows use PROTECT foreign keys to the tenant and to each other
(tickets protect sales/events/staff/categories, sales protect events/staff,
etc.), so a plain ``tenant.delete()`` raises ProtectedError as soon as any
business data exists. Delete children in dependency-safe order inside one
transaction instead.

Global User rows and audit history are deliberately preserved; memberships
cascade with the tenant and audit logs keep their history with tenant=NULL.
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
    except (ProtectedError, RestrictedError) as exc:
        raise Conflict(
            "Tenant still has protected records and could not be deleted. "
            "Please contact support."
        ) from exc

    return counts

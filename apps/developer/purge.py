"""Hard delete of one tenant's data, driveable from the Developer page.

This exists so a developer resetting a test organization does not have to reach
for SQL. Nothing here is soft: rows are removed for good, and only the tenant in
the request is ever touched - every query carries ``tenant=`` explicitly on top
of the auto-scoping manager.

Two groups of data are on offer:

``tickets`` / ``sales``
    The trading history, plus the ticket-number counters.

``masters``
    The configuration a sale was built on: staff assignments, prices, ticket
    types and events. This one is deliberately gated - a sale and a ticket both
    point at an event and at a ticket type, so those rows have to be gone first.

Deliberately out of reach: staff profiles, the tax setting, users, the tenant
itself and the audit log. Wiping those would leave a tenant nobody can sign in
to or configure.
"""

from django.db import transaction
from django.db.models import Max

from apps.assignments.models import StaffEventAssignment
from apps.catalog.models import EventPrice, TicketCategory
from apps.core.exceptions import ValidationError
from apps.events.models import Event
from apps.sales.models import IdempotencyRecord, Sale, SaleItem
from apps.ticketing.models import Ticket, TicketSequence

TICKETS = "tickets"
SALES = "sales"
NUMBERING = "numbering"
MASTERS = "masters"
SCOPES = (TICKETS, SALES, NUMBERING, MASTERS)


def _count(per_model, model):
    return per_model.get(model._meta.label, 0)


def summarize(tenant):
    """How much there is to delete, so the UI can show the damage first."""
    sales = Sale.objects.filter(tenant=tenant)
    return {
        "tickets": Ticket.objects.filter(tenant=tenant).count(),
        "sales": sales.count(),
        "sale_items": SaleItem.objects.filter(sale__tenant=tenant).count(),
        "sequences": TicketSequence.objects.filter(tenant=tenant).count(),
        "pos_sales": sales.filter(source=Sale.Source.POS).count(),
        "manual_sales": sales.filter(source=Sale.Source.MANUAL).count(),
        "events": Event.objects.filter(tenant=tenant).count(),
        "categories": TicketCategory.objects.filter(tenant=tenant).count(),
        "prices": EventPrice.objects.filter(tenant=tenant).count(),
        "assignments": StaffEventAssignment.objects.filter(tenant=tenant).count(),
    }


def _reset_numbering(tenant):
    """Restart ticket numbers at 1, without ever colliding with a kept ticket.

    The counter holds the last number handed out, so putting it back to the
    highest number still in use is exactly "continue from here". With every
    ticket deleted that is 0, and the next ticket is #1 again.
    """
    reset = 0
    for sequence in TicketSequence.objects.filter(tenant=tenant):
        highest = (
            Ticket.objects.filter(tenant=tenant, event=sequence.event).aggregate(
                highest=Max("sequence_number")
            )["highest"]
            or 0
        )
        if sequence.last_number != highest:
            sequence.last_number = highest
            sequence.save(update_fields=["last_number", "updated_at"])
        reset += 1
    return reset


def _delete_masters(tenant, deleted):
    """Assignments, prices, counters, ticket types, then events.

    Cold order is the only one that works: a price protects its ticket type, an
    event protects nothing but is protected by tickets, sales and the number
    counters, so those are cleared first.
    """
    _, per_model = StaffEventAssignment.objects.filter(tenant=tenant).delete()
    deleted["assignments"] = _count(per_model, StaffEventAssignment)

    _, per_model = EventPrice.objects.filter(tenant=tenant).delete()
    deleted["prices"] = _count(per_model, EventPrice)

    # An event cannot go while a counter points at it, and with every ticket gone
    # there is nothing left for the counters to protect.
    _, per_model = TicketSequence.objects.filter(tenant=tenant).delete()
    deleted["sequences"] = _count(per_model, TicketSequence)

    _, per_model = TicketCategory.objects.filter(tenant=tenant).delete()
    deleted["categories"] = _count(per_model, TicketCategory)

    _, per_model = Event.objects.filter(tenant=tenant).delete()
    deleted["events"] = _count(per_model, Event)


@transaction.atomic
def purge(tenant, scopes):
    """Delete the requested kinds of data for ``tenant`` and report the counts.

    A sale cannot be deleted while a ticket still points at it (the foreign key
    is PROTECT), so ticking sales takes the tickets with it. The response says so
    in ``implied`` rather than letting the caller wonder.
    """
    wanted = set(scopes)
    implied = []

    if SALES in wanted and TICKETS not in wanted:
        wanted.add(TICKETS)
        implied.append(TICKETS)

    if MASTERS in wanted:
        # Refuse before anything is removed rather than half-failing on a
        # ProtectedError partway through. The caller ticks the history too.
        remaining = (
            Ticket.objects.filter(tenant=tenant).count()
            if TICKETS not in wanted
            else 0
        ) or (Sale.objects.filter(tenant=tenant).count() if SALES not in wanted else 0)
        if remaining:
            raise ValidationError(
                {
                    "scopes": "Delete tickets and sales as well before events and "
                    "ticket types: existing sales and tickets still point at them."
                }
            )

    deleted = {
        "tickets": 0,
        "sales": 0,
        "sale_items": 0,
        "sequences": 0,
        "events": 0,
        "categories": 0,
        "prices": 0,
        "assignments": 0,
    }

    if TICKETS in wanted:
        _, per_model = Ticket.objects.filter(tenant=tenant).delete()
        deleted["tickets"] = _count(per_model, Ticket)

    if SALES in wanted:
        # These rows answer "what did this key return?" for a retried sale. Left
        # behind they would resolve to a sale that no longer exists.
        IdempotencyRecord.objects.filter(tenant=tenant).delete()
        _, per_model = Sale.objects.filter(tenant=tenant).delete()
        deleted["sales"] = _count(per_model, Sale)
        deleted["sale_items"] = _count(per_model, SaleItem)

    if MASTERS in wanted:
        _delete_masters(tenant, deleted)
    elif NUMBERING in wanted:
        deleted["sequences"] = _reset_numbering(tenant)

    # What was left in place, so the UI can say "numbering kept" rather than
    # leaving the caller to infer it from an empty count.
    remaining = summarize(tenant)
    skipped = {
        scope: remaining[key]
        for scope, key in (
            (TICKETS, "tickets"),
            (SALES, "sales"),
            (MASTERS, "events"),
        )
        if scope not in wanted
    }

    return {"deleted": deleted, "implied": implied, "skipped": skipped}

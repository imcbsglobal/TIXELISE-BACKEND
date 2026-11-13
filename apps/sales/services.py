"""
Transactional sale creation and ticket issuance (MD §11).

Order of operations:
  validate assignment -> validate selling window -> validate categories/prices
  -> idempotency check -> BEGIN TX -> lock TicketSequence -> allocate numbers
  -> create Sale + SaleItems + Tickets + IdempotencyRecord -> audit -> COMMIT
"""
import hashlib
import json
import secrets
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from apps.assignments.models import StaffEventAssignment
from apps.audit.services import record_audit
from apps.catalog.models import EventPrice, TicketCategory
from apps.core.exceptions import (
    AssignmentRequired,
    BadRequest,
    CategoryNotAllowed,
    EventNotSellable,
    IdempotencyConflict,
    NotFound,
    PriceUnavailable,
    SalesWindowClosed,
)
from apps.events.models import Event
from apps.staff.models import StaffProfile
from apps.taxation.services import apply_tax_to_line, resolve_tax_for_event
from apps.ticketing.models import Ticket, TicketSequence

from .models import IdempotencyRecord, Sale, SaleItem

IDEMPOTENCY_TTL_DAYS = 7


def _is_transient(exc) -> bool:
    if isinstance(exc, IntegrityError):
        return True
    message = str(exc).lower()
    return "locked" in message or "busy" in message


def request_fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_event(tenant_id, event_id) -> Event:
    try:
        event = Event.objects.get(pk=event_id, tenant_id=tenant_id)
    except Event.DoesNotExist:
        raise NotFound("Event not found.")
    return event


def _check_assignment(tenant_id, staff, event, categories):
    assignment = (
        StaffEventAssignment.objects.filter(
            tenant_id=tenant_id, staff=staff, event=event
        )
        .order_by("-created_at")
        .first()
    )
    if assignment is None or not assignment.is_usable_at():
        raise AssignmentRequired()

    if assignment.restrict_categories:
        allowed_ids = set(assignment.allowed_categories.values_list("id", flat=True))
        for category in categories:
            if category.id not in allowed_ids:
                raise CategoryNotAllowed()
    return assignment


def _load_categories(tenant, items_data):
    """Load category objects and validate quantity/duplicates/active state."""
    categories = []
    seen = set()
    for item in items_data:
        category_id = item["category_id"]
        quantity = item["quantity"]

        if quantity < 1 or quantity > 100:
            raise BadRequest(
                detail="Quantity must be between 1 and 100.",
                code="INVALID_QUANTITY",
            )
        if category_id in seen:
            raise BadRequest(
                detail="Duplicate category in request.",
                code="DUPLICATE_CATEGORY",
            )
        seen.add(category_id)

        try:
            category = TicketCategory.objects.get(pk=category_id, tenant=tenant)
        except TicketCategory.DoesNotExist:
            raise NotFound("Ticket category not found.")
        if category.status != TicketCategory.Status.ACTIVE:
            raise CategoryNotAllowed("This ticket category is inactive.")
        categories.append(category)
    return categories


def _resolve_prices(tenant, event, categories, quantities):
    """Server-side unit prices; raises PriceUnavailable when missing."""
    priced = []
    for category, quantity in zip(categories, quantities):
        try:
            price = EventPrice.objects.get(
                tenant=tenant, event=event, category=category,
                status=EventPrice.Status.ACTIVE,
            )
        except EventPrice.DoesNotExist:
            raise PriceUnavailable()
        if not price.is_currently_effective():
            raise PriceUnavailable("This price is not currently effective.")
        priced.append((category, quantity, price.amount))
    return priced


def _check_idempotency(tenant, actor, idempotency_key, fingerprint):
    existing = IdempotencyRecord.objects.filter(
        tenant=tenant, actor=actor, idempotency_key=idempotency_key
    ).first()
    if existing is not None:
        if existing.request_hash != fingerprint:
            raise IdempotencyConflict()
        if existing.sale_id is None:
            raise IdempotencyConflict("Original request did not complete.")
        return existing
    return None


def _allocate_sequence(tenant, event, count) -> list[int]:
    """Atomically allocate `count` sequence numbers for (tenant, event)."""
    sequence, _ = TicketSequence.objects.get_or_create(
        tenant=tenant, event=event, defaults={"last_number": 0}
    )
    locked = TicketSequence.objects.select_for_update().get(pk=sequence.pk)
    start = locked.last_number + 1
    locked.last_number += count
    locked.save(update_fields=["last_number", "updated_at"])
    return list(range(start, start + count))


def build_ticket_code(tenant, staff, event, issued_at, sequence_number) -> str:
    timestamp = issued_at.strftime("%Y%m%dT%H%M%SZ")
    return (
        f"{tenant.code}-{staff.staff_code}-{event.code}-"
        f"{timestamp}-{sequence_number:06d}"
    )


def create_sale(*, tenant, user, staff, event_id, items_data, idempotency_key):
    """
    Full sale creation. Returns {"sale": Sale, "tickets": [...],
    "replayed": bool}. Raises TixeliseAPIException subclasses on any
    validation failure.
    """
    if not idempotency_key or len(idempotency_key) > 128:
        raise BadRequest(
            detail="A valid Idempotency-Key header (max 128 chars) is required.",
            code="IDEMPOTENCY_KEY_REQUIRED",
        )

    event = _load_event(tenant.id, event_id)

    if event.status != Event.Status.ACTIVE:
        raise EventNotSellable(f"Event is {event.status}.")
    if not event.is_within_sales_window():
        raise SalesWindowClosed()

    if items_data is None or len(items_data) == 0:
        raise BadRequest(detail="At least one item is required.", code="EMPTY_SALE")

    # MD §11.1 order: assignment -> selling window -> category/price.
    categories = _load_categories(tenant, items_data)
    _check_assignment(tenant.id, staff, event, categories)
    quantities = [item["quantity"] for item in items_data]
    priced_items = _resolve_prices(tenant, event, categories, quantities)

    fingerprint = request_fingerprint(
        {"event": event.id, "items": items_data}
    )

    replay = _check_idempotency(tenant, user, idempotency_key, fingerprint)
    if replay is not None:
        sale = replay.sale
        return {
            "sale": sale,
            "tickets": list(sale.tickets.select_related("category", "event", "staff")),
            "replayed": True,
        }

    # Tax is resolved once, from the event's own setting or the locally stored
    # company setting - never from the central master - so committing a sale
    # cannot depend on a third party.
    tax = resolve_tax_for_event(event, tenant)
    lines = [
        (
            category,
            quantity,
            unit_price,
            *apply_tax_to_line(unit_price=unit_price, quantity=quantity, tax=tax),
        )
        for category, quantity, unit_price in priced_items
    ]
    total_tickets = sum(quantity for _, quantity, _, _, _ in lines)
    gross_total = sum((line[3] for line in lines), Decimal("0.00"))
    tax_total = sum((line[4] for line in lines), Decimal("0.00"))
    now = timezone.now()

    max_attempts = 6
    for attempt in range(max_attempts):
        try:
            with transaction.atomic():
                sequence_numbers = _allocate_sequence(tenant, event, total_tickets)

                sale = Sale.objects.create(
                    tenant=tenant,
                    event=event,
                    staff=staff,
                    sale_reference=(
                        f"{tenant.code}-S-{secrets.token_hex(4).upper()}"
                    ),
                    gross_total=gross_total,
                    tax_total=tax_total,
                    currency=tenant.currency,
                    created_by=user,
                    status=Sale.Status.COMPLETED,
                )

                tickets = []
                seq_iter = iter(sequence_numbers)
                for category, quantity, unit_price, line_total, tax_amount in lines:
                    SaleItem.objects.create(
                        sale=sale,
                        category=category,
                        quantity=quantity,
                        unit_price_snapshot=unit_price,
                        line_total=line_total,
                        tax_rate_snapshot=tax.rate if tax else Decimal("0.00"),
                        tax_code=tax.code if tax else "",
                        tax_name=tax.name if tax else "",
                        tax_amount=tax_amount,
                        hsn_code=tax.hsn_code if tax else "",
                    )
                    for _ in range(quantity):
                        seq = next(seq_iter)
                        code = build_ticket_code(tenant, staff, event, now, seq)
                        tickets.append(
                            Ticket.objects.create(
                                tenant=tenant,
                                ticket_code=code,
                                event=event,
                                staff=staff,
                                sale=sale,
                                category=category,
                                sequence_number=seq,
                                status=Ticket.Status.ISSUED,
                            )
                        )

                IdempotencyRecord.objects.create(
                    tenant=tenant,
                    actor=user,
                    idempotency_key=idempotency_key,
                    request_hash=fingerprint,
                    sale=sale,
                    status=IdempotencyRecord.Status.COMPLETED,
                    expires_at=now + timedelta(days=IDEMPOTENCY_TTL_DAYS),
                )

                record_audit(
                    actor=user,
                    tenant=tenant,
                    action="sale.created",
                    target_type="sale",
                    target_id=sale.id,
                    metadata={
                        "sale_reference": sale.sale_reference,
                        "event": event.code,
                        "staff": staff.staff_code,
                        "tickets": len(tickets),
                        "gross_total": str(gross_total),
                        "tax_total": str(tax_total),
                    },
                )

                return {"sale": sale, "tickets": tickets, "replayed": False}
        except (IntegrityError, OperationalError) as exc:
            # Concurrent request won the unique-scope race, or SQLite briefly
            # held the write lock — both are safe to retry; unique constraints
            # prevent duplicate issuance. SQLite can also return "locked"
            # immediately on read->write upgrades (busy handler skipped), so
            # back off exponentially and retry the whole transaction.
            if not _is_transient(exc):
                raise
            if attempt == max_attempts - 1:
                break
            import time

            time.sleep(0.05 * (2**attempt))
            continue

    raise BadRequest(
        detail="Could not complete the sale due to a conflict. Please retry.",
        code="SALE_CONFLICT",
    )



def _load_manual_staff(tenant, staff_id) -> StaffProfile:
    try:
        staff = StaffProfile.objects.get(pk=staff_id, tenant_id=tenant.id)
    except StaffProfile.DoesNotExist:
        raise NotFound("Staff member not found.")
    if staff.status != StaffProfile.Status.ACTIVE:
        raise BadRequest(detail="This staff member is inactive.", code="STAFF_INACTIVE")
    return staff


def _unique_admin_staff_code(tenant) -> str:
    """A tenant-unique staff code for the admin holder, based on ``ADMIN``."""
    base = "ADMIN"
    taken = set(
        StaffProfile.objects.filter(tenant=tenant).values_list("staff_code", flat=True)
    )
    if base not in taken:
        return base
    suffix = 2
    while f"{base}{suffix}" in taken:
        suffix += 1
    return f"{base}{suffix}"


def get_admin_holder(tenant, user) -> StaffProfile:
    """The StaffProfile that owns tickets an admin issues as themselves.

    Created lazily on first use. It is a ticket owner only: no POS membership is
    added and the admin keeps the ``tenant_admin`` role, so the profile is
    marked ``is_admin_holder`` and hidden from staff management. Reuses an
    existing profile for the same user when one is present.
    """
    profile = StaffProfile.objects.filter(tenant=tenant, user=user).first()
    if profile is not None:
        return profile
    display_name = user.get_full_name().strip() or user.username
    try:
        return StaffProfile.objects.create(
            tenant=tenant,
            user=user,
            staff_code=_unique_admin_staff_code(tenant),
            display_name=display_name,
            email=user.email or "",
            status=StaffProfile.Status.ACTIVE,
            is_admin_holder=True,
            created_by=user,
        )
    except IntegrityError:
        # A concurrent request created it first (unique tenant + user).
        return StaffProfile.objects.get(tenant=tenant, user=user)


def _manual_assignment(tenant, staff, event):
    assignment = (
        StaffEventAssignment.objects.filter(
            tenant_id=tenant.id, staff=staff, event=event
        )
        .order_by("-created_at")
        .first()
    )
    if assignment is None or assignment.status != StaffEventAssignment.Status.ACTIVE:
        raise BadRequest(
            detail="This staff member is not assigned to the event.",
            code="STAFF_NOT_ASSIGNED",
        )
    return assignment


def issue_manual_tickets(
    *, tenant, user, staff_id=None, event_id, items_data, idempotency_key
):
    """
    Manual tickets issued by an admin, charged exactly like a POS sale.

    The opening price is resolved server-side and tax is applied per line, so
    the sale stores a real ``gross_total``/``tax_total`` and the tickets count
    as revenue and transactions in every report. It is tagged source=manual
    only so the Manual Tickets history can list these entries separately.
    Sequence numbers come from the shared per-event counter, so manual codes
    interleave with POS codes and never collide.

    ``staff_id`` is optional: when it is ``None`` the tickets belong to the
    issuing admin, via a lazily created holder profile, and no event assignment
    is required. When a staff id is supplied the existing rules apply unchanged
    -- the staff member must be active and assigned to the event.
    """
    if not idempotency_key or len(idempotency_key) > 128:
        raise BadRequest(
            detail="A valid Idempotency-Key header (max 128 chars) is required.",
            code="IDEMPOTENCY_KEY_REQUIRED",
        )

    event = _load_event(tenant.id, event_id)
    if event.status != Event.Status.ACTIVE:
        raise EventNotSellable(f"Event is {event.status}.")
    if items_data is None or len(items_data) == 0:
        raise BadRequest(detail="At least one item is required.", code="EMPTY_SALE")

    categories = _load_categories(tenant, items_data)

    if staff_id is None:
        # The admin issues as themselves: no assignment is required and every
        # active category is allowed.
        staff = get_admin_holder(tenant, user)
    else:
        staff = _load_manual_staff(tenant, staff_id)
        assignment = _manual_assignment(tenant, staff, event)
        if assignment.restrict_categories:
            allowed_ids = set(
                assignment.allowed_categories.values_list("id", flat=True)
            )
            for category in categories:
                if category.id not in allowed_ids:
                    raise CategoryNotAllowed(
                        "This ticket category is not allowed for this staff member."
                    )

    quantities = [item["quantity"] for item in items_data]
    priced_items = _resolve_prices(tenant, event, categories, quantities)

    fingerprint = request_fingerprint(
        {
            "event": event.id,
            "staff": staff.id,
            "items": items_data,
            "source": Sale.Source.MANUAL,
        }
    )

    replay = _check_idempotency(tenant, user, idempotency_key, fingerprint)
    if replay is not None:
        sale = replay.sale
        return {
            "sale": sale,
            "tickets": list(sale.tickets.select_related("category", "event", "staff")),
            "replayed": True,
        }

    tax = resolve_tax_for_event(event, tenant)
    lines = [
        (
            category,
            quantity,
            unit_price,
            *apply_tax_to_line(unit_price=unit_price, quantity=quantity, tax=tax),
        )
        for category, quantity, unit_price in priced_items
    ]
    total_tickets = sum(quantity for _, quantity, _, _, _ in lines)
    gross_total = sum((line[3] for line in lines), Decimal("0.00"))
    tax_total = sum((line[4] for line in lines), Decimal("0.00"))
    zero = Decimal("0.00")
    now = timezone.now()

    max_attempts = 6
    for attempt in range(max_attempts):
        try:
            with transaction.atomic():
                sequence_numbers = _allocate_sequence(tenant, event, total_tickets)

                sale = Sale.objects.create(
                    tenant=tenant,
                    event=event,
                    staff=staff,
                    sale_reference=f"{tenant.code}-M-{secrets.token_hex(4).upper()}",
                    gross_total=gross_total,
                    tax_total=tax_total,
                    refund_total=zero,
                    currency=tenant.currency,
                    created_by=user,
                    status=Sale.Status.COMPLETED,
                    source=Sale.Source.MANUAL,
                )

                tickets = []
                seq_iter = iter(sequence_numbers)
                for category, quantity, unit_price, line_total, tax_amount in lines:
                    SaleItem.objects.create(
                        sale=sale,
                        category=category,
                        quantity=quantity,
                        unit_price_snapshot=unit_price,
                        line_total=line_total,
                        tax_rate_snapshot=tax.rate if tax else Decimal("0.00"),
                        tax_code=tax.code if tax else "",
                        tax_name=tax.name if tax else "",
                        tax_amount=tax_amount,
                        hsn_code=tax.hsn_code if tax else "",
                    )
                    for _ in range(quantity):
                        seq = next(seq_iter)
                        code = build_ticket_code(tenant, staff, event, now, seq)
                        tickets.append(
                            Ticket.objects.create(
                                tenant=tenant,
                                ticket_code=code,
                                event=event,
                                staff=staff,
                                sale=sale,
                                category=category,
                                sequence_number=seq,
                                status=Ticket.Status.ISSUED,
                            )
                        )

                IdempotencyRecord.objects.create(
                    tenant=tenant,
                    actor=user,
                    idempotency_key=idempotency_key,
                    request_hash=fingerprint,
                    sale=sale,
                    status=IdempotencyRecord.Status.COMPLETED,
                    expires_at=now + timedelta(days=IDEMPOTENCY_TTL_DAYS),
                )

                record_audit(
                    actor=user,
                    tenant=tenant,
                    action="tickets.manual_issued",
                    target_type="sale",
                    target_id=sale.id,
                    metadata={
                        "sale_reference": sale.sale_reference,
                        "event": event.code,
                        "staff": staff.staff_code,
                        "tickets": len(tickets),
                        "gross_total": str(gross_total),
                        "tax_total": str(tax_total),
                        "categories": [c.code for c, _, _ in priced_items],
                        "codes": [t.ticket_code for t in tickets],
                    },
                )

                return {"sale": sale, "tickets": tickets, "replayed": False}
        except (IntegrityError, OperationalError) as exc:
            if not _is_transient(exc):
                raise
            if attempt == max_attempts - 1:
                break
            import time

            time.sleep(0.05 * (2**attempt))
            continue

    raise BadRequest(
        detail="Could not issue the tickets due to a conflict. Please retry.",
        code="SALE_CONFLICT",
    )

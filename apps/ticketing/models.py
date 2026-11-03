import uuid

from django.db import models

from apps.core.models import TenantOwnedModel


class TicketSequence(TenantOwnedModel):
    """
    One counter per (tenant, event) shared by all staff (MD §11.3).
    Allocation is performed with SELECT ... FOR UPDATE inside the sale
    transaction; the UNIQUE constraint is the final safety net.
    """

    event = models.ForeignKey(
        "events.Event", on_delete=models.PROTECT, related_name="ticket_sequences"
    )
    last_number = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tixelise_ticketing_ticketsequence"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "event"], name="uniq_tenant_event_sequence"
            )
        ]

    def __str__(self):
        return f"{self.tenant_id}/{self.event_id}: {self.last_number}"


class Ticket(TenantOwnedModel):
    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        VOIDED = "voided", "Voided"
        REFUNDED = "refunded", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket_code = models.CharField(max_length=120, unique=True)
    event = models.ForeignKey(
        "events.Event", on_delete=models.PROTECT, related_name="tickets"
    )
    staff = models.ForeignKey(
        "staff.StaffProfile", on_delete=models.PROTECT, related_name="tickets"
    )
    sale = models.ForeignKey(
        "sales.Sale", on_delete=models.PROTECT, related_name="tickets"
    )
    category = models.ForeignKey(
        "catalog.TicketCategory", on_delete=models.PROTECT, related_name="tickets"
    )
    sequence_number = models.BigIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ISSUED)
    issued_at = models.DateTimeField(auto_now_add=True)
    reprint_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "tixelise_ticketing_ticket"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "event", "sequence_number"],
                name="uniq_tenant_event_sequence_number",
            )
        ]
        ordering = ["-issued_at"]

    def __str__(self):
        return self.ticket_code

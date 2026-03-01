import uuid

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Interaction(TimeStampedModel):
    class Type(models.TextChoices):
        CALL = "call", "Call"
        MESSAGE = "message", "Message"
        EMAIL = "email", "Email"
        MEETING = "meeting", "Meeting"
        NOTE = "note", "Note"

    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"
        INTERNAL = "internal", "Internal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "users.Organization",
        on_delete=models.CASCADE,
        related_name="interactions",
    )
    lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.CASCADE,
        related_name="interactions",
    )
    deal = models.ForeignKey(
        "pipeline.Deal",
        on_delete=models.CASCADE,
        related_name="interactions",
        blank=True,
        null=True,
    )
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="created_interactions",
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    direction = models.CharField(
        max_length=20,
        choices=Direction.choices,
        default=Direction.INTERNAL,
    )
    subject = models.CharField(max_length=255, blank=True)
    content = models.TextField()
    outcome = models.CharField(max_length=255, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-occurred_at", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "lead", "occurred_at"]),
            models.Index(fields=["organization", "deal", "occurred_at"]),
            models.Index(fields=["organization", "type"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_type_display()} - {self.lead.full_name}"

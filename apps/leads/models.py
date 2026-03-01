import uuid

from django.db import models

from apps.core.models import SoftDeleteModel, TimeStampedModel


class LeadSource(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "users.Organization",
        on_delete=models.CASCADE,
        related_name="lead_sources",
    )
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_lead_source_name_per_organization",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Tag(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "users.Organization",
        on_delete=models.CASCADE,
        related_name="lead_tags",
    )
    name = models.CharField(max_length=80)
    color = models.CharField(max_length=7, default="#BC5C2D")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_tag_name_per_organization",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Lead(TimeStampedModel, SoftDeleteModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        QUALIFIED = "qualified", "Qualified"
        PROPOSAL = "proposal", "Proposal"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    class Temperature(models.TextChoices):
        COLD = "cold", "Cold"
        WARM = "warm", "Warm"
        HOT = "hot", "Hot"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "users.Organization",
        on_delete=models.CASCADE,
        related_name="leads",
    )
    assigned_to = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="assigned_leads",
        blank=True,
        null=True,
    )
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="created_leads",
    )
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    job_title = models.CharField(max_length=255, blank=True)
    source = models.ForeignKey(
        LeadSource,
        on_delete=models.SET_NULL,
        related_name="leads",
        blank=True,
        null=True,
    )
    tags = models.ManyToManyField(Tag, related_name="leads", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    temperature = models.CharField(
        max_length=10,
        choices=Temperature.choices,
        default=Temperature.COLD,
    )
    estimated_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes_summary = models.TextField(blank=True)
    last_interaction_at = models.DateTimeField(blank=True, null=True)
    next_action_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "assigned_to"]),
            models.Index(fields=["organization", "source"]),
            models.Index(fields=["organization", "deleted_at"]),
        ]

    def __str__(self) -> str:
        return self.full_name

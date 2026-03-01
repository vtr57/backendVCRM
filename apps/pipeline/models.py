import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Pipeline(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "users.Organization",
        on_delete=models.CASCADE,
        related_name="pipelines",
    )
    name = models.CharField(max_length=120)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_pipeline_name_per_organization",
            ),
            models.UniqueConstraint(
                fields=["organization"],
                condition=Q(is_default=True),
                name="uniq_default_pipeline_per_organization",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Stage(TimeStampedModel):
    class Kind(models.TextChoices):
        OPEN = "open", "Open"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.CASCADE,
        related_name="stages",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120)
    order = models.PositiveIntegerField()
    color = models.CharField(max_length=7, default="#BC5C2D")
    probability = models.PositiveSmallIntegerField(default=0)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.OPEN)
    wip_limit = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        ordering = ["order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["pipeline", "order"],
                name="uniq_stage_order_per_pipeline",
            ),
            models.UniqueConstraint(
                fields=["pipeline", "slug"],
                name="uniq_stage_slug_per_pipeline",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pipeline.name} - {self.name}"


class Deal(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "users.Organization",
        on_delete=models.CASCADE,
        related_name="deals",
    )
    lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.CASCADE,
        related_name="deals",
    )
    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.CASCADE,
        related_name="deals",
    )
    stage = models.ForeignKey(
        Stage,
        on_delete=models.PROTECT,
        related_name="deals",
    )
    owner = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="owned_deals",
        blank=True,
        null=True,
    )
    title = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    position = models.PositiveIntegerField(default=0)
    expected_close_date = models.DateField(blank=True, null=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    lost_reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="created_deals",
    )

    class Meta:
        ordering = ["stage__order", "position", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "pipeline"]),
            models.Index(fields=["organization", "stage"]),
            models.Index(fields=["organization", "owner"]),
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["organization", "closed_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    def sync_status_from_stage(self):
        if self.stage.kind == Stage.Kind.WON:
            self.status = self.Status.WON
            if self.closed_at is None:
                self.closed_at = timezone.now()
            self.lost_reason = ""
        elif self.stage.kind == Stage.Kind.LOST:
            self.status = self.Status.LOST
            if self.closed_at is None:
                self.closed_at = timezone.now()
        else:
            self.status = self.Status.OPEN
            self.closed_at = None
            self.lost_reason = ""


class StageMovement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "users.Organization",
        on_delete=models.CASCADE,
        related_name="stage_movements",
    )
    deal = models.ForeignKey(
        Deal,
        on_delete=models.CASCADE,
        related_name="movements",
    )
    from_stage = models.ForeignKey(
        Stage,
        on_delete=models.SET_NULL,
        related_name="movements_from",
        blank=True,
        null=True,
    )
    to_stage = models.ForeignKey(
        Stage,
        on_delete=models.CASCADE,
        related_name="movements_to",
    )
    moved_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="stage_movements",
        blank=True,
        null=True,
    )
    moved_at = models.DateTimeField(default=timezone.now)
    from_position = models.PositiveIntegerField(default=0)
    to_position = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-moved_at"]
        indexes = [
            models.Index(fields=["organization", "moved_at"]),
            models.Index(fields=["organization", "to_stage"]),
        ]

    def __str__(self) -> str:
        return f"{self.deal.title}: {self.from_stage_id} -> {self.to_stage_id}"

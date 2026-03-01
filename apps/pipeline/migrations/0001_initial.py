import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("users", "0001_initial"),
        ("leads", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Pipeline",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("is_default", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pipelines",
                        to="users.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Stage",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=120)),
                ("order", models.PositiveIntegerField()),
                ("color", models.CharField(default="#BC5C2D", max_length=7)),
                ("probability", models.PositiveSmallIntegerField(default=0)),
                (
                    "kind",
                    models.CharField(
                        choices=[("open", "Open"), ("won", "Won"), ("lost", "Lost")],
                        default="open",
                        max_length=10,
                    ),
                ),
                ("wip_limit", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "pipeline",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stages",
                        to="pipeline.pipeline",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="Deal",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=255)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Open"), ("won", "Won"), ("lost", "Lost")],
                        default="open",
                        max_length=10,
                    ),
                ),
                ("position", models.PositiveIntegerField(default=0)),
                ("expected_close_date", models.DateField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("lost_reason", models.CharField(blank=True, max_length=255)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_deals",
                        to="users.user",
                    ),
                ),
                (
                    "lead",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deals",
                        to="leads.lead",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deals",
                        to="users.organization",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="owned_deals",
                        to="users.user",
                    ),
                ),
                (
                    "pipeline",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deals",
                        to="pipeline.pipeline",
                    ),
                ),
                (
                    "stage",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="deals",
                        to="pipeline.stage",
                    ),
                ),
            ],
            options={
                "ordering": ["stage__order", "position", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="StageMovement",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("moved_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("from_position", models.PositiveIntegerField(default=0)),
                ("to_position", models.PositiveIntegerField(default=0)),
                ("note", models.CharField(blank=True, max_length=255)),
                (
                    "deal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="movements",
                        to="pipeline.deal",
                    ),
                ),
                (
                    "from_stage",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="movements_from",
                        to="pipeline.stage",
                    ),
                ),
                (
                    "moved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="stage_movements",
                        to="users.user",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stage_movements",
                        to="users.organization",
                    ),
                ),
                (
                    "to_stage",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="movements_to",
                        to="pipeline.stage",
                    ),
                ),
            ],
            options={
                "ordering": ["-moved_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="pipeline",
            constraint=models.UniqueConstraint(
                fields=("organization", "name"),
                name="uniq_pipeline_name_per_organization",
            ),
        ),
        migrations.AddConstraint(
            model_name="pipeline",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True)),
                fields=("organization",),
                name="uniq_default_pipeline_per_organization",
            ),
        ),
        migrations.AddConstraint(
            model_name="stage",
            constraint=models.UniqueConstraint(
                fields=("pipeline", "order"),
                name="uniq_stage_order_per_pipeline",
            ),
        ),
        migrations.AddConstraint(
            model_name="stage",
            constraint=models.UniqueConstraint(
                fields=("pipeline", "slug"),
                name="uniq_stage_slug_per_pipeline",
            ),
        ),
        migrations.AddIndex(
            model_name="deal",
            index=models.Index(fields=["organization", "pipeline"], name="pipeline_dea_org_pip_idx"),
        ),
        migrations.AddIndex(
            model_name="deal",
            index=models.Index(fields=["organization", "stage"], name="pipeline_dea_org_sta_idx"),
        ),
        migrations.AddIndex(
            model_name="deal",
            index=models.Index(fields=["organization", "owner"], name="pipeline_dea_org_own_idx"),
        ),
        migrations.AddIndex(
            model_name="deal",
            index=models.Index(fields=["organization", "status"], name="pipeline_dea_org_sts_idx"),
        ),
        migrations.AddIndex(
            model_name="deal",
            index=models.Index(fields=["organization", "created_at"], name="pipeline_dea_org_crt_idx"),
        ),
        migrations.AddIndex(
            model_name="deal",
            index=models.Index(fields=["organization", "closed_at"], name="pipeline_dea_org_cls_idx"),
        ),
        migrations.AddIndex(
            model_name="stagemovement",
            index=models.Index(fields=["organization", "moved_at"], name="pipeline_mov_org_mvd_idx"),
        ),
        migrations.AddIndex(
            model_name="stagemovement",
            index=models.Index(fields=["organization", "to_stage"], name="pipeline_mov_org_tst_idx"),
        ),
    ]

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("users", "0001_initial"),
        ("leads", "0001_initial"),
        ("pipeline", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Interaction",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("call", "Call"),
                            ("message", "Message"),
                            ("email", "Email"),
                            ("meeting", "Meeting"),
                            ("note", "Note"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "direction",
                    models.CharField(
                        choices=[
                            ("inbound", "Inbound"),
                            ("outbound", "Outbound"),
                            ("internal", "Internal"),
                        ],
                        default="internal",
                        max_length=20,
                    ),
                ),
                ("subject", models.CharField(blank=True, max_length=255)),
                ("content", models.TextField()),
                ("outcome", models.CharField(blank=True, max_length=255)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_interactions",
                        to="users.user",
                    ),
                ),
                (
                    "deal",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="interactions",
                        to="pipeline.deal",
                    ),
                ),
                (
                    "lead",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="interactions",
                        to="leads.lead",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="interactions",
                        to="users.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["-occurred_at", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="interaction",
            index=models.Index(
                fields=["organization", "lead", "occurred_at"],
                name="interaction_org_lead_occurred_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="interaction",
            index=models.Index(
                fields=["organization", "deal", "occurred_at"],
                name="interaction_org_deal_occurred_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="interaction",
            index=models.Index(fields=["organization", "type"], name="interaction_org_type_idx"),
        ),
    ]

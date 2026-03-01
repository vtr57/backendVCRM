import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="LeadSource",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lead_sources",
                        to="users.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Tag",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=80)),
                ("color", models.CharField(default="#BC5C2D", max_length=7)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lead_tags",
                        to="users.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Lead",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("full_name", models.CharField(max_length=255)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("company_name", models.CharField(blank=True, max_length=255)),
                ("job_title", models.CharField(blank=True, max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("contacted", "Contacted"),
                            ("qualified", "Qualified"),
                            ("proposal", "Proposal"),
                            ("won", "Won"),
                            ("lost", "Lost"),
                        ],
                        default="new",
                        max_length=20,
                    ),
                ),
                (
                    "temperature",
                    models.CharField(
                        choices=[("cold", "Cold"), ("warm", "Warm"), ("hot", "Hot")],
                        default="cold",
                        max_length=10,
                    ),
                ),
                ("estimated_value", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("notes_summary", models.TextField(blank=True)),
                ("last_interaction_at", models.DateTimeField(blank=True, null=True)),
                ("next_action_at", models.DateTimeField(blank=True, null=True)),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_leads",
                        to="users.user",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_leads",
                        to="users.user",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="leads",
                        to="users.organization",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="leads",
                        to="leads.leadsource",
                    ),
                ),
                ("tags", models.ManyToManyField(blank=True, related_name="leads", to="leads.tag")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="leadsource",
            constraint=models.UniqueConstraint(
                fields=("organization", "name"),
                name="uniq_lead_source_name_per_organization",
            ),
        ),
        migrations.AddConstraint(
            model_name="tag",
            constraint=models.UniqueConstraint(
                fields=("organization", "name"),
                name="uniq_tag_name_per_organization",
            ),
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["organization", "created_at"], name="leads_lead_org_cra_70a23d_idx"),
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["organization", "status"], name="leads_lead_org_sta_1130d9_idx"),
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["organization", "assigned_to"], name="leads_lead_org_ass_a88013_idx"),
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["organization", "source"], name="leads_lead_org_sou_4f7854_idx"),
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["organization", "deleted_at"], name="leads_lead_org_del_07102a_idx"),
        ),
    ]

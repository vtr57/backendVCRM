from django.db import migrations, models


def migrate_manager_role_to_admin(apps, schema_editor):
    Membership = apps.get_model("users", "Membership")
    Membership.objects.filter(role="manager").update(role="admin")


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_user_is_superuser"),
    ]

    operations = [
        migrations.RunPython(migrate_manager_role_to_admin, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="membership",
            name="role",
            field=models.CharField(
                choices=[
                    ("owner", "Owner"),
                    ("admin", "Admin"),
                    ("sales", "Sales"),
                ],
                default="sales",
                max_length=20,
            ),
        ),
    ]

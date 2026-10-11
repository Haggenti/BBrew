from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0073_equipmentsettings_hop_absorption_l_kg"),
    ]

    operations = [
        migrations.CreateModel(
            name="DashboardSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("notes", models.TextField(blank=True, verbose_name="notes du tableau de bord")),
            ],
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0072_hop_unit_cost_per_100g"),
    ]

    operations = [
        migrations.AddField(
            model_name="equipmentsettings",
            name="hop_absorption_l_kg",
            field=models.DecimalField(
                decimal_places=2,
                default=1,
                max_digits=5,
                verbose_name="absorption des houblons (L/kg)",
            ),
        ),
    ]

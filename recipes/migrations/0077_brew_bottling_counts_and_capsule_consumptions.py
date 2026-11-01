from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0076_brew_stock_additions"),
    ]

    operations = [
        migrations.AddField(
            model_name="brew",
            name="filled_bottle_count",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="nombre de bouteilles remplies",
            ),
        ),
        migrations.AddField(
            model_name="brew",
            name="capsule_consumptions",
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name="répartition des capsules consommées",
            ),
        ),
    ]

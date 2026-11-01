from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0077_brew_bottling_counts_and_capsule_consumptions"),
    ]

    operations = [
        migrations.AddField(
            model_name="equipmentsettings",
            name="bottle_volume_l",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.75"),
                max_digits=4,
                verbose_name="volume d’une bouteille (L)",
            ),
        ),
    ]
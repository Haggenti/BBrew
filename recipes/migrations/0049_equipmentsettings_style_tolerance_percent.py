from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0048_shoppingitem_is_received"),
    ]

    operations = [
        migrations.AddField(
            model_name="equipmentsettings",
            name="style_tolerance_percent",
            field=models.DecimalField(
                decimal_places=1,
                default=10,
                max_digits=5,
                verbose_name="tolérance des styles (%)",
            ),
        ),
    ]

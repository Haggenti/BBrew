from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0074_dashboardsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="equipmentsettings",
            name="mash_evaporation_l_h",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name="évaporation pendant le brassage (L/h)",
            ),
        ),
    ]
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0075_equipmentsettings_mash_evaporation_l_h"),
    ]

    operations = [
        migrations.AddField(
            model_name="brew",
            name="stock_additions",
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name="ajouts manuels au stock du brassin",
            ),
        ),
    ]
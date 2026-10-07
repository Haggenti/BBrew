from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recipes", "0061_activityevent_details"),
    ]

    operations = [
        migrations.AlterField(
            model_name="equipmentsettings",
            name="diameter_cm",
            field=models.DecimalField(
                decimal_places=1,
                default=38,
                max_digits=6,
                verbose_name="diamètre de la cuve (cm)",
            ),
        ),
        migrations.AlterField(
            model_name="equipmentsettings",
            name="height_cm",
            field=models.DecimalField(
                decimal_places=1,
                default=40,
                max_digits=6,
                verbose_name="hauteur de la cuve (cm)",
            ),
        ),
        migrations.AlterField(
            model_name="equipmentsettings",
            name="bag_weight_g",
            field=models.DecimalField(
                decimal_places=1,
                default=100,
                max_digits=7,
                verbose_name="poids du sac (g)",
            ),
        ),
        migrations.AlterField(
            model_name="equipmentsettings",
            name="evaporation_l_h",
            field=models.DecimalField(
                decimal_places=2,
                default=5,
                max_digits=5,
                verbose_name="évaporation (L/h)",
            ),
        ),
        migrations.AlterField(
            model_name="equipmentsettings",
            name="grain_absorption_l_kg",
            field=models.DecimalField(
                decimal_places=2,
                default=0.3,
                max_digits=5,
                verbose_name="absorption des grains (L/kg)",
            ),
        ),
        migrations.AlterField(
            model_name="equipmentsettings",
            name="mash_efficiency",
            field=models.DecimalField(
                decimal_places=1,
                default=72,
                max_digits=5,
                verbose_name="rendement de brassage (%)",
            ),
        ),
        migrations.AlterField(
            model_name="equipmentsettings",
            name="style_tolerance_percent",
            field=models.DecimalField(
                decimal_places=1,
                default=30,
                max_digits=5,
                verbose_name="tolérance des styles (%)",
            ),
        ),
    ]

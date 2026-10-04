from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0034_normalize_hop_forms"),
    ]

    operations = [
        migrations.AddField(
            model_name="ingredient",
            name="for_bottling",
            field=models.BooleanField(default=False, verbose_name="ajoutée à l'embouteillage"),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recipes", "0060_ingredientcatalog_unit_cost"),
    ]

    operations = [
        migrations.AddField(
            model_name="activityevent",
            name="details",
            field=models.TextField(blank=True, verbose_name="détails"),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0047_normalize_empty_yeast_product_references"),
    ]

    operations = [
        migrations.AddField(
            model_name="shoppingitem",
            name="is_received",
            field=models.BooleanField(default=False, verbose_name="réceptionné"),
        ),
    ]

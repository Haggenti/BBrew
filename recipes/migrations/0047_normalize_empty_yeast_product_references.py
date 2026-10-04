from django.db import migrations


def normalize_empty_yeast_product_references(apps, schema_editor):
    IngredientCatalog = apps.get_model("recipes", "IngredientCatalog")
    Ingredient = apps.get_model("recipes", "Ingredient")
    for model in (IngredientCatalog, Ingredient):
        model.objects.filter(kind="yeast", product_id__in=["-", "—"]).update(product_id="")


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0046_clean_empty_yeast_product_references"),
    ]

    operations = [
        migrations.RunPython(normalize_empty_yeast_product_references, migrations.RunPython.noop),
    ]

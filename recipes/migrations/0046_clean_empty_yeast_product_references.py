from django.db import migrations


def clean_empty_yeast_product_references(apps, schema_editor):
    IngredientCatalog = apps.get_model("recipes", "IngredientCatalog")
    Ingredient = apps.get_model("recipes", "Ingredient")
    for model in (IngredientCatalog, Ingredient):
        for item in model.objects.filter(kind="yeast"):
            for suffix in (" (-)", " (—)"):
                if item.name.endswith(suffix):
                    item.name = item.name[: -len(suffix)]
                    item.save(update_fields=["name"])
                    break


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0045_alter_equipmentsettings_mash_efficiency"),
    ]

    operations = [
        migrations.RunPython(clean_empty_yeast_product_references, migrations.RunPython.noop),
    ]

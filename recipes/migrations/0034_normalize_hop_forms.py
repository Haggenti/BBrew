from django.db import migrations


def normalize_hop_forms(apps, schema_editor):
    Ingredient = apps.get_model("recipes", "Ingredient")
    IngredientCatalog = apps.get_model("recipes", "IngredientCatalog")
    Ingredient.objects.filter(kind="hop", form__iexact="pellet").update(form="Pellets")
    IngredientCatalog.objects.filter(kind="hop", form__iexact="pellet").update(form="Pellets")


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0033_ingredient_addition_temperature_c"),
    ]

    operations = [
        migrations.RunPython(normalize_hop_forms, migrations.RunPython.noop),
    ]

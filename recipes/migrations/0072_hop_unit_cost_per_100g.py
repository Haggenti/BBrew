from decimal import Decimal

from django.db import migrations
from django.db.models import F


def convert_hop_unit_costs_to_100g(apps, schema_editor):
    IngredientCatalog = apps.get_model("recipes", "IngredientCatalog")
    IngredientCatalog.objects.filter(kind="hop", unit_cost__isnull=False).update(
        unit_cost=Decimal("100") * F("unit_cost")
    )


def convert_hop_unit_costs_to_grams(apps, schema_editor):
    IngredientCatalog = apps.get_model("recipes", "IngredientCatalog")
    IngredientCatalog.objects.filter(kind="hop", unit_cost__isnull=False).update(
        unit_cost=F("unit_cost") / Decimal("100")
    )


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0071_brew_actual_preboil_og"),
    ]

    operations = [
        migrations.RunPython(
            convert_hop_unit_costs_to_100g,
            convert_hop_unit_costs_to_grams,
        ),
    ]

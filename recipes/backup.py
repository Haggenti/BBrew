import json

from django.core import serializers
from django.db import transaction
from django.utils import timezone

from .models import (
    BeerCategory,
    Brew,
    EquipmentSettings,
    FermentationStep,
    Ingredient,
    IngredientCatalog,
    MashStep,
    Recipe,
    RecipeVersion,
    ShoppingItem,
)

BACKUP_VERSION = 2
SUPPORTED_BACKUP_VERSIONS = {1, BACKUP_VERSION}
BACKUP_MODELS = (
    BeerCategory,
    EquipmentSettings,
    IngredientCatalog,
    Recipe,
    RecipeVersion,
    Brew,
    Ingredient,
    MashStep,
    FermentationStep,
    ShoppingItem,
)


def create_backup():
    records = []
    for model in BACKUP_MODELS:
        records.extend(json.loads(serializers.serialize("json", model.objects.all())))
    return {
        "format": "BBS backup",
        "version": BACKUP_VERSION,
        "created_at": timezone.now().isoformat(),
        "records": records,
        "relations": {
            "shopping_item_sources": [
                {
                    "shopping_item_id": item.pk,
                    "brew_ids": list(item.source_brews.values_list("pk", flat=True)),
                }
                for item in ShoppingItem.objects.prefetch_related("source_brews")
                if item.source_brews.exists()
            ],
        },
    }


def validate_backup(data):
    if not isinstance(data, dict) or data.get("format") not in {"BBS backup", "BBrew backup"}:
        raise ValueError("Le fichier n’est pas une sauvegarde BBS valide.")
    if data.get("version") not in SUPPORTED_BACKUP_VERSIONS:
        raise ValueError("La version de cette sauvegarde n’est pas compatible.")
    if not isinstance(data.get("records"), list):
        raise ValueError("La sauvegarde ne contient pas de données exploitables.")

    allowed_models = {model._meta.label_lower for model in BACKUP_MODELS}
    unknown_models = sorted({record.get("model") for record in data["records"] if record.get("model") not in allowed_models})
    if unknown_models:
        raise ValueError(f"La sauvegarde contient un modèle inconnu : {', '.join(unknown_models)}.")
    relations = data.get("relations", {})
    if not isinstance(relations, dict):
        raise ValueError("Les relations de la sauvegarde sont invalides.")
    if not isinstance(relations.get("shopping_item_sources", []), list):
        raise ValueError("Les relations entre courses et brassins sont invalides.")


def restore_backup(data):
    validate_backup(data)
    records_by_model = {}
    for record in data["records"]:
        records_by_model.setdefault(record["model"].lower(), []).append(record)

    with transaction.atomic():
        for model in BACKUP_MODELS[::-1]:
            model.objects.all().delete()

        for model in BACKUP_MODELS:
            model_records = records_by_model.get(model._meta.label_lower, [])
            for obj in serializers.deserialize("json", json.dumps(model_records)):
                obj.save()

        for relation in data.get("relations", {}).get("shopping_item_sources", []):
            shopping_item = ShoppingItem.objects.get(pk=relation["shopping_item_id"])
            shopping_item.source_brews.set(Brew.objects.filter(pk__in=relation.get("brew_ids", [])))

import json

from django.core import serializers
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

BACKUP_VERSION = 1
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
        "format": "BBrew backup",
        "version": BACKUP_VERSION,
        "created_at": timezone.now().isoformat(),
        "records": records,
    }


def validate_backup(data):
    if not isinstance(data, dict) or data.get("format") != "BBrew backup":
        raise ValueError("Le fichier n’est pas une sauvegarde BBrew valide.")
    if data.get("version") != BACKUP_VERSION:
        raise ValueError("La version de cette sauvegarde n’est pas compatible.")
    if not isinstance(data.get("records"), list):
        raise ValueError("La sauvegarde ne contient pas de données exploitables.")

    allowed_models = {model._meta.label_lower for model in BACKUP_MODELS}
    unknown_models = sorted({record.get("model") for record in data["records"] if record.get("model") not in allowed_models})
    if unknown_models:
        raise ValueError(f"La sauvegarde contient un modèle inconnu : {', '.join(unknown_models)}.")


def restore_backup(data):
    validate_backup(data)
    records_by_model = {}
    for record in data["records"]:
        records_by_model.setdefault(record["model"].lower(), []).append(record)

    for model in BACKUP_MODELS[::-1]:
        model.objects.all().delete()

    for model in BACKUP_MODELS:
        model_records = records_by_model.get(model._meta.label_lower, [])
        for obj in serializers.deserialize("json", json.dumps(model_records)):
            obj.save()

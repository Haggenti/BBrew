from .models import Recipe


FIELD_LABELS = {
    "name": "Nom",
    "batch_size_l": "Volume",
    "efficiency": "Efficacité",
    "target_og": "OG cible",
    "target_ibu": "IBU cible",
    "boil_time_min": "Ébullition",
    "notes": "Notes",
    "tasting_malt": "Malté / douceur",
    "tasting_bitterness": "Amertume perçue",
    "tasting_hops": "Arômes de houblon",
    "tasting_body": "Corps",
    "tasting_alcohol": "Chaleur de l’alcool",
    "tasting_acidity": "Acidité",
    "tasting_rating": "Note globale de dégustation",
    "tasting_notes": "Notes de dégustation",
    "amount_g": "Quantité",
    "manufacturer": "Fabricant",
    "form": "Forme",
    "addition": "Ajout",
    "color_ebc": "Couleur",
    "potential_yield": "Rendement",
    "alpha_acid": "Acides alpha",
    "boil_minutes": "Temps",
    "attenuation": "Atténuation",
    "temperature_c": "Température",
    "duration_min": "Durée",
    "duration_days": "Durée",
    "action": "Action",
}


def _display_value(field, value):
    if value in (None, ""):
        return "vide"
    suffixes = {
        "batch_size_l": " L",
        "efficiency": " %",
        "amount_g": " g",
        "color_ebc": " EBC",
        "potential_yield": " %",
        "alpha_acid": " %",
        "temperature_c": " °C",
        "duration_min": " min",
        "duration_days": " j",
        "boil_time_min": " min",
    }
    return f"{value}{suffixes.get(field, '')}"


def _changed_fields(before, after, excluded=()):
    changes = []
    for field in after:
        if field in excluded or before.get(field) == after.get(field):
            continue
        label = FIELD_LABELS.get(field, field)
        changes.append(f"{label} : {_display_value(field, before.get(field))} → {_display_value(field, after.get(field))}")
    return changes


def _list_change_details(before, after, collection, key_fields, excluded=()):
    before_items = {tuple(item.get(field) for field in key_fields): item for item in before.get(collection, [])}
    after_items = {tuple(item.get(field) for field in key_fields): item for item in after.get(collection, [])}
    details = []
    for key, item in after_items.items():
        if key not in before_items:
            label = item.get("name") or item.get("phase") or item.get("kind") or "élément"
            details.append(f"Ajout : {label}")
        else:
            details.extend(_changed_fields(before_items[key], item, excluded))
    for key, item in before_items.items():
        if key not in after_items:
            label = item.get("name") or item.get("phase") or item.get("kind") or "élément"
            details.append(f"Suppression : {label}")
    return details


def describe_version_change(before, after, reason):
    if before is None:
        return "Version initiale"
    details = _changed_fields(before["recipe"], after["recipe"])
    details += _list_change_details(before, after, "ingredients", ("kind", "name"), {"kind", "catalog"})
    details += _list_change_details(before, after, "mash_steps", ("position",), {"position"})
    details += _list_change_details(before, after, "fermentation_steps", ("position",), {"position"})
    return "\n".join(details[:6]) or reason


def recipe_snapshot(recipe):
    return {
        "recipe": {
            "name": recipe.name,
            "category": recipe.category_id,
            "batch_size_l": str(recipe.batch_size_l),
            "efficiency": str(recipe.efficiency),
            "target_og": str(recipe.target_og),
            "target_ibu": str(recipe.target_ibu),
            "target_carbonation": str(recipe.target_carbonation),
            "boil_time_min": recipe.boil_time_min,
            "mash_time_min": recipe.mash_time_min,
            "mash_time_max": recipe.mash_time_max,
            "mash_temperature_min": recipe.mash_temperature_min,
            "mash_temperature_max": recipe.mash_temperature_max,
            "mash_time_grid": recipe.mash_time_grid,
            "mash_temperature_grid": recipe.mash_temperature_grid,
            "mash_zones": recipe.mash_zones,
            "notes": recipe.notes,
        },
        "ingredients": [
            {
                "kind": item.kind,
                "catalog": item.catalog_id,
                "name": item.name,
                "amount_g": str(item.amount_g),
                "manufacturer": item.manufacturer,
                "form": item.form,
                "addition": item.addition,
                "addition_temperature_c": str(item.addition_temperature_c) if item.addition_temperature_c is not None else None,
                "for_bottling": item.for_bottling,
                "notes": item.notes,
                "color_ebc": str(item.color_ebc),
                "cost_total": str(item.cost_total) if item.cost_total is not None else None,
                "potential_yield": str(item.potential_yield),
                "alpha_acid": str(item.alpha_acid),
                "boil_minutes": item.boil_minutes,
                "attenuation": str(item.attenuation),
            }
            for item in recipe.ingredients.all()
        ],
        "mash_steps": [
            {
                "position": step.position,
                "name": step.name,
                "temperature_c": str(step.temperature_c),
                "duration_min": step.duration_min,
            }
            for step in recipe.mash_steps.all()
        ],
        "fermentation_steps": [
            {
                "position": step.position,
                "phase": step.phase,
                "temperature_c": str(step.temperature_c),
                "duration_days": step.duration_days,
                "action": step.action,
            }
            for step in recipe.fermentation_steps.all()
        ],
    }

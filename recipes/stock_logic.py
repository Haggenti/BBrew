from decimal import Decimal, ROUND_CEILING

from django.utils import timezone

from .models import Brew, Ingredient, IngredientCatalog


def brew_stock_requirements(brew):
    requirements = {}
    if not brew.recipe_version:
        return []
    for ingredient in brew.recipe_version.snapshot.get("ingredients", []):
        catalog_id = ingredient.get("catalog")
        kind = ingredient.get("kind")
        key = f"{catalog_id}:{kind}" if catalog_id is not None else f"missing:{ingredient.get('name', 'unknown')}"
        if key not in requirements:
            requirements[key] = {
                "key": key,
                "catalog_id": catalog_id,
                "kind": kind,
                "name": ingredient.get("name", "Ingrédient inconnu"),
                "required": 0,
                "unit": "paquet(s)" if kind == Ingredient.Kind.YEAST else "" if kind == Ingredient.Kind.OTHER else "g",
            }
        requirements[key]["required"] += (
            1
            if kind == Ingredient.Kind.YEAST
            else int(Decimal(str(ingredient.get("amount_g", 0))).to_integral_value(rounding=ROUND_CEILING))
        )
    catalog_ids = [item["catalog_id"] for item in requirements.values() if item["catalog_id"] is not None]
    catalog_by_id = IngredientCatalog.objects.in_bulk(catalog_ids)
    consumed = set(brew.stock_consumed_items or [])
    for item in requirements.values():
        item["catalog"] = catalog_by_id.get(item["catalog_id"])
        item["available"] = item["catalog"].quantity_available if item["catalog"] else None
        item["consumed"] = item["key"] in consumed
    return list(requirements.values())


def planned_stock_needs():
    needs = {}
    upcoming_brews = Brew.objects.filter(
        planned_date__gte=timezone.localdate(),
        status=Brew.Status.PLANNED,
    )
    for brew in upcoming_brews:
        for requirement in brew_stock_requirements(brew):
            catalog_id = requirement["catalog_id"]
            if catalog_id is None:
                continue
            need = needs.setdefault(catalog_id, {"required": 0, "unit": requirement["unit"], "brews": []})
            need["required"] += requirement["required"]
            if brew not in need["brews"]:
                need["brews"].append(brew)
    return needs


def planned_brew_stock_requirements():
    """Return requirements after reserving stock chronologically for planned brews."""
    today = timezone.localdate()
    upcoming_brews = Brew.objects.filter(
        planned_date__gte=today,
        status=Brew.Status.PLANNED,
    ).order_by("planned_date", "pk")
    reserved = {}
    requirements_by_brew = {}
    for brew in upcoming_brews:
        requirements = brew_stock_requirements(brew)
        for requirement in requirements:
            catalog_id = requirement["catalog_id"]
            if catalog_id is None or requirement["available"] is None:
                requirement["available_after_previous"] = None
                requirement["sufficient_for_brew"] = False
                continue
            available_after_previous = requirement["available"] - reserved.get(catalog_id, 0)
            requirement["available_after_previous"] = max(0, available_after_previous)
            requirement["sufficient_for_brew"] = available_after_previous >= requirement["required"]
            reserved[catalog_id] = reserved.get(catalog_id, 0) + requirement["required"]
        requirements_by_brew[brew.pk] = requirements
    return requirements_by_brew

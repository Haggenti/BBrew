from .models import Recipe


def recipe_snapshot(recipe):
    return {
        "recipe": {
            "name": recipe.name,
            "batch_size_l": str(recipe.batch_size_l),
            "efficiency": str(recipe.efficiency),
            "target_og": str(recipe.target_og),
            "target_ibu": str(recipe.target_ibu),
            "boil_time_min": recipe.boil_time_min,
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
                "color_ebc": str(item.color_ebc),
                "cost_total": str(item.cost_total),
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

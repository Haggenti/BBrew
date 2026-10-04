from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from xml.etree import ElementTree
import json

from .calculations import average_mash_temperature, ebc_color_rgb, estimated_abv, estimated_color_ebc, estimated_efficiency, estimated_final_gravity, estimated_og, ibu_final_gravity_comment, ibu_final_gravity_ratio, plato_from_gravity, tinseth_ibu
from .beerxml import export_recipe, import_recipe
from decimal import Decimal
from decimal import ROUND_CEILING
from django.utils import timezone

from .forms import BackupUploadForm, BeerCategoryForm, BeerXMLUploadForm, BoilSettingsForm, BrewForm, CatalogHopForm, CatalogMaltForm, CatalogOtherForm, CatalogYeastForm, CatalogForm, EquipmentSettingsForm, FermentationStepForm, HopForm, MaltForm, MashStepForm, OtherForm, RecipeCategoryForm, RecipeEfficiencyForm, RecipeForm, RecipeNameForm, RecipeNotesForm, ScaleForm, ShoppingItemForm, YeastForm
from .models import BeerCategory, Brew, EquipmentSettings, FermentationStep, Ingredient, IngredientCatalog, MashStep, Recipe, RecipeVersion, ShoppingItem
from .signals import save_version, suspend_versioning
from .versioning import describe_version_change
from .backup import create_backup, restore_backup


def recipe_list(request):
    recipes = list(Recipe.objects.all())
    for recipe in recipes:
        malts = recipe.ingredients.filter(kind=Ingredient.Kind.MALT)
        yeasts = recipe.ingredients.filter(kind=Ingredient.Kind.YEAST)
        mash_steps = list(recipe.mash_steps.all())
        estimated_og_value = (
            estimated_og(malts, float(recipe.batch_size_l), float(recipe.efficiency))
            if malts
            else None
        )
        recipe.estimated_og_value = estimated_og_value
        recipe.estimated_abv_value = estimated_abv(
            estimated_og_value or float(recipe.target_og),
            yeasts,
            mash_steps,
        )
        recipe.estimated_ebc_value = (
            estimated_color_ebc(malts, float(recipe.batch_size_l))
            if malts
            else None
        )
        recipe.estimated_ebc_color = (
            ebc_color_rgb(recipe.estimated_ebc_value)
            if recipe.estimated_ebc_value is not None
            else None
        )
    return render(request, "recipes/list.html", {"recipes": recipes})


def brew_list(request):
    return render(request, "recipes/brews.html", {"brews": Brew.objects.all()})


def shopping_list(request):
    return render(
        request,
        "recipes/shopping_list.html",
        {"items": ShoppingItem.objects.all(), "form": ShoppingItemForm()},
    )


@require_POST
def shopping_item_create(request):
    form = ShoppingItemForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, "Article ajouté à la liste de courses.")
    return redirect("recipes:shopping_list")


@require_POST
def shopping_item_toggle(request, pk):
    item = get_object_or_404(ShoppingItem, pk=pk)
    item.is_completed = not item.is_completed
    item.save(update_fields=["is_completed"])
    return redirect("recipes:shopping_list")


@require_POST
def shopping_item_delete(request, pk):
    item = get_object_or_404(ShoppingItem, pk=pk)
    item.delete()
    messages.success(request, "Article supprimé de la liste de courses.")
    return redirect("recipes:shopping_list")


def brew_create(request):
    form = BrewForm(request.POST or None, equipment_settings=EquipmentSettings.objects.first())
    if request.method == "POST" and form.is_valid():
        brew = form.save()
        messages.success(request, f"Le brassin « {brew.recipe_name} » a été créé.")
        return redirect("recipes:brews")
    return render(request, "recipes/brew_form.html", {"form": form, "latest_versions": _latest_recipe_versions()})


def brew_detail(request, pk):
    brew = get_object_or_404(Brew, pk=pk)
    comparison = _brew_comparison(brew)
    return render(
        request,
        "recipes/brew_detail.html",
        {"brew": brew, "comparison": comparison, "stock_requirements": _brew_stock_requirements(brew)},
    )


def brew_edit(request, pk):
    brew = get_object_or_404(Brew, pk=pk)
    form = BrewForm(
        request.POST or None,
        instance=brew,
        equipment_settings=EquipmentSettings.objects.first(),
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Le brassin « {brew.recipe_name} » a été mis à jour.")
        return redirect("recipes:brew_detail", pk=brew.pk)
    return render(request, "recipes/brew_form.html", {"form": form, "brew": brew, "latest_versions": _latest_recipe_versions()})


def _latest_recipe_versions():
    return {
        recipe.pk: (recipe.current_version or recipe.versions.first()).pk
        for recipe in Recipe.objects.all()
        if recipe.current_version or recipe.versions.first()
    }


@require_POST
def brew_delete(request, pk):
    brew = get_object_or_404(Brew, pk=pk)
    brew_name = brew.recipe_name
    brew.delete()
    messages.success(request, f"Le brassin « {brew_name} » a été supprimé.")
    return redirect("recipes:brews")


def _brew_stock_requirements(brew):
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
                "unit": (
                    "paquet(s)"
                    if kind == Ingredient.Kind.YEAST
                    else "" if kind == Ingredient.Kind.OTHER else "g"
                ),
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


def _brew_comparison(brew):
    actual_efficiency = None
    evaporation_total = None
    evaporation_rate = None
    residual_water_kg = None
    dry_grains_kg = 0
    if brew.recipe_version:
        dry_grains_kg = sum(
            float(item.get("amount_g", 0))
            for item in brew.recipe_version.snapshot.get("ingredients", [])
            if item.get("kind") == Ingredient.Kind.MALT
        ) / 1000
    elif brew.recipe:
        dry_grains_kg = float(
            sum(brew.recipe.ingredients.filter(kind=Ingredient.Kind.MALT).values_list("amount_g", flat=True))
        ) / 1000
    if brew.actual_spent_grains_weight_kg is not None:
        equipment = EquipmentSettings.objects.first()
        bag_weight_kg = float(equipment.bag_weight_kg) / 1000 if equipment else 0
        residual_water_kg = float(brew.actual_spent_grains_weight_kg) - bag_weight_kg - dry_grains_kg
    if brew.actual_preboil_volume_l is not None and brew.actual_batch_size_l is not None:
        evaporation_total = float(brew.actual_preboil_volume_l - brew.actual_batch_size_l)
        boil_time = None
        if brew.recipe_version:
            boil_time = brew.recipe_version.snapshot.get("boil_time_min")
        if boil_time is None and brew.recipe:
            boil_time = brew.recipe.boil_time_min
        if boil_time:
            evaporation_rate = evaporation_total / (float(boil_time) / 60)
    if brew.actual_og is not None and brew.actual_batch_size_l and brew.recipe_version:
        from types import SimpleNamespace

        malts = [
            SimpleNamespace(**item)
            for item in brew.recipe_version.snapshot.get("ingredients", [])
            if item["kind"] == Ingredient.Kind.MALT
        ]
        actual_efficiency = estimated_efficiency(malts, brew.actual_og, brew.actual_batch_size_l)
    return {
        "actual_efficiency": actual_efficiency,
        "evaporation_total": evaporation_total,
        "evaporation_rate": evaporation_rate,
        "grain_weight_kg": dry_grains_kg or None,
        "residual_water_kg": residual_water_kg,
        "absorption_l_per_kg": (
            residual_water_kg / dry_grains_kg
            if residual_water_kg is not None and dry_grains_kg > 0
            else None
        ),
        "og_delta": float(brew.actual_og - brew.planned_og) if brew.actual_og is not None and brew.planned_og is not None else None,
        "fg_delta": float(brew.actual_fg - brew.planned_fg) if brew.actual_fg is not None and brew.planned_fg is not None else None,
        "abv_delta": brew.actual_abv - float(brew.planned_abv) if brew.actual_abv is not None and brew.planned_abv is not None else None,
        "volume_delta": float(brew.actual_batch_size_l - brew.planned_batch_size_l) if brew.actual_batch_size_l is not None and brew.planned_batch_size_l is not None else None,
        "efficiency_delta": actual_efficiency - float(brew.planned_efficiency) if actual_efficiency is not None and brew.planned_efficiency is not None else None,
    }


@require_POST
def brew_consume_stock(request, pk):
    brew = get_object_or_404(Brew, pk=pk)
    selected = set(request.POST.getlist("stock_item"))
    requirements = _brew_stock_requirements(brew)
    consumable = {item["key"]: item for item in requirements if item["catalog"] and not item["consumed"]}
    with transaction.atomic():
        consumed_items = set(brew.stock_consumed_items or [])
        for key in selected & consumable.keys():
            requirement = consumable[key]
            item = IngredientCatalog.objects.select_for_update().get(pk=requirement["catalog_id"])
            item.quantity_available -= requirement["required"]
            item.save(update_fields=["quantity_available"])
            consumed_items.add(key)
        brew.stock_consumed_items = sorted(consumed_items)
        if consumable and all(item["key"] in consumed_items for item in requirements if item["catalog"]):
            brew.stock_consumed_at = timezone.now()
        brew.save(update_fields=["stock_consumed_items", "stock_consumed_at"])
    messages.success(request, "Les lignes sélectionnées ont été consommées.")
    return redirect("recipes:brew_detail", pk=brew.pk)


@require_POST
def brew_rollback_stock(request, pk):
    brew = get_object_or_404(Brew, pk=pk)
    selected = set(request.POST.getlist("stock_item"))
    requirements = _brew_stock_requirements(brew)
    restorable = {item["key"]: item for item in requirements if item["catalog"] and item["consumed"]}
    if not selected & restorable.keys():
        messages.error(request, "Aucune ligne de consommation n’a été sélectionnée.")
        return redirect("recipes:brew_detail", pk=brew.pk)

    with transaction.atomic():
        consumed_items = set(brew.stock_consumed_items or [])
        for key in selected & restorable.keys():
            requirement = restorable[key]
            item = IngredientCatalog.objects.select_for_update().get(pk=requirement["catalog_id"])
            item.quantity_available += requirement["required"]
            item.save(update_fields=["quantity_available"])
            consumed_items.discard(key)
        brew.stock_consumed_items = sorted(consumed_items)
        brew.stock_consumed_at = None
        brew.save(update_fields=["stock_consumed_items", "stock_consumed_at"])
    messages.success(request, "Les lignes sélectionnées ont été restaurées dans le stock.")
    return redirect("recipes:brew_detail", pk=brew.pk)


def equipment_settings(request):
    settings = EquipmentSettings.objects.first()
    form = EquipmentSettingsForm(request.POST or None, instance=settings)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Les paramètres de brassage ont été enregistrés.")
        return redirect("recipes:equipment_settings")
    return render(
        request,
        "recipes/equipment_settings.html",
        {"form": form, "backup_form": BackupUploadForm()},
    )


@require_POST
def database_reset(request):
    sections = {
        "recipes": ("recettes", (Recipe,)),
        "brews": ("brassins", (Brew,)),
        "stock": ("stock", (IngredientCatalog,)),
        "styles": ("catégories BJCP", (BeerCategory,)),
        "equipment": ("paramètres d’équipement", (EquipmentSettings,)),
    }
    selected = [key for key in request.POST.getlist("reset_section") if key in sections]
    if request.POST.get("confirmation") != "SUPPRIMER":
        messages.error(request, "La remise à zéro n’a pas été effectuée : saisissez SUPPRIMER pour confirmer.")
    elif not selected:
        messages.error(request, "Sélectionnez au moins une catégorie de données à supprimer.")
    else:
        with transaction.atomic(), suspend_versioning():
            for key in selected:
                for model in sections[key][1]:
                    model.objects.all().delete()
        labels = ", ".join(sections[key][0] for key in selected)
        messages.success(request, f"Données supprimées : {labels}.")
    return redirect("recipes:equipment_settings")


def backup_download(request):
    response = HttpResponse(
        json.dumps(create_backup(), ensure_ascii=False, indent=2),
        content_type="application/json",
    )
    response["Content-Disposition"] = 'attachment; filename="bbrew-sauvegarde.json"'
    return response


@require_POST
def backup_restore(request):
    form = BackupUploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            data = json.load(form.cleaned_data["file"])
            with transaction.atomic(), suspend_versioning():
                restore_backup(data)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            form.add_error("file", f"Restauration impossible : {error}")
        else:
            messages.success(request, "La sauvegarde a été restaurée. Les données précédentes ont été remplacées.")
            return redirect("recipes:list")
    return render(
        request,
        "recipes/equipment_settings.html",
        {
            "form": EquipmentSettingsForm(instance=EquipmentSettings.objects.first()),
            "backup_form": form,
        },
    )


def category_list(request):
    return render(
        request,
        "recipes/categories.html",
        {"categories": BeerCategory.objects.all(), "form": BeerCategoryForm()},
    )


def category_create(request):
    form = BeerCategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "La catégorie a été ajoutée.")
        return redirect("recipes:categories")
    return render(request, "recipes/categories.html", {"categories": BeerCategory.objects.all(), "form": form})


def category_edit(request, pk):
    category = get_object_or_404(BeerCategory, pk=pk)
    form = BeerCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "La catégorie a été modifiée.")
        return redirect("recipes:categories")
    return render(request, "recipes/category_form.html", {"form": form, "category": category})


@require_POST
def category_delete(request, pk):
    category = get_object_or_404(BeerCategory, pk=pk)
    category.delete()
    messages.success(request, "La catégorie a été supprimée.")
    return redirect("recipes:categories")


def recipe_history(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    versions = list(recipe.versions.all())
    for index, version in enumerate(versions):
        previous = versions[index + 1].snapshot if index + 1 < len(versions) else None
        version.change_tooltip = describe_version_change(previous, version.snapshot, version.reason)
    return render(
        request,
        "recipes/history.html",
        {"recipe": recipe, "versions": versions},
    )


@require_POST
def recipe_restore(request, pk, version_pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    version = get_object_or_404(RecipeVersion, pk=version_pk, recipe=recipe)
    data = version.snapshot
    recipe_data = data["recipe"]
    for field in ("name", "batch_size_l", "efficiency", "target_og", "target_ibu", "boil_time_min", "notes"):
        setattr(recipe, field, recipe_data[field])
    with suspend_versioning():
        recipe.save()
        recipe.ingredients.all().delete()
        recipe.mash_steps.all().delete()
        recipe.fermentation_steps.all().delete()
        for item in data["ingredients"]:
            catalog_id = item.pop("catalog", None)
            item["catalog_id"] = (
                IngredientCatalog.objects.filter(pk=catalog_id).values_list("pk", flat=True).first()
                if catalog_id is not None
                else None
            )
            Ingredient.objects.create(recipe=recipe, **item)
        for step in data["mash_steps"]:
            MashStep.objects.create(recipe=recipe, **step)
        for step in data.get("fermentation_steps", []):
            FermentationStep.objects.create(recipe=recipe, **step)
    recipe.current_version = version
    recipe.save(update_fields=["current_version"])
    messages.success(request, f"La version V{version.version_number} de la recette est maintenant active.")
    return redirect("recipes:detail", pk=recipe.pk)


@require_POST
def recipe_version_create(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    reason = (request.POST.get("reason") or "Version manuelle").strip()[:120]
    version = save_version(recipe, reason or "Version manuelle")
    messages.success(request, f"La version V{version.version_number} de la recette a été créée.")
    return redirect("recipes:detail", pk=recipe.pk)


@require_POST
def recipe_version_delete(request, pk, version_pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    version = get_object_or_404(RecipeVersion, pk=version_pk, recipe=recipe)
    if recipe.current_version_id == version.pk:
        messages.error(request, "La version active ne peut pas être supprimée. Activez d’abord une autre version.")
    else:
        version_number = version.version_number
        version.delete()
        messages.success(request, f"La version V{version_number} a été supprimée.")
    return redirect("recipes:history", pk=recipe.pk)


def catalog_list(request):
    return render(
        request,
        "recipes/catalog.html",
        {
            "malt_form": CatalogMaltForm(),
            "hop_form": CatalogHopForm(),
            "yeast_form": CatalogYeastForm(),
            "malts": IngredientCatalog.objects.filter(kind=IngredientCatalog.Kind.MALT),
            "hops": IngredientCatalog.objects.filter(kind=IngredientCatalog.Kind.HOP),
            "yeasts": IngredientCatalog.objects.filter(kind=IngredientCatalog.Kind.YEAST),
            "others": IngredientCatalog.objects.filter(kind=IngredientCatalog.Kind.OTHER),
            "other_form": CatalogOtherForm(),
        },
    )


def catalog_create(request):
    form_classes = {
        IngredientCatalog.Kind.MALT: CatalogMaltForm,
        IngredientCatalog.Kind.HOP: CatalogHopForm,
        IngredientCatalog.Kind.YEAST: CatalogYeastForm,
        IngredientCatalog.Kind.OTHER: CatalogOtherForm,
    }
    kind = request.POST.get("kind")
    form_class = form_classes.get(kind)
    if form_class is None:
        messages.error(request, "Le type d'ingrédient est invalide.")
        return redirect("recipes:catalog")
    form = form_class(request.POST)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        item.kind = kind
        item.save(update_fields=["kind"])
        messages.success(request, f"{item.name} a été ajouté au catalogue.")
    return redirect("recipes:catalog")


def catalog_edit(request, pk):
    item = get_object_or_404(IngredientCatalog, pk=pk)
    form = CatalogForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{item.name} a été modifié dans le catalogue.")
        return redirect("recipes:catalog")
    return render(request, "recipes/catalog_form.html", {"form": form, "item": item})


@require_POST
def catalog_delete(request, pk):
    item = get_object_or_404(IngredientCatalog, pk=pk)
    item_name = item.name
    item.delete()
    messages.success(request, f"{item_name} a été supprimé du catalogue.")
    return redirect("recipes:catalog")


def recipe_detail(request, pk, edit_forms=None):
    recipe = get_object_or_404(Recipe, pk=pk)
    equipment = EquipmentSettings.objects.first() or EquipmentSettings()
    edit_forms = edit_forms or {}
    malts = recipe.ingredients.filter(kind="malt")
    hops = recipe.ingredients.filter(kind="hop")
    yeasts = recipe.ingredients.filter(kind="yeast")
    others = recipe.ingredients.filter(kind="other")
    mash_steps = list(recipe.mash_steps.all())
    og = estimated_og(malts, float(recipe.batch_size_l), float(recipe.efficiency)) if malts else None
    ibu = tinseth_ibu(hops, float(recipe.batch_size_l), og or float(recipe.target_og)) if hops else None
    ebc = estimated_color_ebc(malts, float(recipe.batch_size_l)) if malts else None
    abv = estimated_abv(og or float(recipe.target_og), yeasts, mash_steps)
    final_gravity = estimated_final_gravity(og or float(recipe.target_og), yeasts, mash_steps)
    ibu_df_ratio = ibu_final_gravity_ratio(ibu, final_gravity)
    ibu_df_comment = ibu_final_gravity_comment(ibu_df_ratio, final_gravity)

    def category_matches_profile(category):
        values = (
            (og, category.og_min, category.og_max),
            (final_gravity, category.fg_min, category.fg_max),
            (ibu, category.ibu_min, category.ibu_max),
            (ebc, category.ebc_min, category.ebc_max),
            (abv, category.abv_min, category.abv_max),
        )
        return all(
            value is not None
            and minimum is not None
            and maximum is not None
            and float(minimum) <= float(value) <= float(maximum)
            for value, minimum, maximum in values
        )

    categories = list(BeerCategory.objects.all())
    compatible_categories = [category for category in categories if category_matches_profile(category)]
    other_categories = [category for category in categories if category not in compatible_categories]
    category_form = RecipeCategoryForm(instance=recipe)
    category_form.fields["category"].choices = [
        ("", "---------"),
        ("Styles compatibles avec la recette", [(category.pk, str(category)) for category in compatible_categories]),
        ("Autres styles", [(category.pk, str(category)) for category in other_categories]),
    ]

    def style_indicator(label, value, minimum, maximum, unit):
        if value is None or minimum is None or maximum is None:
            return None
        value = float(value)
        minimum = float(minimum)
        maximum = float(maximum)
        span = maximum - minimum
        position = 50 if span <= 0 else max(0, min(100, (value - minimum) / span * 100))
        status = "dans la fourchette" if minimum <= value <= maximum else ("en dessous" if value < minimum else "au-dessus")
        return {
            "label": label,
            "value": value,
            "minimum": minimum,
            "maximum": maximum,
            "unit": unit,
            "position": position,
            "status": status,
            "ok": minimum <= value <= maximum,
        }

    style_indicators = []
    if recipe.category:
        for indicator in (
            style_indicator("OG", og, recipe.category.og_min, recipe.category.og_max, ""),
            style_indicator("FG", final_gravity, recipe.category.fg_min, recipe.category.fg_max, ""),
            style_indicator("Couleur", ebc, recipe.category.ebc_min, recipe.category.ebc_max, " EBC"),
            style_indicator("Amertume", ibu, recipe.category.ibu_min, recipe.category.ibu_max, " IBU"),
            style_indicator("Alcool", abv, recipe.category.abv_min, recipe.category.abv_max, " %"),
        ):
            if indicator:
                style_indicators.append(indicator)
    malt_total = sum(float(malt.amount_g) for malt in malts)
    mash_chart_points = []
    mash_elapsed = 0
    if mash_steps:
        mash_chart_points.append({"x": 0, "y": float(mash_steps[0].temperature_c)})
        for index, step in enumerate(mash_steps):
            mash_elapsed += step.duration_min
            mash_chart_points.append({"x": mash_elapsed, "y": float(step.temperature_c)})
            if index + 1 < len(mash_steps):
                mash_chart_points.append(
                    {"x": mash_elapsed, "y": float(mash_steps[index + 1].temperature_c)}
                )

    def inline_form(form, form_id):
        for field in form.fields.values():
            field.widget.attrs["form"] = form_id
        return form

    malt_rows = [
        {
            "ingredient": malt,
            "proportion": round(float(malt.amount_g) / malt_total * 100, 1) if malt_total else 0,
            "edit_form": inline_form(
                edit_forms.get(malt.pk, MaltForm(instance=malt)),
                f"edit-malt-{malt.pk}",
            ),
        }
        for malt in malts
    ]
    hop_rows = [
        {
            "ingredient": hop,
            "ibu": tinseth_ibu([hop], float(recipe.batch_size_l), og or float(recipe.target_og)),
            "edit_form": inline_form(
                edit_forms.get(hop.pk, HopForm(instance=hop)),
                f"edit-hop-{hop.pk}",
            ),
        }
        for hop in hops
    ]
    hop_rows.sort(key=lambda row: (-row["ingredient"].boil_minutes, row["ingredient"].pk))
    boil_hop_rows = [
        row for row in hop_rows
        if row["ingredient"].addition in ("", "Ébullition")
    ]
    cooling_hop_rows = [
        row for row in hop_rows
        if row["ingredient"].addition == "Refroidissement"
    ]
    boil_events = [{"type": "start"}]
    if boil_hop_rows:
        previous_remaining = recipe.boil_time_min
        for row in boil_hop_rows:
            remaining = row["ingredient"].boil_minutes
            wait_minutes = previous_remaining - remaining
            if wait_minutes > 0:
                boil_events.append({"type": "timer", "minutes": wait_minutes})
            boil_events.append({"type": "hop", "row": row})
            previous_remaining = remaining
        if previous_remaining > 0:
            boil_events.append({"type": "timer", "minutes": previous_remaining})
    else:
        boil_events.append({"type": "timer", "minutes": recipe.boil_time_min})
    boil_events.append({"type": "cool"})
    for row in cooling_hop_rows:
        boil_events.append({"type": "cooling_hop", "row": row})
    return render(
        request,
        "recipes/detail.html",
        {
            "recipe": recipe,
            "name_form": RecipeNameForm(instance=recipe),
            "category_form": category_form,
            "efficiency_form": RecipeEfficiencyForm(instance=recipe),
            "notes_form": RecipeNotesForm(instance=recipe),
            "scale_form": ScaleForm(initial={"batch_size_l": recipe.batch_size_l}),
            "malt_form": MaltForm(),
            "hop_form": HopForm(),
            "yeast_form": YeastForm(),
            "other_form": OtherForm(),
            "malt_rows": malt_rows,
            "malt_total_g": malt_total,
            "mash_chart_points": mash_chart_points,
            "water_equipment": {
                "diameter_cm": float(equipment.diameter_cm),
                "height_cm": float(equipment.height_cm),
                "evaporation_l_min": float(equipment.evaporation_l_min),
                "grain_absorption_l_kg": float(equipment.grain_absorption_l_kg),
                "dead_space_l": float(equipment.dead_space_l),
            },
            "hop_rows": hop_rows,
            "boil_events": boil_events,
            "yeast_rows": [
                {
                    "ingredient": yeast,
                    "edit_form": inline_form(
                        edit_forms.get(yeast.pk, YeastForm(instance=yeast)),
                        f"edit-yeast-{yeast.pk}",
                    ),
                }
                for yeast in yeasts
            ],
            "other_rows": [
                {
                    "ingredient": other,
                    "edit_form": inline_form(
                        edit_forms.get(other.pk, OtherForm(instance=other)),
                        f"edit-other-{other.pk}",
                    ),
                }
                for other in others
            ],
            "mash_steps": recipe.mash_steps.all(),
            "mash_rows": [
                {"step": step, "edit_form": MashStepForm(instance=step)}
                for step in recipe.mash_steps.all()
            ],
            "mash_form": MashStepForm(),
            "fermentation_steps": recipe.fermentation_steps.all(),
            "fermentation_rows": [
                {"step": step, "edit_form": FermentationStepForm(instance=step)}
                for step in recipe.fermentation_steps.all()
            ],
            "fermentation_form": FermentationStepForm(),
            "catalog_data": [
                {
                    "id": item.pk,
                    "name": item.name,
                    "manufacturer": item.manufacturer,
                    "form": item.form,
                    "color_ebc": str(item.color_ebc),
                    "potential_yield": str(item.potential_yield),
                    "alpha_acid": str(item.alpha_acid),
                    "attenuation": str(item.attenuation),
                }
                for item in IngredientCatalog.objects.all()
            ],
            "estimated_og": og,
            "estimated_plato": plato_from_gravity(og) if og else None,
            "estimated_ibu": ibu,
            "estimated_ebc": ebc,
            "estimated_abv": abv,
            "estimated_final_gravity": final_gravity,
            "mash_temperature": average_mash_temperature(mash_steps),
            "has_mash_steps": bool(mash_steps),
            "ibu_df_ratio": ibu_df_ratio,
            "ibu_df_comment": ibu_df_comment,
            "style_indicators": style_indicators,
        },
    )


def mash_list(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    return render(
        request,
        "recipes/mash.html",
        {"recipe": recipe, "mash_steps": recipe.mash_steps.all(), "form": MashStepForm()},
    )


def mash_create(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form = MashStepForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        step = form.save(commit=False)
        step.recipe = recipe
        step.position = (recipe.mash_steps.aggregate(max_position=Max("position"))["max_position"] or 0) + 1
        step.save()
        messages.success(request, f"Le palier « {step.name} » a été ajouté.")
    return redirect("recipes:mash", pk=recipe.pk)


def mash_edit(request, pk):
    step = get_object_or_404(MashStep, pk=pk)
    form = MashStepForm(request.POST or None, instance=step)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Le palier « {step.name} » a été modifié.")
        return redirect("recipes:mash", pk=step.recipe_id)
    return render(request, "recipes/mash_form.html", {"form": form, "step": step})


@require_POST
def mash_delete(request, pk):
    step = get_object_or_404(MashStep, pk=pk)
    recipe_id = step.recipe_id
    step_name = step.name
    step.delete()
    messages.success(request, f"Le palier « {step_name} » a été supprimé.")
    return redirect("recipes:mash", pk=recipe_id)


def fermentation_create(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form = FermentationStepForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        step = form.save(commit=False)
        step.recipe = recipe
        step.position = (recipe.fermentation_steps.aggregate(max_position=Max("position"))["max_position"] or 0) + 1
        step.save()
        messages.success(request, "Le palier de fermentation a été ajouté.")
    return redirect("recipes:detail", pk=recipe.pk)


def fermentation_edit(request, pk):
    step = get_object_or_404(FermentationStep, pk=pk)
    form = FermentationStepForm(request.POST or None, instance=step)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Le palier de fermentation a été modifié.")
    return redirect("recipes:detail", pk=step.recipe_id)


@require_POST
def fermentation_delete(request, pk):
    step = get_object_or_404(FermentationStep, pk=pk)
    recipe_id = step.recipe_id
    step.delete()
    messages.success(request, "Le palier de fermentation a été supprimé.")
    return redirect("recipes:detail", pk=recipe_id)


@require_POST
def fermentation_reorder(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    step_ids = request.POST.getlist("step_order")
    steps = list(recipe.fermentation_steps.filter(pk__in=step_ids))
    if len(steps) != len(step_ids) or len(set(step_ids)) != len(step_ids):
        messages.error(request, "L’ordre des phases de fermentation est invalide.")
        return redirect("recipes:detail", pk=recipe.pk)
    steps_by_id = {str(step.pk): step for step in steps}
    with transaction.atomic():
        for position, step_id in enumerate(step_ids, start=1):
            step = steps_by_id[step_id]
            if step.position != position:
                FermentationStep.objects.filter(pk=step.pk).update(position=position)
    messages.success(request, "L’ordre des phases de fermentation a été enregistré.")
    return redirect("recipes:detail", pk=recipe.pk)


def recipe_create(request):
    equipment = EquipmentSettings.objects.first()
    initial = {"efficiency": equipment.mash_efficiency} if equipment else {}
    form = RecipeForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        recipe = form.save()
        messages.success(request, f"La recette « {recipe.name} » a été créée.")
        return redirect("recipes:list")
    return render(request, "recipes/form.html", {"form": form})


def recipe_export(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    response = HttpResponse(export_recipe(recipe), content_type="application/xml")
    response["Content-Disposition"] = f'attachment; filename="{recipe.name}.xml"'
    return response


def boil_settings_update(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form = BoilSettingsForm(request.POST or None, instance=recipe)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "La durée globale d'ébullition a été mise à jour.")
    return redirect("recipes:detail", pk=recipe.pk)


def recipe_efficiency_update(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form = RecipeEfficiencyForm(request.POST or None, instance=recipe)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "L’efficacité de la recette a été mise à jour.")
    return redirect("recipes:detail", pk=recipe.pk)


def recipe_name_update(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form = RecipeNameForm(request.POST or None, instance=recipe)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Le nom de la recette a été mis à jour.")
    return redirect("recipes:detail", pk=recipe.pk)


def recipe_category_update(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form = RecipeCategoryForm(request.POST or None, instance=recipe)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "La catégorie BJCP de la recette a été mise à jour.")
    return redirect("recipes:detail", pk=recipe.pk)


def recipe_scale(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form = ScaleForm(request.POST or None, initial={"batch_size_l": recipe.batch_size_l})
    if request.method == "POST" and form.is_valid():
        new_volume = form.cleaned_data["batch_size_l"]
        if request.POST.get("action") == "volume_only":
            recipe.batch_size_l = new_volume
            recipe.save(update_fields=["batch_size_l"])
            messages.success(request, f"Le volume de la recette est maintenant de {new_volume} L. Les ingrédients n’ont pas été modifiés.")
            return redirect("recipes:detail", pk=recipe.pk)
        old_volume = Decimal(recipe.batch_size_l)
        ratio = new_volume / old_volume
        with transaction.atomic():
            for ingredient in recipe.ingredients.all():
                precision = Decimal("1") if ingredient.kind in (Ingredient.Kind.MALT, Ingredient.Kind.YEAST) else Decimal("0.1")
                ingredient.amount_g = (Decimal(ingredient.amount_g) * ratio).quantize(precision)
                ingredient.cost_total = (Decimal(ingredient.cost_total) * ratio).quantize(Decimal("0.01"))
                ingredient.save(update_fields=["amount_g", "cost_total"])
            recipe.batch_size_l = new_volume
            recipe.save(update_fields=["batch_size_l"])
        messages.success(request, f"La recette a été redimensionnée pour {new_volume} L.")
    return redirect("recipes:detail", pk=recipe.pk)


def recipe_notes_update(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form = RecipeNotesForm(request.POST or None, instance=recipe)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Les notes de la recette ont été enregistrées.")
    return redirect("recipes:detail", pk=recipe.pk)


def _catalog_for_imported_ingredient(ingredient):
    return IngredientCatalog.objects.filter(
        kind=ingredient["kind"],
        name__iexact=ingredient["name"],
    ).first()


def _create_catalog_from_imported_ingredient(ingredient):
    return IngredientCatalog.objects.create(
        name=ingredient["name"],
        kind=ingredient["kind"],
        manufacturer=ingredient.get("manufacturer", ""),
        product_id=ingredient.get("product_id", ""),
        form=ingredient.get("form", ""),
        color_ebc=ingredient.get("color_ebc", 0),
        potential_yield=ingredient.get("potential_yield", 80),
        alpha_acid=ingredient.get("alpha_acid", 5),
        attenuation=ingredient.get("attenuation", 78),
    )


def _category_for_imported_recipe(data):
    code = str(data.get("category_code", "")).strip()
    name = str(data.get("category_name", "")).strip()
    if code:
        category = BeerCategory.objects.filter(code__iexact=code).first()
        if category:
            return category
    if name:
        return BeerCategory.objects.filter(name__iexact=name).first()
    return None


def _finish_recipe_import(data, catalog_indexes, recipe=None, name=None):
    with transaction.atomic():
        with suspend_versioning():
            recipe = recipe or Recipe()
            recipe.name = name or data["name"]
            recipe.batch_size_l = data["batch_size_l"]
            recipe.efficiency = data["efficiency"]
            recipe.target_og = data["target_og"]
            recipe.target_ibu = data["target_ibu"]
            recipe.boil_time_min = data["boil_time_min"]
            recipe.category = _category_for_imported_recipe(data)
            recipe.save()
            recipe.ingredients.all().delete()
            recipe.mash_steps.all().delete()
            recipe.fermentation_steps.all().delete()
            for index, imported_ingredient in enumerate(data["ingredients"]):
                catalog = _catalog_for_imported_ingredient(imported_ingredient)
                if catalog is None and index in catalog_indexes:
                    catalog = _create_catalog_from_imported_ingredient(imported_ingredient)
                elif catalog is not None and imported_ingredient.get("form") and not catalog.form:
                    catalog.form = imported_ingredient["form"]
                    catalog.save(update_fields=["form"])
                Ingredient.objects.create(recipe=recipe, catalog=catalog, **imported_ingredient)
            for step in data.get("mash_steps", []):
                MashStep.objects.create(recipe=recipe, **step)
            for step in data.get("fermentation_steps", []):
                FermentationStep.objects.create(recipe=recipe, **step)
        RecipeVersion.objects.filter(recipe=recipe).delete()
        recipe.current_version = None
        recipe.save(update_fields=["current_version"])
        save_version(recipe, "Version initiale · Import BeerXML")
    return recipe


def _recipe_import_preview(imports):
    for index, data in enumerate(imports):
        data["file_index"] = index
        data["source_name"] = data.get("source_name") or data["name"]
        data["missing_catalog"] = [
            {"index": ingredient_index, **ingredient}
            for ingredient_index, ingredient in enumerate(data["ingredients"])
            if _catalog_for_imported_ingredient(ingredient) is None
        ]
        data["name_conflict"] = Recipe.objects.filter(name__iexact=data["name"]).first()
    return imports


def recipe_import(request):
    form = BeerXMLUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and request.POST.get("confirm_catalog") == "1":
        imports = request.session.get("pending_beerxml_imports")
        if imports is None:
            legacy_data = request.session.get("pending_beerxml_import")
            imports = [legacy_data] if legacy_data else None
        if not imports:
            form.add_error(None, "La session d’import a expiré. Veuillez sélectionner à nouveau le fichier BeerXML.")
        else:
            imports = _recipe_import_preview(imports)
            imported_recipes = []
            for file_index, data in enumerate(imports):
                catalog_indexes = {
                    int(value.split(":", 1)[1])
                    for value in request.POST.getlist("add_to_catalog")
                    if value.startswith(f"{file_index}:") and value.split(":", 1)[1].isdigit()
                }
                legacy_indexes = (
                    {int(value) for value in request.POST.getlist("add_to_catalog") if value.isdigit()}
                    if file_index == 0 else set()
                )
                catalog_indexes |= legacy_indexes
                name = request.POST.get(
                    f"import_name_{file_index}",
                    request.POST.get("import_name", data["name"]) if file_index == 0 else data["name"],
                ).strip()
                existing = Recipe.objects.filter(name__iexact=name).first()
                conflict_action = request.POST.get(
                    f"conflict_action_{file_index}",
                    request.POST.get("conflict_action", "rename") if file_index == 0 else "rename",
                )
                if existing and conflict_action != "replace":
                    return render(request, "recipes/import_confirm.html", {"imports": _recipe_import_preview(imports)})
                imported_recipes.append(
                    _finish_recipe_import(
                        data,
                        catalog_indexes,
                        recipe=existing if conflict_action == "replace" else None,
                        name=name,
                    )
                )
            request.session.pop("pending_beerxml_imports", None)
            request.session.pop("pending_beerxml_import", None)
            messages.success(request, f"{len(imported_recipes)} recette(s) ont été importée(s).")
            return redirect(
                "recipes:detail" if len(imported_recipes) == 1 else "recipes:list",
                pk=imported_recipes[0].pk,
            ) if len(imported_recipes) == 1 else redirect("recipes:list")
    elif request.method == "POST" and form.is_valid():
        try:
            imports = [
                {"source_name": uploaded_file.name, **import_recipe(uploaded_file.read())}
                for uploaded_file in form.cleaned_data["file"]
            ]
            imports = _recipe_import_preview(imports)
            if any(data["missing_catalog"] or data["name_conflict"] for data in imports):
                request.session["pending_beerxml_imports"] = [
                    {key: value for key, value in data.items() if key != "name_conflict"}
                    for data in imports
                ]
                return render(request, "recipes/import_confirm.html", {"imports": imports})
            imported_recipes = [_finish_recipe_import(data, set()) for data in imports]
        except (ValueError, TypeError, ElementTree.ParseError) as error:
            form.add_error("file", f"Import BeerXML impossible : {error}")
        else:
            messages.success(request, f"{len(imported_recipes)} recette(s) ont été importée(s).")
            return redirect(
                "recipes:detail", pk=imported_recipes[0].pk
            ) if len(imported_recipes) == 1 else redirect("recipes:list")
    return render(request, "recipes/import.html", {"form": form})


@require_POST
def recipe_delete(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    recipe_name = recipe.name
    recipe.versions.all().delete()
    recipe.delete()
    messages.success(request, f"La recette « {recipe_name} » a été supprimée.")
    return redirect("recipes:list")


def ingredient_create(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form_classes = {
        Ingredient.Kind.MALT: MaltForm,
        Ingredient.Kind.HOP: HopForm,
        Ingredient.Kind.YEAST: YeastForm,
        Ingredient.Kind.OTHER: OtherForm,
    }
    kind = request.POST.get("kind")
    form_class = form_classes.get(kind)
    if form_class is None:
        messages.error(request, "Le type d'ingrédient est invalide.")
        return redirect("recipes:detail", pk=recipe.pk)
    form = form_class(request.POST)
    if request.method == "POST" and form.is_valid():
        ingredient = form.save(commit=False)
        ingredient.recipe = recipe
        ingredient.kind = kind
        if ingredient.catalog:
            catalog = ingredient.catalog
            ingredient.name = ingredient.name or catalog.name
            ingredient.manufacturer = catalog.manufacturer
            ingredient.product_id = catalog.product_id
            ingredient.form = catalog.form
            if kind == Ingredient.Kind.MALT:
                ingredient.color_ebc = catalog.color_ebc
                ingredient.potential_yield = catalog.potential_yield
            elif kind == Ingredient.Kind.HOP:
                ingredient.alpha_acid = catalog.alpha_acid
            elif kind == Ingredient.Kind.YEAST:
                ingredient.attenuation = catalog.attenuation
        ingredient.save()
        messages.success(request, f"{ingredient.name} a été ajouté à la recette.")
    return redirect("recipes:detail", pk=recipe.pk)


def ingredient_edit(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    form_classes = {
        Ingredient.Kind.MALT: MaltForm,
        Ingredient.Kind.HOP: HopForm,
        Ingredient.Kind.YEAST: YeastForm,
        Ingredient.Kind.OTHER: OtherForm,
    }
    form_class = form_classes[ingredient.kind]
    form = form_class(request.POST or None, instance=ingredient)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{ingredient.name} a été modifié.")
        return redirect("recipes:detail", pk=ingredient.recipe_id)
    return recipe_detail(request, ingredient.recipe_id, {ingredient.pk: form})


@require_POST
def ingredient_delete(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    recipe_id = ingredient.recipe_id
    ingredient_name = ingredient.name
    ingredient.delete()
    messages.success(request, f"{ingredient_name} a été supprimé.")
    return redirect("recipes:detail", pk=recipe_id)

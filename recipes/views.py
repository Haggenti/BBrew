from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from xml.etree import ElementTree
import json
import calendar
from itertools import groupby
from datetime import date, timedelta

from .calculations import average_mash_temperature, ebc_color_rgb, estimated_abv, estimated_color_ebc, estimated_efficiency, estimated_final_gravity, estimated_og, ibu_final_gravity_comment, ibu_final_gravity_ratio, plato_from_gravity, tinseth_ibu
from .beerxml import export_recipe, import_recipe
from decimal import Decimal
from decimal import ROUND_CEILING, ROUND_FLOOR
from django.utils import timezone

from .forms import BackupUploadForm, BeerCategoryForm, BeerXMLUploadForm, BoilSettingsForm, BrewForm, CatalogConsumableForm, CatalogHopForm, CatalogMaltForm, CatalogOtherForm, CatalogYeastForm, CatalogForm, EquipmentSettingsForm, FermentationStepForm, HopForm, IngredientCostForm, MaltForm, MashGraphSettingsForm, MashStepForm, OtherForm, RecipeCategoryForm, RecipeEfficiencyForm, RecipeForm, RecipeNameForm, RecipeNotesForm, RecipeTastingForm, ScaleForm, ShoppingItemForm, YeastForm
from .models import BeerCategory, Brew, EquipmentSettings, FermentationStep, Ingredient, IngredientCatalog, MashStep, Recipe, RecipeVersion, ShoppingItem
from .signals import save_version, suspend_versioning
from .versioning import describe_version_change
from .backup import create_backup, restore_backup
from .catalog_rules import CATALOG_KIND_RULES
from .stock_logic import brew_stock_requirements, planned_stock_needs


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


def dashboard(request):
    today = timezone.localdate()
    planned_needs = planned_stock_needs()
    stock_alert_count = sum(
        1
        for item in IngredientCatalog.objects.all()
        if planned_needs.get(item.pk, {}).get("required", 0) > item.quantity_available
    )
    dashboard = {
        "recipe_count": Recipe.objects.count(),
        "upcoming_brew_count": Brew.objects.filter(
            planned_date__gte=today,
        ).exclude(status__in=[Brew.Status.COMPLETED, Brew.Status.CANCELLED]).count(),
        "shopping_count": ShoppingItem.objects.filter(is_ordered=False).count(),
        "stock_alert_count": stock_alert_count,
    }
    return render(request, "recipes/dashboard.html", {"dashboard": dashboard})


def brew_list(request):
    brews = list(Brew.objects.all())
    existing_shopping_names = {
        item.name.strip().casefold()
        for item in ShoppingItem.objects.all()
    }
    for brew in brews:
        if brew.status == Brew.Status.PLANNED:
            requirements = brew_stock_requirements(brew)
            missing_items = [
                item for item in requirements
                if item["catalog"] is None
                or item["available"] is None
                or item["available"] < item["required"]
            ]
            brew.stock_missing_items = [
                item for item in missing_items
                if item["name"].strip().casefold() not in existing_shopping_names
            ]
            if brew.recipe_version and not missing_items:
                brew.stock_status = "ok"
            elif missing_items and not brew.stock_missing_items:
                brew.stock_status = "shopping"
            else:
                brew.stock_status = "insufficient"
        else:
            brew.stock_status = None
            brew.stock_missing_items = []
    today = timezone.localdate()
    try:
        if request.GET.get("month"):
            calendar_date = date.fromisoformat(f"{request.GET['month']}-01")
        elif "month_number" in request.GET or "year" in request.GET:
            selected_year = request.GET.get("year")
            selected_month = request.GET.get("month_number")
            if selected_year is None or selected_month is None:
                raise ValueError
            calendar_date = date(
                int(selected_year),
                int(selected_month),
                1,
            )
        else:
            raise ValueError
    except (TypeError, ValueError):
        calendar_date = today.replace(day=1)
    previous_month = (calendar_date.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (calendar_date.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_names = (
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    )
    calendar_days = {}
    bottling_days = {}
    for brew in brews:
        if brew.planned_date:
            calendar_days.setdefault(brew.planned_date, []).append(brew)
        if brew.completed_date:
            bottling_days.setdefault(brew.completed_date, []).append(brew)
    month_weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(
        calendar_date.year, calendar_date.month
    )
    calendar_start = month_weeks[0][0]
    calendar_end = month_weeks[-1][-1]
    span_entries = sorted(
        (
            brew for brew in brews
            if brew.planned_date
            and brew.completed_date
            and brew.planned_date <= calendar_end
            and brew.completed_date >= calendar_start
        ),
        key=lambda brew: (brew.planned_date, brew.completed_date, brew.pk),
    )
    lane_end_dates = []
    span_lanes = {}
    for brew in span_entries:
        lane = next(
            (
                lane_index
                for lane_index, lane_end in enumerate(lane_end_dates)
                if lane_end < brew.planned_date
            ),
            len(lane_end_dates),
        )
        if lane == len(lane_end_dates):
            lane_end_dates.append(brew.completed_date)
        else:
            lane_end_dates[lane] = brew.completed_date
        span_lanes[brew.pk] = lane
    calendar_span_lanes = max(1, len(lane_end_dates))
    calendar_weeks = []
    for week in month_weeks:
        spans_by_day = {}
        for brew in span_entries:
            for day in week:
                if brew.planned_date <= day <= brew.completed_date:
                    spans_by_day.setdefault(day, []).append(
                        {
                            "brew": brew,
                            "lane": span_lanes[brew.pk],
                            "starts": day == brew.planned_date,
                            "ends": day == brew.completed_date,
                            "continues_before": day == week[0] and brew.planned_date < day,
                            "continues_after": day == week[-1] and brew.completed_date > day,
                        }
                    )
        calendar_weeks.append(
            {
                "number": week[0].isocalendar().week,
                "days": [
                    {
                        "number": day.day,
                        "date": day,
                        "in_month": day.month == calendar_date.month,
                        "brews": calendar_days.get(day, []),
                        "bottlings": [
                            brew for brew in bottling_days.get(day, [])
                            if not brew.planned_date or not brew.completed_date
                        ],
                        "brew_spans": spans_by_day.get(day, []),
                    }
                    for day in week
                ],
            }
        )
    return render(
        request,
        "recipes/brews.html",
        {
            "brews": brews,
            "calendar_month": f"{month_names[calendar_date.month - 1]} {calendar_date.year}",
            "calendar_weekdays": ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"),
            "calendar_weeks": calendar_weeks,
            "calendar_span_lanes": calendar_span_lanes,
            "calendar_days": calendar_days,
            "calendar_today": today,
            "calendar_date": calendar_date,
            "calendar_selected_month": calendar_date.month,
            "calendar_selected_year": calendar_date.year,
            "calendar_years": sorted(
                set(range(max(1, today.year - 10), min(9999, today.year + 10) + 1))
                | {calendar_date.year}
            ),
            "calendar_months": tuple(enumerate(month_names, start=1)),
            "today_month": today.strftime("%Y-%m"),
            "previous_month": previous_month.strftime("%Y-%m"),
            "next_month": next_month.strftime("%Y-%m"),
            "calendar_statuses": Brew.Status.choices,
        },
    )


def shopping_list(request):
    items_query = ShoppingItem.objects.select_related("catalog").prefetch_related("source_brews")
    items = list(items_query)
    catalog_items = IngredientCatalog.objects.all().order_by("kind", "name")
    catalog_by_name = {item.name.casefold(): item for item in catalog_items}
    for item in items:
        item.catalog_match = item.catalog or catalog_by_name.get(item.name.strip().casefold())
        item.remaining_quantity = (
            max(item.planned_quantity - (item.received_quantity or 0), 0)
            if item.planned_quantity is not None
            else None
        )
    return render(
        request,
        "recipes/shopping_list.html",
        {
            "items": items,
            "todo_items": [item for item in items if not item.is_ordered],
            "ordered_items": [
                item for item in items
                if item.is_ordered and not item.is_received and not item.received_quantity
            ],
            "received_items": [
                item for item in items
                if item.is_ordered and (item.is_received or item.received_quantity)
            ],
            "form": ShoppingItemForm(),
            "catalog_items": catalog_items,
            "catalog_kinds": IngredientCatalog.Kind.choices,
            "shopping_quantity_presets": {
                kind: rules["quantity_presets"]
                for kind, rules in CATALOG_KIND_RULES.items()
            },
        },
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
    item.is_ordered = not item.is_ordered
    item.save(update_fields=["is_ordered"])
    return redirect("recipes:shopping_list")


@require_POST
def shopping_item_mark_received(request, pk):
    item = get_object_or_404(ShoppingItem, pk=pk)
    if not item.is_ordered:
        messages.error(request, f"« {item.name} » doit d’abord être marqué comme commandé.")
        return redirect("recipes:shopping_list")
    item.is_received = True
    item.save(update_fields=["is_received"])
    messages.success(request, f"« {item.name} » est maintenant en attente d’intégration au stock.")
    return redirect("recipes:shopping_list")


@require_POST
def shopping_item_delete(request, pk):
    item = get_object_or_404(ShoppingItem, pk=pk)
    item.delete()
    messages.success(request, "Article supprimé de la liste de courses.")
    return redirect("recipes:shopping_list")


@require_POST
def shopping_item_receive(request, pk):
    item = get_object_or_404(ShoppingItem, pk=pk)
    if not item.is_ordered:
        messages.error(request, f"« {item.name} » doit d’abord être marqué comme commandé.")
        return redirect("recipes:shopping_list")
    try:
        quantity = int(request.POST.get("quantity", ""))
    except (TypeError, ValueError):
        quantity = 0
    if quantity <= 0:
        messages.error(request, "La quantité reçue doit être un nombre entier positif.")
        return redirect("recipes:shopping_list")

    catalog_id = request.POST.get("catalog_id")
    catalog = item.catalog
    created_catalog = False
    if catalog_id == "new":
        kind = request.POST.get("new_kind", "")
        if kind not in IngredientCatalog.Kind.values:
            messages.error(request, "Sélectionnez un type valide pour la nouvelle fiche de stock.")
            return redirect("recipes:shopping_list")
    elif catalog is None and catalog_id:
        catalog = IngredientCatalog.objects.filter(pk=catalog_id).first()
    if catalog is None:
        catalog = IngredientCatalog.objects.filter(name__iexact=item.name.strip()).first()

    if catalog is None and catalog_id != "new":
        messages.error(request, f"Aucune fiche de stock ne correspond à « {item.name} ».")
        return redirect("recipes:shopping_list")

    with transaction.atomic():
        if catalog_id == "new":
            catalog = IngredientCatalog.objects.create(
                name=item.name.strip(),
                kind=kind,
                quantity_available=0,
            )
            created_catalog = True
        else:
            catalog = IngredientCatalog.objects.select_for_update().get(pk=catalog.pk)
        catalog.quantity_available += quantity
        catalog.save(update_fields=["quantity_available"])
        item.delete()
    suffix = " (nouvelle fiche créée)" if created_catalog else ""
    messages.success(request, f"{quantity} unité(s) de « {item.name} » ajoutée(s) au stock{suffix}.")
    return redirect("recipes:shopping_list")


@require_POST
def shopping_list_clear(request):
    deleted_count, _ = ShoppingItem.objects.filter(is_ordered=False).delete()
    if deleted_count:
        messages.success(request, "La liste de courses a été vidée.")
    else:
        messages.info(request, "La liste de courses est déjà vide.")
    return redirect("recipes:shopping_list")


@require_POST
def shopping_list_clear_received(request):
    deleted_count, _ = ShoppingItem.objects.filter(is_ordered=True).delete()
    if deleted_count:
        messages.success(request, "Les articles reçus ont été supprimés de la liste de courses.")
    else:
        messages.info(request, "Aucun article reçu à supprimer.")
    return redirect("recipes:shopping_list")


@require_POST
def brew_missing_stock_to_shopping(request, pk):
    brew = get_object_or_404(Brew, pk=pk)
    names = request.POST.getlist("names") or [request.POST.get("name", "")]
    names = list(dict.fromkeys(name.strip() for name in names if name.strip()))
    existing_items = {
        item.name.casefold(): item
        for item in ShoppingItem.objects.all()
    }
    added_names = []
    for name in names:
        normalized_name = name.casefold()
        if normalized_name in existing_items:
            existing_items[normalized_name].source_brews.add(brew)
            continue
        shopping_item = ShoppingItem.objects.create(name=name)
        shopping_item.source_brews.add(brew)
        existing_items[normalized_name] = shopping_item
        added_names.append(name)

    if not names:
        messages.error(request, "Impossible d’ajouter un article sans nom.")
    elif added_names:
        messages.success(
            request,
            f"{len(added_names)} article(s) ajouté(s) à la liste de courses.",
        )
    else:
        messages.info(request, "Les articles sélectionnés sont déjà dans la liste de courses.")
    return redirect("recipes:brews")


def brew_create(request):
    initial = {}
    recipe_id = request.GET.get("recipe")
    if request.method == "GET" and recipe_id:
        initial["recipe"] = Recipe.objects.filter(pk=recipe_id).first()
    form = BrewForm(
        request.POST or None,
        initial=initial,
        equipment_settings=EquipmentSettings.objects.first(),
    )
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
        {
            "brew": brew,
            "comparison": comparison,
            "stock_requirements": brew_stock_requirements(brew),
            "capsule_catalogs": IngredientCatalog.objects.filter(
                kind=IngredientCatalog.Kind.CONSUMABLE
            ),
        },
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


@require_POST
def brew_status_cycle(request, pk):
    brew = get_object_or_404(Brew, pk=pk)
    statuses = [status for status, _ in Brew.Status.choices]
    current_index = statuses.index(brew.status)
    brew.status = statuses[(current_index + 1) % len(statuses)]
    brew.save(update_fields=["status"])
    messages.success(request, f"Statut mis à jour : {brew.get_status_display()}.")
    if request.POST.get("return_to") == "detail":
        return redirect("recipes:brew_detail", pk=brew.pk)
    return redirect("recipes:brews")


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
        bag_weight_g = float(equipment.bag_weight_g) / 1000 if equipment else 0
        residual_water_kg = float(brew.actual_spent_grains_weight_kg) - bag_weight_g - dry_grains_kg
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
    requirements = brew_stock_requirements(brew)
    consumable = {item["key"]: item for item in requirements if item["catalog"] and not item["consumed"]}
    with transaction.atomic():
        consumed_items = set(brew.stock_consumed_items or [])
        locked_items = {}
        for key in selected & consumable.keys():
            requirement = consumable[key]
            item = IngredientCatalog.objects.select_for_update().get(pk=requirement["catalog_id"])
            locked_items[key] = item
            if item.quantity_available < requirement["required"]:
                messages.error(
                    request,
                    f"Stock insuffisant pour « {item.name} » : "
                    f"{item.quantity_available} disponible(s), {requirement['required']} nécessaire(s).",
                )
        insufficient = [
            key for key in selected & consumable.keys()
            if locked_items[key].quantity_available < consumable[key]["required"]
        ]
        if insufficient:
            return redirect("recipes:brew_detail", pk=brew.pk)

        for key in selected & consumable.keys():
            requirement = consumable[key]
            item = locked_items[key]
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
    requirements = brew_stock_requirements(brew)
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


@require_POST
def brew_consume_capsules(request, pk):
    brew = get_object_or_404(Brew, pk=pk)
    if brew.capsules_consumed_at:
        messages.error(request, "Les capsules de ce brassin ont déjà été consommées.")
        return redirect("recipes:brew_detail", pk=brew.pk)
    if not brew.bottled_bottle_count or not brew.capsule_catalog:
        messages.error(request, "Indiquez le nombre de bouteilles et le type de capsules avant de consommer le stock.")
        return redirect("recipes:brew_detail", pk=brew.pk)
    if brew.capsule_catalog.kind != IngredientCatalog.Kind.CONSUMABLE:
        messages.error(request, "La fiche sélectionnée n’est pas un consommable.")
        return redirect("recipes:brew_detail", pk=brew.pk)

    with transaction.atomic():
        capsules = IngredientCatalog.objects.select_for_update().get(pk=brew.capsule_catalog_id)
        if capsules.quantity_available < brew.bottled_bottle_count:
            messages.error(
                request,
                f"Stock insuffisant : {capsules.quantity_available} capsule(s) disponible(s) pour "
                f"{brew.bottled_bottle_count} nécessaire(s).",
            )
            return redirect("recipes:brew_detail", pk=brew.pk)
        capsules.quantity_available -= brew.bottled_bottle_count
        capsules.save(update_fields=["quantity_available"])
        brew.capsules_consumed = brew.bottled_bottle_count
        brew.capsules_consumed_at = timezone.now()
        brew.save(update_fields=["capsules_consumed", "capsules_consumed_at"])
    messages.success(request, f"{brew.capsules_consumed} capsule(s) consommée(s).")
    return redirect("recipes:brew_detail", pk=brew.pk)


@require_POST
def brew_bottling_update(request, pk):
    brew = get_object_or_404(Brew, pk=pk)
    try:
        bottle_count = int(request.POST.get("bottled_bottle_count", ""))
    except (TypeError, ValueError):
        bottle_count = 0
    capsule_catalog = IngredientCatalog.objects.filter(
        pk=request.POST.get("capsule_catalog"),
        kind=IngredientCatalog.Kind.CONSUMABLE,
    ).first()
    if bottle_count <= 0 or capsule_catalog is None:
        messages.error(request, "Indiquez un nombre de bouteilles positif et un consommable de capsules valide.")
        return redirect("recipes:brew_detail", pk=brew.pk)
    if brew.capsules_consumed_at:
        messages.error(request, "La consommation des capsules a déjà été enregistrée.")
        return redirect("recipes:brew_detail", pk=brew.pk)
    update_fields = ["bottled_bottle_count", "capsule_catalog"]
    if "completed_date" in request.POST:
        raw_completed_date = request.POST.get("completed_date", "").strip()
        if raw_completed_date:
            try:
                completed_date = date.fromisoformat(raw_completed_date)
            except ValueError:
                messages.error(request, "La date de mise en bouteille est invalide.")
                return redirect("recipes:brew_detail", pk=brew.pk)
            if brew.planned_date and completed_date < brew.planned_date:
                messages.error(
                    request,
                    "La date de mise en bouteille ne peut pas être antérieure à la date du brassage.",
                )
                return redirect("recipes:brew_detail", pk=brew.pk)
        else:
            completed_date = None
        brew.completed_date = completed_date
        update_fields.append("completed_date")
    brew.bottled_bottle_count = bottle_count
    brew.capsule_catalog = capsule_catalog
    brew.save(update_fields=update_fields)
    messages.success(request, "Les informations de mise en bouteille ont été enregistrées.")
    return redirect("recipes:brew_detail", pk=brew.pk)


@require_POST
def brew_rollback_capsules(request, pk):
    brew = get_object_or_404(Brew, pk=pk)
    if not brew.capsules_consumed_at or not brew.capsule_catalog_id or not brew.capsules_consumed:
        messages.error(request, "Aucune consommation de capsules à annuler.")
        return redirect("recipes:brew_detail", pk=brew.pk)
    with transaction.atomic():
        capsules = IngredientCatalog.objects.select_for_update().get(pk=brew.capsule_catalog_id)
        capsules.quantity_available += brew.capsules_consumed
        capsules.save(update_fields=["quantity_available"])
        brew.capsules_consumed = 0
        brew.capsules_consumed_at = None
        brew.save(update_fields=["capsules_consumed", "capsules_consumed_at"])
    messages.success(request, "La consommation des capsules a été annulée.")
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
def category_copy_ranges(request, pk):
    source = get_object_or_404(BeerCategory, pk=request.POST.get("source_id"))
    target = get_object_or_404(BeerCategory, pk=pk)
    range_fields = ("og_min", "og_max", "fg_min", "fg_max", "ibu_min", "ibu_max", "ebc_min", "ebc_max", "abv_min", "abv_max")
    for field in range_fields:
        setattr(target, field, getattr(source, field))
    target.save(update_fields=list(range_fields))
    messages.success(request, f"Les fourchettes de « {source.name} » ont été copiées vers « {target.name} ».")
    return redirect("recipes:categories")


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
    for field in (
        "name",
        "batch_size_l",
        "efficiency",
        "target_og",
        "target_ibu",
        "boil_time_min",
        "notes",
    ):
        setattr(recipe, field, recipe_data[field])
    recipe.target_carbonation = recipe_data.get("target_carbonation", Decimal("2.40"))
    for field, default in (
        ("mash_time_min", 0),
        ("mash_time_max", 180),
        ("mash_temperature_min", 45),
        ("mash_temperature_max", 80),
        ("mash_time_grid", 15),
        ("mash_temperature_grid", 5),
    ):
        setattr(recipe, field, recipe_data.get(field, default))
    recipe.mash_zones = recipe_data.get("mash_zones", ["beta", "alpha"])
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
    query = request.GET.get("q", "").strip()
    alerts_only = request.GET.get("alerts") == "1"
    planned_needs = planned_stock_needs()
    catalog_items = list(IngredientCatalog.objects.all())
    stock_alerts = []
    for item in catalog_items:
        planned_need = planned_needs.get(item.pk, {"required": 0, "unit": "", "brews": []})
        item.planned_required = planned_need["required"]
        item.planned_deficit = max(item.planned_required - item.quantity_available, 0)
        item.stock_alert = item.planned_deficit > 0
        item.planned_brews = planned_need["brews"]
        if item.stock_alert:
            stock_alerts.append(item)
    stock_alert_brews = []
    planned_brews = {
        brew.pk: brew
        for need in planned_needs.values()
        for brew in need["brews"]
    }
    for brew in planned_brews.values():
        missing_items = []
        for requirement in brew_stock_requirements(brew):
            catalog = requirement["catalog"]
            if catalog is None or catalog.quantity_available >= requirement["required"]:
                continue
            missing_items.append(
                {
                    "name": requirement["name"],
                    "deficit": requirement["required"] - catalog.quantity_available,
                    "unit": requirement["unit"],
                }
            )
        if missing_items:
            stock_alert_brews.append({"brew": brew, "missing_items": missing_items})
    if query:
        catalog_items = [item for item in catalog_items if query.casefold() in item.name.casefold()]
    if alerts_only:
        catalog_items = [item for item in catalog_items if item.stock_alert]
    return render(
        request,
        "recipes/catalog.html",
        {
            "malt_form": CatalogMaltForm(),
            "hop_form": CatalogHopForm(),
            "yeast_form": CatalogYeastForm(),
            "malts": [item for item in catalog_items if item.kind == IngredientCatalog.Kind.MALT],
            "hops": [item for item in catalog_items if item.kind == IngredientCatalog.Kind.HOP],
            "yeasts": [item for item in catalog_items if item.kind == IngredientCatalog.Kind.YEAST],
            "others": [item for item in catalog_items if item.kind == IngredientCatalog.Kind.OTHER],
            "other_form": CatalogOtherForm(),
            "consumables": [item for item in catalog_items if item.kind == IngredientCatalog.Kind.CONSUMABLE],
            "consumable_form": CatalogConsumableForm(),
            "catalog_query": query,
            "alerts_only": alerts_only,
            "stock_alerts": stock_alerts,
            "stock_alert_brews": stock_alert_brews,
        },
    )


def catalog_create(request):
    form_classes = {
        IngredientCatalog.Kind.MALT: CatalogMaltForm,
        IngredientCatalog.Kind.HOP: CatalogHopForm,
        IngredientCatalog.Kind.YEAST: CatalogYeastForm,
        IngredientCatalog.Kind.OTHER: CatalogOtherForm,
        IngredientCatalog.Kind.CONSUMABLE: CatalogConsumableForm,
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
    previous_name = item.name
    form = CatalogForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            item = form.save()
            updated_ingredients = 0
            if item.name != previous_name:
                updated_ingredients = Ingredient.objects.filter(catalog_id=item.pk).update(name=item.name)
        suffix = (
            f" et propagé à {updated_ingredients} ingrédient(s) de recette"
            if updated_ingredients
            else ""
        )
        messages.success(request, f"{item.name} a été modifié dans le catalogue{suffix}.")
        return redirect("recipes:catalog")
    return render(request, "recipes/catalog_form.html", {"form": form, "item": item})


@require_POST
def catalog_delete(request, pk):
    item = get_object_or_404(IngredientCatalog, pk=pk)
    item_name = item.name
    item.delete()
    messages.success(request, f"{item_name} a été supprimé du catalogue.")
    return redirect("recipes:catalog")


@require_POST
def catalog_add_quantity(request, pk):
    item = get_object_or_404(IngredientCatalog, pk=pk)
    try:
        quantity = int(request.POST.get("quantity", ""))
    except (TypeError, ValueError):
        quantity = 0
    if quantity == 0:
        messages.error(request, "La quantité doit être un nombre entier différent de zéro.")
    else:
        item.quantity_available += quantity
        item.save(update_fields=["quantity_available"])
        action = "ajoutée(s) au stock" if quantity > 0 else "retirée(s) du stock"
        messages.success(request, f"{abs(quantity)} unité(s) {action} de {item.name}.")
    return redirect("recipes:catalog")


def recipe_detail(request, pk, edit_forms=None):
    recipe = get_object_or_404(Recipe, pk=pk)
    if recipe.category_id is None:
        default_category = BeerCategory.objects.filter(code="18A").first()
        if default_category:
            recipe.category = default_category
            recipe.save(update_fields=["category"])
    equipment = EquipmentSettings.objects.first() or EquipmentSettings()
    cost_tracking_enabled = equipment.cost_management_enabled
    ingredient_costs = [
        ingredient.cost_total
        for ingredient in recipe.ingredients.all()
        if ingredient.cost_total is not None
    ]
    ingredient_count = recipe.ingredients.count()
    known_cost_count = len(ingredient_costs)
    estimated_recipe_cost = sum(ingredient_costs, Decimal("0")) if known_cost_count else None
    estimated_cost_per_liter = (
        estimated_recipe_cost / Decimal(recipe.batch_size_l)
        if estimated_recipe_cost is not None and recipe.batch_size_l
        else None
    )
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

        def within_range(value, minimum, maximum, tolerance=0):
            if value is None or minimum is None or maximum is None:
                return False
            minimum = float(minimum)
            maximum = float(maximum)
            tolerance = (maximum - minimum) * tolerance
            return minimum - tolerance <= float(value) <= maximum + tolerance

        tolerance = float(equipment.style_tolerance_percent) / 100
        return all(
            within_range(value, minimum, maximum, tolerance)
            for value, minimum, maximum in values
        )

    categories = list(BeerCategory.objects.all())
    compatible_categories = [category for category in categories if category_matches_profile(category)]
    incompatible_categories = [
        category for category in categories if category not in compatible_categories
    ]
    category_form = RecipeCategoryForm(instance=recipe)
    category_form.fields["category"].choices = [
        ("", "---------"),
        ("Styles compatibles avec la recette", [(category.pk, str(category)) for category in compatible_categories]),
        ("Styles incompatibles", [(category.pk, str(category)) for category in incompatible_categories]),
    ]

    def style_indicator(label, value, minimum, maximum, unit, tick_size, absolute_minimum):
        if value is None or minimum is None or maximum is None:
            return None
        value = float(value)
        minimum = float(minimum)
        maximum = float(maximum)
        tick = Decimal(str(tick_size))
        data_minimum = min(Decimal(str(value)), Decimal(str(minimum)))
        data_maximum = max(Decimal(str(value)), Decimal(str(maximum)))
        span = max(data_maximum - data_minimum, tick)
        margin = max(span * Decimal("0.3"), tick * 2)
        raw_minimum = (data_minimum - margin) / tick
        raw_maximum = (data_maximum + margin) / tick
        scale_minimum = float(
            max(
                Decimal(str(absolute_minimum)),
                raw_minimum.to_integral_value(rounding=ROUND_FLOOR) * tick,
            )
        )
        scale_maximum = float(raw_maximum.to_integral_value(rounding=ROUND_CEILING) * tick)
        scale_span = scale_maximum - scale_minimum

        def scale_position(point):
            return max(0, min(100, (point - scale_minimum) / scale_span * 100))

        value_position = scale_position(value)
        style_start = scale_position(minimum)
        style_end = scale_position(maximum)
        return {
            "label": label,
            "value": value,
            "minimum": minimum,
            "maximum": maximum,
            "scale_minimum": scale_minimum,
            "scale_maximum": scale_maximum,
            "style_start": style_start,
            "style_width": style_end - style_start,
            "unit": unit,
            "position": value_position,
            "ok": minimum <= value <= maximum,
        }

    style_indicators = []
    if recipe.category:
        for indicator in (
            style_indicator("DI", og, recipe.category.og_min, recipe.category.og_max, "", 0.005, 0.9),
            style_indicator("DF", final_gravity, recipe.category.fg_min, recipe.category.fg_max, "", 0.005, 0.9),
            style_indicator("Couleur", ebc, recipe.category.ebc_min, recipe.category.ebc_max, " EBC", 5, 0),
            style_indicator("Amertume", ibu, recipe.category.ibu_min, recipe.category.ibu_max, " IBU", 5, 0),
            style_indicator("Alcool", abv, recipe.category.abv_min, recipe.category.abv_max, " %", 0.5, 0),
        ):
            if indicator:
                style_indicators.append(indicator)
    malt_total = sum(float(malt.amount_g) for malt in malts)
    mash_chart_points = []
    mash_elapsed = 0
    if mash_steps:
        mash_chart_points.append(
            {"x": 0, "y": float(mash_steps[0].temperature_c), "step_id": mash_steps[0].pk, "step_index": 0}
        )
        for index, step in enumerate(mash_steps):
            mash_elapsed += step.duration_min
            mash_chart_points.append(
                {
                    "x": mash_elapsed,
                    "y": float(step.temperature_c),
                    "step_id": step.pk,
                    "step_index": index,
                }
            )
            if index + 1 < len(mash_steps):
                mash_chart_points.append(
                    {
                        "x": mash_elapsed,
                        "y": float(mash_steps[index + 1].temperature_c),
                        "step_id": mash_steps[index + 1].pk,
                        "step_index": index + 1,
                    }
                )
    mash_edit_points = [
        {
            "id": step.pk,
            "name": step.name,
            "temperature": float(step.temperature_c),
            "duration": step.duration_min,
        }
        for step in mash_steps
    ]

    def inline_form(form, form_id):
        for field in form.fields.values():
            field.widget.attrs["form"] = form_id
        return form

    malt_rows = [
        {
            "ingredient": malt,
            "proportion": round(float(malt.amount_g) / malt_total * 100, 1) if malt_total else 0,
            "edit_form": inline_form(
                edit_forms.get(
                    malt.pk,
                    MaltForm(instance=malt, cost_tracking_enabled=cost_tracking_enabled),
                ),
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
                edit_forms.get(
                    hop.pk,
                    HopForm(instance=hop, cost_tracking_enabled=cost_tracking_enabled),
                ),
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
    boil_other_rows = [
        {"ingredient": other}
        for other in others
        if other.addition == "Ébullition"
    ]
    boil_addition_rows = sorted(
        [*boil_hop_rows, *boil_other_rows],
        key=lambda row: (-row["ingredient"].boil_minutes, row["ingredient"].pk),
    )
    cooling_hop_rows = [
        row for row in hop_rows
        if row["ingredient"].addition == "Refroidissement"
    ]
    cooling_hop_rows.sort(
        key=lambda row: (
            -float(row["ingredient"].addition_temperature_c),
            row["ingredient"].pk,
        )
    )
    boil_events = [{"type": "start"}]
    if boil_addition_rows:
        previous_remaining = recipe.boil_time_min
        for remaining, grouped_rows in groupby(
            boil_addition_rows,
            key=lambda row: row["ingredient"].boil_minutes,
        ):
            rows = list(grouped_rows)
            wait_minutes = previous_remaining - remaining
            if wait_minutes > 0:
                boil_events.append({"type": "timer", "minutes": wait_minutes})
            boil_events.append({"type": "addition", "rows": rows})
            previous_remaining = remaining
        if previous_remaining > 0:
            boil_events.append({"type": "timer", "minutes": previous_remaining})
    else:
        boil_events.append({"type": "timer", "minutes": recipe.boil_time_min})
    boil_events.append({"type": "cool"})
    for temperature, grouped_rows in groupby(
        cooling_hop_rows,
        key=lambda row: row["ingredient"].addition_temperature_c,
    ):
        boil_events.append(
            {"type": "cooling_hop", "temperature": temperature, "rows": list(grouped_rows)}
        )
    tasting_form = RecipeTastingForm(instance=recipe)
    inventory_by_kind = []
    for kind, label in IngredientCatalog.Kind.choices:
        if kind == IngredientCatalog.Kind.CONSUMABLE:
            continue
        inventory_by_kind.append(
            {
                "kind": kind,
                "label": label,
                "items": IngredientCatalog.objects.filter(kind=kind).order_by("name"),
            }
        )
    return render(
        request,
        "recipes/detail.html",
        {
            "recipe": recipe,
            "name_form": RecipeNameForm(instance=recipe),
            "tasting_form": tasting_form,
            "tasting_stars": [
                {
                    "number": star_number,
                    "left_value": Decimal(star_number) - Decimal("0.5"),
                    "right_value": Decimal(star_number),
                }
                for star_number in range(1, 6)
            ],
            "tasting_axes": [
                {
                    "name": field_name,
                    "label": label,
                    "value": getattr(recipe, field_name),
                    "field": tasting_form[field_name],
                }
                for field_name, label in (
                    ("tasting_malt", "Malté / douceur"),
                    ("tasting_bitterness", "Amertume perçue"),
                    ("tasting_hops", "Arômes de houblon"),
                    ("tasting_body", "Corps"),
                    ("tasting_alcohol", "Chaleur de l’alcool"),
                    ("tasting_acidity", "Acidité"),
                )
            ],
            "category_form": category_form,
            "efficiency_form": RecipeEfficiencyForm(instance=recipe),
            "notes_form": RecipeNotesForm(instance=recipe),
            "scale_form": ScaleForm(initial={"batch_size_l": recipe.batch_size_l}),
            "malt_form": MaltForm(cost_tracking_enabled=cost_tracking_enabled),
            "hop_form": HopForm(cost_tracking_enabled=cost_tracking_enabled),
            "yeast_form": YeastForm(cost_tracking_enabled=cost_tracking_enabled),
            "other_form": OtherForm(cost_tracking_enabled=cost_tracking_enabled),
            "cost_tracking_enabled": cost_tracking_enabled,
            "estimated_recipe_cost": estimated_recipe_cost,
            "estimated_cost_per_liter": estimated_cost_per_liter,
            "known_cost_count": known_cost_count,
            "ingredient_count": ingredient_count,
            "cost_rows": recipe.ingredients.all(),
            "malt_rows": malt_rows,
            "malt_total_g": malt_total,
            "mash_chart_points": mash_chart_points,
            "mash_edit_points": mash_edit_points,
            "water_equipment": {
                "diameter_cm": float(equipment.diameter_cm),
                "height_cm": float(equipment.height_cm),
                "evaporation_l_h": float(equipment.evaporation_l_h),
                "grain_absorption_l_kg": float(equipment.grain_absorption_l_kg),
                "dead_space_l": float(equipment.dead_space_l),
            },
            "hop_rows": hop_rows,
            "boil_events": boil_events,
            "yeast_rows": [
                {
                    "ingredient": yeast,
                    "edit_form": inline_form(
                        edit_forms.get(
                            yeast.pk,
                            YeastForm(instance=yeast, cost_tracking_enabled=cost_tracking_enabled),
                        ),
                        f"edit-yeast-{yeast.pk}",
                    ),
                }
                for yeast in yeasts
            ],
            "other_rows": [
                {
                    "ingredient": other,
                    "edit_form": inline_form(
                        edit_forms.get(
                            other.pk,
                            OtherForm(instance=other, cost_tracking_enabled=cost_tracking_enabled),
                        ),
                        f"edit-other-{other.pk}",
                    ),
                }
                for other in others
            ],
            "mash_steps": mash_steps,
            "mash_rows": [
                {"step": step, "edit_form": MashStepForm(instance=step)}
                for step in recipe.mash_steps.all()
            ],
            "mash_graph_settings_form": MashGraphSettingsForm(instance=recipe),
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
                    "kind": item.kind,
                    "quantity_available": item.quantity_available,
                    "manufacturer": item.manufacturer,
                    "form": item.form,
                    "color_ebc": str(item.color_ebc),
                    "potential_yield": str(item.potential_yield),
                    "alpha_acid": str(item.alpha_acid),
                    "attenuation": str(item.attenuation),
                }
                for item in IngredientCatalog.objects.all()
            ],
            "inventory_by_kind": inventory_by_kind,
            "estimated_og": og,
            "estimated_plato": plato_from_gravity(og) if og else None,
            "estimated_ibu": ibu,
            "estimated_ebc": ebc,
            "estimated_ebc_color": ebc_color_rgb(ebc) if ebc is not None else None,
            "estimated_abv": abv,
            "estimated_final_gravity": final_gravity,
            "estimated_final_plato": plato_from_gravity(final_gravity) if final_gravity else None,
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
        return redirect("recipes:detail", pk=step.recipe_id)
    return render(request, "recipes/mash_form.html", {"form": form, "step": step})


@require_POST
def mash_profile_update(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    steps = {str(step.pk): step for step in recipe.mash_steps.all()}
    updated = 0
    for step_id, step in steps.items():
        raw_temperature = request.POST.get(f"temperature_{step_id}")
        raw_duration = request.POST.get(f"duration_{step_id}")
        try:
            temperature = Decimal(raw_temperature)
            duration = int(raw_duration)
        except (TypeError, ValueError, ArithmeticError):
            messages.error(request, "Une température de palier est invalide.")
            return redirect("recipes:detail", pk=recipe.pk)
        if not 35 <= temperature <= 100 or duration < 1:
            messages.error(request, "Les températures doivent être comprises entre 35 et 100 °C et les durées doivent être positives.")
            return redirect("recipes:detail", pk=recipe.pk)
        step.temperature_c = temperature
        step.duration_min = duration
        step.save(update_fields=["temperature_c", "duration_min"])
        updated += 1
    if updated:
        messages.success(request, "Les températures des paliers ont été enregistrées.")
    return redirect("recipes:detail", pk=recipe.pk)


@require_POST
def mash_graph_update(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    step_ids = request.POST.getlist("step_id")
    names = request.POST.getlist("step_name")
    temperatures = request.POST.getlist("step_temperature")
    durations = request.POST.getlist("step_duration")
    if not step_ids or not (len(step_ids) == len(names) == len(temperatures) == len(durations)):
        messages.error(request, "Les données des paliers sont incomplètes.")
        return redirect("recipes:detail", pk=recipe.pk)

    existing = {str(step.pk): step for step in recipe.mash_steps.all()}
    parsed = []
    seen_ids = set()
    try:
        for step_id, name, raw_temperature, raw_duration in zip(step_ids, names, temperatures, durations):
            name = name.strip()
            temperature = Decimal(raw_temperature)
            duration = int(raw_duration)
            if step_id.startswith("new-"):
                step_id = ""
            if not name or not 35 <= temperature <= 100 or duration < 1 or (step_id and step_id not in existing):
                raise ValueError
            if step_id and step_id in seen_ids:
                raise ValueError
            seen_ids.add(step_id)
            parsed.append((step_id, name, temperature, duration))
    except (TypeError, ValueError, ArithmeticError):
        messages.error(request, "Chaque palier doit avoir un nom, une température entre 35 et 100 °C et une durée positive.")
        return redirect("recipes:detail", pk=recipe.pk)

    auto_names = all(
        name.removeprefix("Palier").strip().isdigit()
        for _, name, _, _ in parsed
    )
    with transaction.atomic():
        kept_ids = [int(step_id) for step_id in step_ids if step_id in existing]
        recipe.mash_steps.exclude(pk__in=kept_ids).delete()
        for position, (step_id, name, temperature, duration) in enumerate(parsed, start=1):
            step = existing.get(step_id) if step_id else MashStep(recipe=recipe)
            step.name = f"Palier {position}" if auto_names else name
            step.temperature_c = temperature
            step.duration_min = duration
            step.position = position
            step.save()
    messages.success(request, "Les paliers de brassage ont été enregistrés.")
    return redirect("recipes:detail", pk=recipe.pk)


@require_POST
def mash_graph_settings_update(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form = MashGraphSettingsForm(request.POST, instance=recipe)
    if form.is_valid():
        form.save()
        messages.success(request, "Les réglages du graphique ont été enregistrés.")
    else:
        messages.error(request, "Les bornes et les graduations du graphique sont invalides.")
    return redirect("recipes:detail", pk=recipe.pk)


@require_POST
def mash_zones_update(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    allowed_zones = {"protease", "beta", "alpha", "mashout"}
    recipe.mash_zones = [
        zone for zone in request.POST.getlist("zones")
        if zone in allowed_zones
    ]
    recipe.save(update_fields=["mash_zones"])
    messages.success(request, "Les zones brassicoles ont été enregistrées.")
    return redirect("recipes:detail", pk=recipe.pk)


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
        if recipe.category_id is None:
            default_category = BeerCategory.objects.filter(code="18A").first()
            if default_category:
                recipe.category = default_category
                recipe.save(update_fields=["category"])
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


@require_POST
def recipe_tasting_update(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form = RecipeTastingForm(request.POST, instance=recipe)
    if form.is_valid():
        form.save()
        messages.success(request, "Le profil de dégustation a été mis à jour.")
    else:
        messages.error(request, "Le profil de dégustation contient une note invalide.")
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
                update_fields = ["amount_g"]
                if ingredient.cost_total is not None:
                    ingredient.cost_total = (ingredient.cost_total * ratio).quantize(Decimal("0.01"))
                    update_fields.append("cost_total")
                ingredient.save(update_fields=update_fields)
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
            recipe.target_carbonation = data["target_carbonation"]
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
    catalog_id = request.POST.get("catalog") or request.POST.get("name")
    catalog = IngredientCatalog.objects.filter(pk=catalog_id, kind=kind).first()
    if catalog is None:
        messages.error(request, "La fiche de stock sélectionnée n'existe pas ou ne correspond pas au type.")
        return redirect("recipes:detail", pk=recipe.pk)
    cost_tracking_enabled = (
        EquipmentSettings.objects.values_list("cost_management_enabled", flat=True).first()
        or False
    )
    form = form_class(request.POST, cost_tracking_enabled=cost_tracking_enabled)
    if request.method == "POST" and form.is_valid():
        ingredient = form.save(commit=False)
        ingredient.recipe = recipe
        ingredient.kind = kind
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
    cost_tracking_enabled = (
        EquipmentSettings.objects.values_list("cost_management_enabled", flat=True).first()
        or False
    )
    form = form_class(
        request.POST or None,
        instance=ingredient,
        cost_tracking_enabled=cost_tracking_enabled,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{ingredient.name} a été modifié.")
        return redirect("recipes:detail", pk=ingredient.recipe_id)
    return recipe_detail(request, ingredient.recipe_id, {ingredient.pk: form})


@require_POST
def ingredient_cost_update(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    recipe_id = ingredient.recipe_id
    cost_tracking_enabled = (
        EquipmentSettings.objects.values_list("cost_management_enabled", flat=True).first()
        or False
    )
    if not cost_tracking_enabled:
        messages.error(request, "Activez d’abord la gestion des coûts dans les paramètres.")
    else:
        form = IngredientCostForm(request.POST)
        if form.is_valid():
            ingredient.cost_total = form.cleaned_data["cost_total"]
            ingredient.save(update_fields=["cost_total"])
            messages.success(request, f"Le coût de {ingredient.name} a été mis à jour.")
        else:
            messages.error(request, "Le coût doit être un montant positif ou laissé vide.")
    return redirect("recipes:detail", pk=recipe_id)


@require_POST
def ingredient_delete(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    recipe_id = ingredient.recipe_id
    ingredient_name = ingredient.name
    ingredient.delete()
    messages.success(request, f"{ingredient_name} a été supprimé.")
    return redirect("recipes:detail", pk=recipe_id)

from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from xml.etree import ElementTree

from .calculations import average_mash_temperature, estimated_abv, estimated_color_ebc, estimated_final_gravity, estimated_og, ibu_final_gravity_comment, ibu_final_gravity_ratio, plato_from_gravity, tinseth_ibu
from .beerxml import export_recipe, import_recipe
from decimal import Decimal

from .forms import BeerCategoryForm, BeerXMLUploadForm, BoilSettingsForm, CatalogHopForm, CatalogMaltForm, CatalogYeastForm, CatalogForm, EquipmentSettingsForm, FermentationStepForm, HopForm, MaltForm, MashStepForm, RecipeCategoryForm, RecipeEfficiencyForm, RecipeForm, RecipeNameForm, RecipeNotesForm, ScaleForm, YeastForm
from .models import BeerCategory, EquipmentSettings, FermentationStep, Ingredient, IngredientCatalog, MashStep, Recipe, RecipeVersion


def recipe_list(request):
    return render(request, "recipes/list.html", {"recipes": Recipe.objects.all()})


def equipment_settings(request):
    settings = EquipmentSettings.objects.first()
    form = EquipmentSettingsForm(request.POST or None, instance=settings)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Les paramètres de brassage ont été enregistrés.")
        return redirect("recipes:equipment_settings")
    return render(request, "recipes/equipment_settings.html", {"form": form})


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
    return render(
        request,
        "recipes/history.html",
        {"recipe": recipe, "versions": recipe.versions.all()},
    )


@require_POST
def recipe_restore(request, pk, version_pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    version = get_object_or_404(RecipeVersion, pk=version_pk, recipe=recipe)
    data = version.snapshot
    recipe_data = data["recipe"]
    for field in ("name", "batch_size_l", "efficiency", "target_og", "target_ibu", "boil_time_min", "notes"):
        setattr(recipe, field, recipe_data[field])
    recipe.save()
    recipe.ingredients.all().delete()
    recipe.mash_steps.all().delete()
    recipe.fermentation_steps.all().delete()
    for item in data["ingredients"]:
        item = {**item, "catalog_id": item.pop("catalog")}
        Ingredient.objects.create(recipe=recipe, **item)
    for step in data["mash_steps"]:
        MashStep.objects.create(recipe=recipe, **step)
    for step in data.get("fermentation_steps", []):
        FermentationStep.objects.create(recipe=recipe, **step)
    messages.success(request, "La version de la recette a été restaurée.")
    return redirect("recipes:detail", pk=recipe.pk)


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
        },
    )


def catalog_create(request):
    form_classes = {
        IngredientCatalog.Kind.MALT: CatalogMaltForm,
        IngredientCatalog.Kind.HOP: CatalogHopForm,
        IngredientCatalog.Kind.YEAST: CatalogYeastForm,
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
    mash_steps = list(recipe.mash_steps.all())
    og = estimated_og(malts, float(recipe.batch_size_l), float(recipe.efficiency)) if malts else None
    ibu = tinseth_ibu(hops, float(recipe.batch_size_l), og or float(recipe.target_og)) if hops else None
    ebc = estimated_color_ebc(malts, float(recipe.batch_size_l)) if malts else None
    abv = estimated_abv(og or float(recipe.target_og), yeasts, mash_steps)
    final_gravity = estimated_final_gravity(og or float(recipe.target_og), yeasts, mash_steps)
    ibu_df_ratio = ibu_final_gravity_ratio(ibu, final_gravity)
    ibu_df_comment = ibu_final_gravity_comment(ibu_df_ratio, final_gravity)

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
    return render(
        request,
        "recipes/detail.html",
        {
            "recipe": recipe,
            "name_form": RecipeNameForm(instance=recipe),
            "category_form": RecipeCategoryForm(instance=recipe),
            "efficiency_form": RecipeEfficiencyForm(instance=recipe),
            "notes_form": RecipeNotesForm(instance=recipe),
            "scale_form": ScaleForm(initial={"batch_size_l": recipe.batch_size_l}),
            "malt_form": MaltForm(),
            "hop_form": HopForm(),
            "yeast_form": YeastForm(),
            "malt_rows": malt_rows,
            "malt_total_g": malt_total,
            "water_equipment": {
                "diameter_cm": float(equipment.diameter_cm),
                "height_cm": float(equipment.height_cm),
                "evaporation_l_min": float(equipment.evaporation_l_min),
                "grain_absorption_l_kg": float(equipment.grain_absorption_l_kg),
                "dead_space_l": float(equipment.dead_space_l),
            },
            "hop_rows": hop_rows,
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
        form=ingredient.get("form", ""),
        color_ebc=ingredient.get("color_ebc", 0),
        potential_yield=ingredient.get("potential_yield", 80),
        alpha_acid=ingredient.get("alpha_acid", 5),
        attenuation=ingredient.get("attenuation", 78),
    )


def _finish_recipe_import(data, catalog_indexes):
    with transaction.atomic():
        recipe = Recipe.objects.create(
            name=data["name"],
            batch_size_l=data["batch_size_l"],
            efficiency=data["efficiency"],
            target_og=data["target_og"],
            target_ibu=data["target_ibu"],
            boil_time_min=data["boil_time_min"],
        )
        for index, imported_ingredient in enumerate(data["ingredients"]):
            catalog = _catalog_for_imported_ingredient(imported_ingredient)
            if catalog is None and index in catalog_indexes:
                catalog = _create_catalog_from_imported_ingredient(imported_ingredient)
            Ingredient.objects.create(recipe=recipe, catalog=catalog, **imported_ingredient)
    return recipe


def recipe_import(request):
    form = BeerXMLUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and request.POST.get("confirm_catalog") == "1":
        data = request.session.pop("pending_beerxml_import", None)
        if data is None:
            form.add_error(None, "La session d’import a expiré. Veuillez sélectionner à nouveau le fichier BeerXML.")
        else:
            catalog_indexes = {
                int(value)
                for value in request.POST.getlist("add_to_catalog")
                if value.isdigit()
            }
            recipe = _finish_recipe_import(data, catalog_indexes)
            messages.success(request, f"La recette « {recipe.name} » a été importée.")
            return redirect("recipes:detail", pk=recipe.pk)
    elif request.method == "POST" and form.is_valid():
        try:
            data = import_recipe(form.cleaned_data["file"].read())
            missing_catalog = [
                {"index": index, **ingredient}
                for index, ingredient in enumerate(data["ingredients"])
                if _catalog_for_imported_ingredient(ingredient) is None
            ]
            if missing_catalog:
                request.session["pending_beerxml_import"] = data
                return render(
                    request,
                    "recipes/import_confirm.html",
                    {"missing_catalog": missing_catalog, "recipe_name": data["name"]},
                )
            recipe = _finish_recipe_import(data, set())
        except (ValueError, TypeError, ElementTree.ParseError) as error:
            form.add_error("file", f"Import BeerXML impossible : {error}")
        else:
            messages.success(request, f"La recette « {recipe.name} » a été importée.")
            return redirect("recipes:detail", pk=recipe.pk)
    return render(request, "recipes/import.html", {"form": form})


@require_POST
def recipe_delete(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    recipe_name = recipe.name
    recipe.delete()
    messages.success(request, f"La recette « {recipe_name} » a été supprimée.")
    return redirect("recipes:list")


def ingredient_create(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form_classes = {
        Ingredient.Kind.MALT: MaltForm,
        Ingredient.Kind.HOP: HopForm,
        Ingredient.Kind.YEAST: YeastForm,
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

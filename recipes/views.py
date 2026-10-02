from django.contrib import messages
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render

from .calculations import estimated_abv, estimated_color_ebc, estimated_og, tinseth_ibu
from .forms import CatalogForm, HopForm, MaltForm, RecipeForm, YeastForm
from .models import Ingredient, IngredientCatalog, Recipe


def recipe_list(request):
    return render(request, "recipes/list.html", {"recipes": Recipe.objects.all()})


def catalog_list(request):
    return render(
        request,
        "recipes/catalog.html",
        {"catalog_form": CatalogForm(), "catalog_items": IngredientCatalog.objects.all()},
    )


def catalog_create(request):
    form = CatalogForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save()
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


def recipe_detail(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    malts = recipe.ingredients.filter(kind="malt")
    hops = recipe.ingredients.filter(kind="hop")
    yeasts = recipe.ingredients.filter(kind="yeast")
    og = estimated_og(malts, float(recipe.batch_size_l), float(recipe.efficiency)) if malts else None
    ibu = tinseth_ibu(hops, float(recipe.batch_size_l), og or float(recipe.target_og)) if hops else None
    ebc = estimated_color_ebc(malts, float(recipe.batch_size_l)) if malts else None
    abv = estimated_abv(og or float(recipe.target_og), yeasts)
    malt_total = sum(float(malt.amount_g) for malt in malts)
    malt_rows = [
        {
            "ingredient": malt,
            "proportion": round(float(malt.amount_g) / malt_total * 100, 1) if malt_total else 0,
        }
        for malt in malts
    ]
    hop_rows = [
        {
            "ingredient": hop,
            "ibu": tinseth_ibu([hop], float(recipe.batch_size_l), og or float(recipe.target_og)),
        }
        for hop in hops
    ]
    chart_data = {
        "labels": ["OG cible", "OG estimée", "IBU cible", "IBU estimés"],
        "values": [
            float(recipe.target_og),
            og or 0,
            float(recipe.target_ibu),
            ibu or 0,
        ],
    }
    return render(
        request,
        "recipes/detail.html",
        {
            "recipe": recipe,
            "malt_form": MaltForm(),
            "hop_form": HopForm(),
            "yeast_form": YeastForm(),
            "malt_rows": malt_rows,
            "hop_rows": hop_rows,
            "yeast_ingredients": yeasts,
            "estimated_og": og,
            "estimated_ibu": ibu,
            "estimated_ebc": ebc,
            "estimated_abv": abv,
            "chart_data": chart_data,
        },
    )


def recipe_create(request):
    form = RecipeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        recipe = form.save()
        messages.success(request, f"La recette « {recipe.name} » a été créée.")
        return redirect("recipes:list")
    return render(request, "recipes/form.html", {"form": form})


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
            ingredient.name = ingredient.name or ingredient.catalog.name
            ingredient.manufacturer = ingredient.manufacturer or ingredient.catalog.manufacturer
            ingredient.form = ingredient.form or ingredient.catalog.form
            ingredient.color_ebc = ingredient.color_ebc or ingredient.catalog.color_ebc
            ingredient.ppg = ingredient.ppg or ingredient.catalog.ppg
            ingredient.alpha_acid = ingredient.alpha_acid or ingredient.catalog.alpha_acid
            ingredient.attenuation = ingredient.attenuation or ingredient.catalog.attenuation
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
    return render(
        request,
        "recipes/ingredient_form.html",
        {"form": form, "ingredient": ingredient},
    )


@require_POST
def ingredient_delete(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    recipe_id = ingredient.recipe_id
    ingredient_name = ingredient.name
    ingredient.delete()
    messages.success(request, f"{ingredient_name} a été supprimé.")
    return redirect("recipes:detail", pk=recipe_id)

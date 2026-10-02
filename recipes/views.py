from django.contrib import messages
from django.shortcuts import redirect, render

from .calculations import estimated_og, tinseth_ibu
from .forms import IngredientForm, RecipeForm
from .models import Recipe


def recipe_list(request):
    return render(request, "recipes/list.html", {"recipes": Recipe.objects.all()})


def recipe_detail(request, pk):
    recipe = Recipe.objects.get(pk=pk)
    malts = recipe.ingredients.filter(kind="malt")
    hops = recipe.ingredients.filter(kind="hop")
    og = estimated_og(malts, float(recipe.batch_size_l), float(recipe.efficiency)) if malts else None
    ibu = tinseth_ibu(hops, float(recipe.batch_size_l), og or float(recipe.target_og)) if hops else None
    return render(
        request,
        "recipes/detail.html",
        {"recipe": recipe, "ingredient_form": IngredientForm(), "estimated_og": og, "estimated_ibu": ibu},
    )


def recipe_create(request):
    form = RecipeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        recipe = form.save()
        messages.success(request, f"La recette « {recipe.name} » a été créée.")
        return redirect("recipes:list")
    return render(request, "recipes/form.html", {"form": form})


def ingredient_create(request, pk):
    recipe = Recipe.objects.get(pk=pk)
    form = IngredientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ingredient = form.save(commit=False)
        ingredient.recipe = recipe
        ingredient.save()
        messages.success(request, f"{ingredient.name} a été ajouté à la recette.")
    return redirect("recipes:detail", pk=recipe.pk)

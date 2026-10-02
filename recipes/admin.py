from django.contrib import admin

from .models import Ingredient, IngredientCatalog, Recipe


@admin.register(IngredientCatalog)
class IngredientCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "manufacturer", "form")
    list_filter = ("kind",)
    search_fields = ("name", "manufacturer")


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("name", "batch_size_l", "target_og", "target_ibu", "created_at")
    search_fields = ("name",)


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "recipe", "amount_g")
    list_filter = ("kind",)

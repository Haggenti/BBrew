from django.urls import path

from . import views

app_name = "recipes"

urlpatterns = [
    path("", views.recipe_list, name="list"),
    path("catalogue/", views.catalog_list, name="catalog"),
    path("catalogue/ajouter/", views.catalog_create, name="catalog_create"),
    path("catalogue/<int:pk>/modifier/", views.catalog_edit, name="catalog_edit"),
    path("catalogue/<int:pk>/supprimer/", views.catalog_delete, name="catalog_delete"),
    path("recettes/nouvelle/", views.recipe_create, name="create"),
    path("recettes/<int:pk>/", views.recipe_detail, name="detail"),
    path("recettes/<int:pk>/supprimer/", views.recipe_delete, name="delete"),
    path("recettes/<int:pk>/ingredients/ajouter/", views.ingredient_create, name="ingredient_create"),
    path("ingredients/<int:pk>/modifier/", views.ingredient_edit, name="ingredient_edit"),
    path("ingredients/<int:pk>/supprimer/", views.ingredient_delete, name="ingredient_delete"),
]

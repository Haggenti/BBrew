from django.urls import path

from . import views

app_name = "recipes"

urlpatterns = [
    path("", views.recipe_list, name="list"),
    path("recettes/nouvelle/", views.recipe_create, name="create"),
    path("recettes/<int:pk>/", views.recipe_detail, name="detail"),
    path("recettes/<int:pk>/ingredients/ajouter/", views.ingredient_create, name="ingredient_create"),
]

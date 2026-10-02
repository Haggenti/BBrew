from django.urls import path

from . import views

app_name = "recipes"

urlpatterns = [
    path("", views.recipe_list, name="list"),
    path("parametres/", views.equipment_settings, name="equipment_settings"),
    path("catalogue/", views.catalog_list, name="catalog"),
    path("catalogue/ajouter/", views.catalog_create, name="catalog_create"),
    path("catalogue/<int:pk>/modifier/", views.catalog_edit, name="catalog_edit"),
    path("catalogue/<int:pk>/supprimer/", views.catalog_delete, name="catalog_delete"),
    path("recettes/nouvelle/", views.recipe_create, name="create"),
    path("recettes/importer/", views.recipe_import, name="import"),
    path("recettes/<int:pk>/", views.recipe_detail, name="detail"),
    path("recettes/<int:pk>/historique/", views.recipe_history, name="history"),
    path("recettes/<int:pk>/historique/<int:version_pk>/restaurer/", views.recipe_restore, name="restore"),
    path("recettes/<int:pk>/brassage/", views.mash_list, name="mash"),
    path("recettes/<int:pk>/brassage/ajouter/", views.mash_create, name="mash_create"),
    path("recettes/<int:pk>/exporter/", views.recipe_export, name="export"),
    path("recettes/<int:pk>/ebullition/", views.boil_settings_update, name="boil_settings"),
    path("recettes/<int:pk>/nom/", views.recipe_name_update, name="name_update"),
    path("recettes/<int:pk>/notes/", views.recipe_notes_update, name="notes_update"),
    path("recettes/<int:pk>/scale/", views.recipe_scale, name="scale"),
    path("recettes/<int:pk>/supprimer/", views.recipe_delete, name="delete"),
    path("recettes/<int:pk>/ingredients/ajouter/", views.ingredient_create, name="ingredient_create"),
    path("ingredients/<int:pk>/modifier/", views.ingredient_edit, name="ingredient_edit"),
    path("ingredients/<int:pk>/supprimer/", views.ingredient_delete, name="ingredient_delete"),
    path("paliers/<int:pk>/modifier/", views.mash_edit, name="mash_edit"),
    path("paliers/<int:pk>/supprimer/", views.mash_delete, name="mash_delete"),
    path("fermentation/<int:pk>/modifier/", views.fermentation_edit, name="fermentation_edit"),
    path("fermentation/<int:pk>/supprimer/", views.fermentation_delete, name="fermentation_delete"),
    path("recettes/<int:pk>/fermentation/ajouter/", views.fermentation_create, name="fermentation_create"),
]

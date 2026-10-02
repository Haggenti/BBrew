from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from .models import FermentationStep, Ingredient, MashStep, Recipe, RecipeVersion
from .versioning import recipe_snapshot

_deleting_recipe_ids = set()


def save_version(recipe, reason):
    if recipe.pk in _deleting_recipe_ids:
        return
    if not Recipe.objects.filter(pk=recipe.pk).exists():
        return
    RecipeVersion.objects.create(
        recipe=recipe,
        reason=reason,
        snapshot=recipe_snapshot(recipe),
    )


@receiver(post_save, sender=Recipe)
def recipe_saved(sender, instance, created, **kwargs):
    save_version(instance, "Création de la recette" if created else "Modification de la recette")


@receiver(pre_delete, sender=Recipe)
def recipe_deleting(sender, instance, **kwargs):
    _deleting_recipe_ids.add(instance.pk)


@receiver(post_delete, sender=Recipe)
def recipe_deleted(sender, instance, **kwargs):
    _deleting_recipe_ids.discard(instance.pk)


@receiver(post_save, sender=Ingredient)
def ingredient_saved(sender, instance, created, **kwargs):
    save_version(instance.recipe, "Ajout d'un ingrédient" if created else "Modification d'un ingrédient")


@receiver(post_delete, sender=Ingredient)
def ingredient_deleted(sender, instance, **kwargs):
    save_version(instance.recipe, "Suppression d'un ingrédient")


@receiver(post_save, sender=MashStep)
def mash_step_saved(sender, instance, created, **kwargs):
    save_version(instance.recipe, "Ajout d'un palier" if created else "Modification d'un palier")


@receiver(post_delete, sender=MashStep)
def mash_step_deleted(sender, instance, **kwargs):
    save_version(instance.recipe, "Suppression d'un palier")


@receiver(post_save, sender=FermentationStep)
def fermentation_step_saved(sender, instance, created, **kwargs):
    save_version(instance.recipe, "Ajout d'un palier de fermentation" if created else "Modification d'un palier de fermentation")


@receiver(post_delete, sender=FermentationStep)
def fermentation_step_deleted(sender, instance, **kwargs):
    save_version(instance.recipe, "Suppression d'un palier de fermentation")

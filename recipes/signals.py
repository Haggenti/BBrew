from decimal import Decimal
from contextlib import contextmanager

from django.db import connections
from django.db.models import Max
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import Brew, FermentationStep, Ingredient, MashStep, Recipe, RecipeVersion
from .versioning import recipe_snapshot

_deleting_recipe_ids = set()
_versioning_suspended = 0


@contextmanager
def suspend_versioning():
    global _versioning_suspended
    _versioning_suspended += 1
    try:
        yield
    finally:
        _versioning_suspended -= 1


def _reason(action, subject):
    return f"{action} · {subject}"[:120]


def _ingredient_subject(instance):
    amount = f"{Decimal(str(instance.amount_g)):g} g"
    return f"{instance.name} ({amount})"


def _mash_subject(instance):
    temperature = f"{Decimal(str(instance.temperature_c)):g}"
    return f"{instance.name} ({temperature} °C · {instance.duration_min} min)"


def _fermentation_subject(instance):
    temperature = f"{Decimal(str(instance.temperature_c)):g}"
    return f"{instance.get_phase_display()} ({temperature} °C · {instance.duration_days} j)"


def save_version(recipe, reason):
    if _versioning_suspended or recipe.pk in _deleting_recipe_ids:
        return
    if not Recipe.objects.filter(pk=recipe.pk).exists():
        return
    next_number = (RecipeVersion.objects.filter(recipe=recipe).aggregate(max_number=Max("version_number"))["max_number"] or 0) + 1
    version = RecipeVersion.objects.create(
        recipe=recipe,
        version_number=next_number,
        reason=reason,
        snapshot=recipe_snapshot(recipe),
    )
    recipe.current_version = version
    Recipe.objects.filter(pk=recipe.pk).update(current_version=version)
    return version


@receiver(post_save, sender=Recipe)
def recipe_created(sender, instance, created, **kwargs):
    if created:
        save_version(instance, "Version initiale")


@receiver(pre_delete, sender=Recipe)
def recipe_deleting(sender, instance, **kwargs):
    _deleting_recipe_ids.add(instance.pk)


@receiver(post_delete, sender=Recipe)
def recipe_deleted(sender, instance, **kwargs):
    _deleting_recipe_ids.discard(instance.pk)


def _reset_brew_sequence_if_empty(sender, using):
    if sender.objects.using(using).exists():
        return

    connection = connections[using]
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sqlite_sequence WHERE name = %s",
                [sender._meta.db_table],
            )


@receiver(pre_save, sender=Brew)
def reset_brew_number_before_first_brew(sender, instance, using, **kwargs):
    if instance._state.adding:
        _reset_brew_sequence_if_empty(sender, using)


@receiver(post_delete, sender=Brew)
def reset_brew_number_when_empty(sender, instance, using, **kwargs):
    _reset_brew_sequence_if_empty(sender, using)

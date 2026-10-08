from decimal import Decimal
from contextlib import contextmanager

from django.db import connections
from django.db.models import Max
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import (
    ActivityEvent,
    BeerCategory,
    Brew,
    EquipmentSettings,
    FermentationStep,
    Ingredient,
    IngredientCatalog,
    MashStep,
    Recipe,
    RecipeVersion,
    ShoppingItem,
)
from .versioning import recipe_snapshot

_deleting_recipe_ids = set()
_versioning_suspended = 0
AUDITED_MODELS = {
    Recipe: ("recette", lambda item: item.name),
    Brew: ("brassin", lambda item: item.recipe_name),
    RecipeVersion: ("version de recette", lambda item: f"V{item.version_number} · recette #{item.recipe_id}"),
    EquipmentSettings: ("paramètres d’équipement", lambda item: "Configuration de l’équipement"),
    ShoppingItem: ("article de courses", lambda item: item.name),
    BeerCategory: ("catégorie BJCP", lambda item: f"{item.code} — {item.name}"),
    IngredientCatalog: ("fiche de stock", lambda item: item.name),
    Ingredient: ("ingrédient de recette", lambda item: item.name),
    MashStep: ("palier d’empâtage", lambda item: item.name),
    FermentationStep: ("palier de fermentation", lambda item: item.phase),
}
VERSION_SNAPSHOT_MODELS = {Recipe, Ingredient, MashStep, FermentationStep}


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


def log_activity(event_type, description, model_name="", object_id="", using="default"):
    ActivityEvent.objects.using(using).create(
        event_type=event_type,
        description=description[:300],
        model_name=model_name[:80],
        object_id=str(object_id)[:80],
    )


def _audit_fields(instance):
    excluded = {"created_at", "snapshot", "stock_consumed_items"}
    return [
        field
        for field in instance._meta.concrete_fields
        if field.name not in excluded and not field.primary_key and not field.auto_created
    ]


def _capture_audit_state(sender, instance, using, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    if instance._state.adding or instance.pk is None:
        instance._activity_before = None
        return

    fields = _audit_fields(instance)
    instance._activity_before = sender.objects.using(using).filter(pk=instance.pk).values(
        *(field.attname for field in fields)
    ).first()


@receiver(pre_save)
def capture_model_state_for_activity(sender, instance, using, **kwargs):
    _capture_audit_state(sender, instance, using, **kwargs)


def _display_audit_value(instance, field, value, using):
    if value is None:
        return "non renseigné"
    if field.name in {"notes", "tasting_notes", "action", "description"}:
        return "renseigné" if value else "vide"
    if field.get_internal_type() in {"TextField", "JSONField"}:
        return "renseigné" if value else "vide"
    if field.choices:
        return dict(field.flatchoices).get(value, str(value))
    if field.is_relation:
        related = field.related_model.objects.using(using).filter(pk=value).first()
        return str(related) if related is not None else f"#{value}"
    if isinstance(value, bool):
        return "oui" if value else "non"
    if isinstance(value, Decimal):
        return f"{value.normalize():f}"
    return str(value)


def _activity_details(instance, before, using, update_fields=None):
    details = []
    included_fields = set(update_fields) if update_fields is not None else None
    for field in _audit_fields(instance):
        if included_fields is not None and field.name not in included_fields and field.attname not in included_fields:
            continue
        previous = before.get(field.attname) if before is not None else None
        current = getattr(instance, field.attname)
        if before is not None and previous == current:
            continue

        label = str(field.verbose_name).capitalize()
        if before is None:
            value = _display_audit_value(instance, field, current, using)
            details.append(f"{label} : {value}")
        elif (
            field.name in {"notes", "tasting_notes", "action", "description"}
            or field.get_internal_type() in {"TextField", "JSONField"}
        ):
            details.append(f"{label} : contenu modifié (non journalisé)")
        else:
            old_value = _display_audit_value(instance, field, previous, using)
            new_value = _display_audit_value(instance, field, current, using)
            details.append(f"{label} : {old_value} → {new_value}")

    if not details:
        return ""
    if len(details) > 8:
        remaining = len(details) - 8
        details = details[:8] + [f"et {remaining} autre(s) champ(s)"]
    return "\n".join(details)


def _audit_subject(instance):
    model_name, subject_getter = AUDITED_MODELS[type(instance)]
    return model_name, str(subject_getter(instance))[:180]


def _sync_current_recipe_version(instance):
    if _versioning_suspended or type(instance) not in VERSION_SNAPSHOT_MODELS:
        return
    recipe_id = instance.pk if isinstance(instance, Recipe) else instance.recipe_id
    recipe = Recipe.objects.select_related("current_version").filter(pk=recipe_id).first()
    if recipe is None or recipe.current_version is None:
        return
    RecipeVersion.objects.filter(pk=recipe.current_version_id).update(
        snapshot=recipe_snapshot(recipe),
    )


@receiver(post_save)
def log_model_save(sender, instance, created, using, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    model_name, subject = _audit_subject(instance)
    event_type = ActivityEvent.EventType.CREATE if created else ActivityEvent.EventType.UPDATE
    action = "Création" if created else "Modification"
    details = _activity_details(
        instance,
        None if created else getattr(instance, "_activity_before", None),
        using,
        kwargs.get("update_fields"),
    )
    ActivityEvent.objects.using(using).create(
        event_type=event_type,
        description=f"{action} — {model_name} : {subject}"[:300],
        details=details,
        model_name=model_name[:80],
        object_id=str(instance.pk)[:80],
    )
    _sync_current_recipe_version(instance)


@receiver(post_delete)
def log_model_delete(sender, instance, using, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    model_name, subject = _audit_subject(instance)
    ActivityEvent.objects.using(using).create(
        event_type=ActivityEvent.EventType.DELETE,
        description=f"Suppression — {model_name} : {subject}"[:300],
        details=_activity_details(instance, None, using),
        model_name=model_name[:80],
        object_id=str(instance.pk)[:80],
    )
    _sync_current_recipe_version(instance)


@receiver(m2m_changed, sender=ShoppingItem.source_brews.through)
def log_shopping_brew_links(sender, instance, action, reverse, pk_set, using, **kwargs):
    if reverse or action not in {"post_add", "post_remove", "post_clear"}:
        return
    relation_action = {
        "post_add": "Brassins associés",
        "post_remove": "Brassins dissociés",
        "post_clear": "Associations avec les brassins supprimées",
    }[action]
    if action != "post_clear" and not pk_set:
        return
    log_activity(
        ActivityEvent.EventType.UPDATE,
        f"Modification — article de courses « {instance.name} » : {relation_action}",
        "article de courses",
        instance.pk,
        using,
    )


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

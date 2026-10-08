from django.db import migrations, models


def copy_recipe_snapshots(apps, schema_editor):
    Brew = apps.get_model("recipes", "Brew")
    for brew in Brew.objects.select_related("recipe_version").filter(recipe_version__isnull=False):
        if brew.recipe_version.snapshot:
            brew.recipe_snapshot = brew.recipe_version.snapshot
            brew.save(update_fields=["recipe_snapshot"])


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0067_brew_recipe_version_synced_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="brew",
            name="recipe_snapshot",
            field=models.JSONField(blank=True, null=True, verbose_name="snapshot de la recette"),
        ),
        migrations.RunPython(copy_recipe_snapshots, migrations.RunPython.noop),
    ]

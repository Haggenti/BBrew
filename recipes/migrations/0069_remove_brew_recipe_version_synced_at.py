from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0068_brew_recipe_snapshot"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="brew",
            name="recipe_version_synced_at",
        ),
    ]

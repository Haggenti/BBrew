from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0066_alter_brew_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="brew",
            name="recipe_version_synced_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="version de recette synchronisée le",
            ),
        ),
    ]

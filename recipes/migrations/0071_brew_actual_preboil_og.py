from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0070_remove_recipe_recipe_tasting_scores_max_5_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="brew",
            name="actual_preboil_og",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=5,
                null=True,
                verbose_name="DI pré-ébullition mesurée",
            ),
        ),
    ]

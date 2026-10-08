from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0064_merge_conditioning_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="recipeversion",
            name="modified_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]

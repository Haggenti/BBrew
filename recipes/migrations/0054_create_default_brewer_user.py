from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


def create_default_brewer(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    User.objects.using(schema_editor.connection.alias).get_or_create(
        username="brewer",
        defaults={"password": make_password("brewer")},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0053_recipe_mash_zones"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(create_default_brewer, migrations.RunPython.noop),
    ]

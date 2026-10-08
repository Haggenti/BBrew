from django.db import migrations


def merge_conditioning_into_completed(apps, schema_editor):
    Brew = apps.get_model("recipes", "Brew")
    Brew.objects.filter(status="conditioning").update(status="completed")


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0063_purchaseorder"),
    ]

    operations = [
        migrations.RunPython(
            merge_conditioning_into_completed,
            migrations.RunPython.noop,
        ),
    ]

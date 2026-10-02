from django.db import migrations


BJCP_2021_CODES = ['1A', '1B', '1C', '1D', '2A', '2B', '2C', '3A', '3B', '3C', '3D', '4A', '4B', '4C', '5A', '5B', '5C', '5D', '6A', '6B', '6C', '7A', '7B', '8A', '8B', '9A', '9B', '9C', '10A', '10B', '10C', '11A', '11B', '11C', '12A', '12B', '12C', '13A', '13B', '13C', '14A', '14B', '14C', '15A', '15B', '15C', '16A', '16B', '16C', '16D', '17A', '17B', '17C', '17D', '18A', '18B', '19A', '19B', '19C', '20A', '20B', '20C', '21A', '21B', '21C', '22A', '22B', '22C', '22D', '23A', '23B', '23C', '23D', '23E', '23F', '23G', '24A', '24B', '24C', '25A', '25B', '25C', '26A', '26B', '26C', '26D', '28A', '28B', '28C', '28D', '29A', '29B', '29C', '29D', '30A', '30B', '30C', '30D', '31A', '31B', '32A', '32B', '34A', '34B', '34C', 'X1', 'X2', 'X3', 'X4', 'X5']


def keep_only_bjcp_2021(apps, schema_editor):
    BeerCategory = apps.get_model("recipes", "BeerCategory")
    BeerCategory.objects.exclude(code__in=BJCP_2021_CODES).delete()


class Migration(migrations.Migration):

    dependencies = [("recipes", "0016_seed_bjcp_styles")]

    operations = [migrations.RunPython(keep_only_bjcp_2021, migrations.RunPython.noop)]

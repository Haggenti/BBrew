from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0062_alter_equipmentsettings_defaults"),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("supplier", models.CharField(max_length=160, verbose_name="fournisseur / magasin")),
                ("order_date", models.DateField(verbose_name="date de commande")),
                ("is_received", models.BooleanField(default=False, verbose_name="reçue")),
                ("received_date", models.DateField(blank=True, null=True, verbose_name="date de réception")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="montant (€)")),
                ("invoice_pdf", models.FileField(blank=True, null=True, upload_to="invoices/%Y/%m/", validators=[django.core.validators.FileExtensionValidator(["pdf"])], verbose_name="facture PDF")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "commande",
                "verbose_name_plural": "historique des commandes",
                "ordering": ["-order_date", "-id"],
            },
        ),
    ]

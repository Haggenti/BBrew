from django.db import models


class Recipe(models.Model):
    name = models.CharField("nom", max_length=120)
    batch_size_l = models.DecimalField("volume final (L)", max_digits=6, decimal_places=2, default=20)
    efficiency = models.DecimalField("rendement (%)", max_digits=5, decimal_places=2, default=75)
    target_og = models.DecimalField("densité initiale cible", max_digits=5, decimal_places=3, default=1.050)
    target_ibu = models.DecimalField("IBU cible", max_digits=6, decimal_places=1, default=25)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def estimated_abv(self):
        return round((float(self.target_og) - 1) * 131.25, 1)


class Ingredient(models.Model):
    class Kind(models.TextChoices):
        MALT = "malt", "Malt"
        HOP = "hop", "Houblon"
        YEAST = "yeast", "Levure"

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredients")
    name = models.CharField("nom", max_length=120)
    kind = models.CharField("type", max_length=10, choices=Kind.choices)
    amount_g = models.DecimalField("quantité (g)", max_digits=8, decimal_places=1)
    ppg = models.DecimalField("potentiel (PPG)", max_digits=5, decimal_places=1, default=37)
    alpha_acid = models.DecimalField("acides alpha (%)", max_digits=5, decimal_places=2, default=5)
    boil_minutes = models.PositiveIntegerField("ébullition (min)", default=60)
    attenuation = models.DecimalField("atténuation (%)", max_digits=5, decimal_places=2, default=78)

    class Meta:
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

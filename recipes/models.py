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


class IngredientCatalog(models.Model):
    class Kind(models.TextChoices):
        MALT = "malt", "Malt"
        HOP = "hop", "Houblon"
        YEAST = "yeast", "Levure"

    name = models.CharField("nom", max_length=120)
    kind = models.CharField("type", max_length=10, choices=Kind.choices)
    manufacturer = models.CharField("fabricant / laboratoire", max_length=120, blank=True)
    form = models.CharField("forme", max_length=60, blank=True)
    color_ebc = models.DecimalField("couleur (EBC)", max_digits=7, decimal_places=1, default=0)
    ppg = models.DecimalField("potentiel (PPG)", max_digits=5, decimal_places=1, default=37)
    alpha_acid = models.DecimalField("acides alpha (%)", max_digits=5, decimal_places=2, default=5)
    attenuation = models.DecimalField("atténuation (%)", max_digits=5, decimal_places=2, default=78)

    class Meta:
        ordering = ["kind", "name"]
        verbose_name = "ingrédient du catalogue"
        verbose_name_plural = "ingrédients du catalogue"

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class Ingredient(models.Model):
    class Kind(models.TextChoices):
        MALT = "malt", "Malt"
        HOP = "hop", "Houblon"
        YEAST = "yeast", "Levure"

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredients")
    catalog = models.ForeignKey(
        IngredientCatalog,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="recipe_ingredients",
    )
    name = models.CharField("nom", max_length=120)
    kind = models.CharField("type", max_length=10, choices=Kind.choices)
    amount_g = models.DecimalField("quantité (g)", max_digits=8, decimal_places=1)
    manufacturer = models.CharField("fabricant / laboratoire", max_length=120, blank=True)
    form = models.CharField("forme", max_length=60, blank=True)
    addition = models.CharField("ajout", max_length=100, blank=True)
    color_ebc = models.DecimalField("couleur (EBC)", max_digits=7, decimal_places=1, default=0)
    cost_total = models.DecimalField("coût total", max_digits=8, decimal_places=2, default=0)
    ppg = models.DecimalField("potentiel (PPG)", max_digits=5, decimal_places=1, default=37)
    alpha_acid = models.DecimalField("acides alpha (%)", max_digits=5, decimal_places=2, default=5)
    boil_minutes = models.PositiveIntegerField("ébullition (min)", default=60)
    attenuation = models.DecimalField("atténuation (%)", max_digits=5, decimal_places=2, default=78)

    class Meta:
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

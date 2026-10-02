from django.db import models


class Recipe(models.Model):
    name = models.CharField("nom", max_length=120)
    category = models.ForeignKey(
        "BeerCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recipes",
        verbose_name="catégorie BJCP",
    )
    batch_size_l = models.DecimalField("volume final (L)", max_digits=6, decimal_places=2, default=20)
    efficiency = models.DecimalField("rendement (%)", max_digits=5, decimal_places=2, default=75)
    target_og = models.DecimalField("densité initiale cible", max_digits=5, decimal_places=3, default=1.050)
    target_ibu = models.DecimalField("IBU cible", max_digits=6, decimal_places=1, default=25)
    boil_time_min = models.PositiveIntegerField("durée d'ébullition (min)", default=60)
    notes = models.TextField("notes", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def estimated_abv(self):
        return round((float(self.target_og) - 1) * 131.25, 1)


class RecipeVersion(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="versions")
    created_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField("modification", max_length=120, default="Modification")
    snapshot = models.JSONField()

    class Meta:
        ordering = ["-created_at", "-id"]


class EquipmentSettings(models.Model):
    diameter_cm = models.DecimalField("diamètre de la cuve (cm)", max_digits=6, decimal_places=1, default=40)
    height_cm = models.DecimalField("hauteur de la cuve (cm)", max_digits=6, decimal_places=1, default=45)
    evaporation_l_min = models.DecimalField("évaporation (L/min)", max_digits=5, decimal_places=2, default=0.25)
    grain_absorption_l_kg = models.DecimalField("absorption des grains (L/kg)", max_digits=5, decimal_places=2, default=0.8)
    dead_space_l = models.DecimalField("volume mort (L)", max_digits=5, decimal_places=2, default=0)
    mash_efficiency = models.DecimalField("rendement d'empâtage (%)", max_digits=5, decimal_places=1, default=75)

    def __str__(self):
        return "Paramètres de brassage"


class BeerCategory(models.Model):
    code = models.CharField("code BJCP", max_length=10, unique=True)
    name = models.CharField("nom", max_length=120)
    description = models.TextField("description", blank=True)
    og_min = models.DecimalField("OG minimale", max_digits=5, decimal_places=3, null=True, blank=True)
    og_max = models.DecimalField("OG maximale", max_digits=5, decimal_places=3, null=True, blank=True)
    fg_min = models.DecimalField("FG minimale", max_digits=5, decimal_places=3, null=True, blank=True)
    fg_max = models.DecimalField("FG maximale", max_digits=5, decimal_places=3, null=True, blank=True)
    ibu_min = models.DecimalField("IBU minimum", max_digits=6, decimal_places=1, null=True, blank=True)
    ibu_max = models.DecimalField("IBU maximum", max_digits=6, decimal_places=1, null=True, blank=True)
    ebc_min = models.DecimalField("EBC minimum", max_digits=7, decimal_places=1, null=True, blank=True)
    ebc_max = models.DecimalField("EBC maximum", max_digits=7, decimal_places=1, null=True, blank=True)
    abv_min = models.DecimalField("ABV minimum (%)", max_digits=5, decimal_places=2, null=True, blank=True)
    abv_max = models.DecimalField("ABV maximum (%)", max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "catégorie de bière"
        verbose_name_plural = "catégories de bière"

    def __str__(self):
        return f"{self.code} — {self.name}"


class IngredientCatalog(models.Model):
    class Kind(models.TextChoices):
        MALT = "malt", "Malt"
        HOP = "hop", "Houblon"
        YEAST = "yeast", "Levure"

    name = models.CharField("nom", max_length=120)
    kind = models.CharField("type", max_length=10, choices=Kind.choices)
    quantity_available = models.PositiveIntegerField("quantité disponible", default=0)
    manufacturer = models.CharField("fabricant / laboratoire", max_length=120, blank=True)
    form = models.CharField("forme", max_length=60, blank=True)
    color_ebc = models.DecimalField("couleur (EBC)", max_digits=7, decimal_places=1, default=0)
    potential_yield = models.DecimalField("rendement potentiel (%)", max_digits=5, decimal_places=1, default=80)
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
    potential_yield = models.DecimalField("rendement potentiel (%)", max_digits=5, decimal_places=1, default=80)
    alpha_acid = models.DecimalField("acides alpha (%)", max_digits=5, decimal_places=2, default=5)
    boil_minutes = models.PositiveIntegerField("ébullition (min)", default=60)
    attenuation = models.DecimalField("atténuation (%)", max_digits=5, decimal_places=2, default=78)

    class Meta:
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class MashStep(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="mash_steps")
    position = models.PositiveIntegerField("ordre", default=1)
    name = models.CharField("nom du palier", max_length=120)
    temperature_c = models.DecimalField("température (°C)", max_digits=5, decimal_places=1)
    duration_min = models.PositiveIntegerField("durée (min)")

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.name} — {self.temperature_c} °C / {self.duration_min} min"


class FermentationStep(models.Model):
    class Phase(models.TextChoices):
        PRIMARY = "Fermentation primaire", "Fermentation primaire"
        SECONDARY = "Fermentation secondaire", "Fermentation secondaire"
        DRY_HOP = "Dry hop", "Dry hop"
        COLD_CRASH = "Cold crash", "Cold crash"
        CONDITIONING = "Conditionnement", "Conditionnement"
        OTHER = "Autre", "Autre"

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="fermentation_steps")
    position = models.PositiveIntegerField("ordre", default=1)
    phase = models.CharField("phase", max_length=60, choices=Phase.choices)
    temperature_c = models.DecimalField("température (°C)", max_digits=5, decimal_places=1)
    duration_days = models.PositiveIntegerField("durée (jours)")
    action = models.CharField("action / commentaire", max_length=200, blank=True)

    class Meta:
        ordering = ["position", "id"]

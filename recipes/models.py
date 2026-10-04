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
    current_version = models.ForeignKey(
        "RecipeVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="version active",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(batch_size_l__gt=0), name="recipe_batch_size_positive"),
            models.CheckConstraint(
                condition=models.Q(efficiency__gte=1) & models.Q(efficiency__lte=100),
                name="recipe_efficiency_between_1_100",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def estimated_abv(self):
        return round((float(self.target_og) - 1) * 131.25, 1)

    @property
    def current_version_number(self):
        return self.current_version.version_number if self.current_version else None


class Brew(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planifié"
        BREWING = "brewing", "Brassage en cours"
        FERMENTING = "fermenting", "Fermentation"
        CONDITIONING = "conditioning", "Garde / conditionnement"
        COMPLETED = "completed", "Terminé"
        CANCELLED = "cancelled", "Annulé"

    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="brews",
    )
    recipe_version = models.ForeignKey(
        "RecipeVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="brews",
    )
    recipe_name = models.CharField("nom de la recette", max_length=120)
    recipe_version_label = models.CharField("version de recette", max_length=200, blank=True)
    stock_consumed_at = models.DateTimeField("stock consommé le", null=True, blank=True)
    stock_consumed_items = models.JSONField("lignes de stock consommées", default=list, blank=True)
    planned_batch_size_l = models.DecimalField("volume prévu (L)", max_digits=6, decimal_places=2, null=True, blank=True)
    planned_og = models.DecimalField("DI prévue", max_digits=5, decimal_places=3, null=True, blank=True)
    planned_fg = models.DecimalField("DF prévue", max_digits=5, decimal_places=3, null=True, blank=True)
    planned_abv = models.DecimalField("ABV prévu (%)", max_digits=5, decimal_places=2, null=True, blank=True)
    planned_efficiency = models.DecimalField("rendement prévu (%)", max_digits=5, decimal_places=1, null=True, blank=True)
    status = models.CharField("statut", max_length=20, choices=Status.choices, default=Status.PLANNED)
    planned_date = models.DateField("date du brassage", null=True, blank=True)
    completed_date = models.DateField("date de mise en bouteille", null=True, blank=True)
    bottled_bottle_count = models.PositiveIntegerField("nombre de bouteilles à capsuler", null=True, blank=True)
    capsule_catalog = models.ForeignKey(
        "IngredientCatalog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bottling_brews",
        verbose_name="type de capsules",
    )
    capsules_consumed = models.PositiveIntegerField("capsules consommées", default=0)
    capsules_consumed_at = models.DateTimeField("capsules consommées le", null=True, blank=True)
    actual_preboil_volume_l = models.DecimalField(
        "volume pré-ébullition réel (L)", max_digits=6, decimal_places=2, null=True, blank=True
    )
    actual_batch_size_l = models.DecimalField(
        "volume réel (L)", max_digits=6, decimal_places=2, null=True, blank=True
    )
    actual_spent_grains_weight_kg = models.DecimalField(
        "poids des drêches avec sac (kg)", max_digits=6, decimal_places=3, null=True, blank=True
    )
    actual_og = models.DecimalField("DI mesurée", max_digits=5, decimal_places=3, null=True, blank=True)
    actual_fg = models.DecimalField("DF mesurée", max_digits=5, decimal_places=3, null=True, blank=True)
    fermentation_temperature_c = models.DecimalField(
        "température de fermentation (°C)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    notes = models.TextField("notes", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-planned_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(planned_date__isnull=True)
                    | models.Q(completed_date__isnull=True)
                    | models.Q(completed_date__gte=models.F("planned_date"))
                ),
                name="brew_bottling_after_brew",
            ),
            models.CheckConstraint(
                condition=models.Q(actual_preboil_volume_l__isnull=True) | models.Q(actual_preboil_volume_l__gte=0),
                name="brew_preboil_volume_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(actual_batch_size_l__isnull=True) | models.Q(actual_batch_size_l__gte=0),
                name="brew_batch_volume_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.recipe_name} · {self.get_status_display()}"

    @property
    def actual_abv(self):
        if self.actual_og is None or self.actual_fg is None:
            return None
        return round((float(self.actual_og) - float(self.actual_fg)) * 131.25, 2)


class RecipeVersion(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField("numéro de version", default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField("modification", max_length=120, default="Modification")
    snapshot = models.JSONField()

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["recipe", "version_number"], name="unique_recipe_version_number"),
        ]

    def __str__(self):
        return f"{self.recipe.name} · V{self.version_number}"


class EquipmentSettings(models.Model):
    diameter_cm = models.DecimalField("diamètre de la cuve (cm)", max_digits=6, decimal_places=1, default=40)
    height_cm = models.DecimalField("hauteur de la cuve (cm)", max_digits=6, decimal_places=1, default=45)
    bag_weight_g = models.DecimalField("poids du sac (g)", max_digits=7, decimal_places=1, default=0)
    evaporation_l_h = models.DecimalField("évaporation (L/h)", max_digits=5, decimal_places=2, default=15)
    grain_absorption_l_kg = models.DecimalField("absorption des grains (L/kg)", max_digits=5, decimal_places=2, default=0.8)
    dead_space_l = models.DecimalField("volume mort (L)", max_digits=5, decimal_places=2, default=0)
    mash_efficiency = models.DecimalField("rendement de brassage (%)", max_digits=5, decimal_places=1, default=75)
    style_tolerance_percent = models.DecimalField("tolérance des styles (%)", max_digits=5, decimal_places=1, default=10)

    def __str__(self):
        return "Paramètres de brassage"


class ShoppingItem(models.Model):
    name = models.CharField("article", max_length=160)
    is_ordered = models.BooleanField("commandé", default=False)
    source_brews = models.ManyToManyField(
        "Brew",
        verbose_name="brassins à l'origine",
        blank=True,
        related_name="shopping_items",
    )
    catalog = models.ForeignKey(
        "IngredientCatalog",
        verbose_name="fiche de stock",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shopping_items",
    )
    planned_quantity = models.PositiveIntegerField("quantité prévue", null=True, blank=True)
    unit = models.CharField("unité", max_length=30, blank=True)
    received_quantity = models.PositiveIntegerField("quantité reçue", null=True, blank=True)
    is_received = models.BooleanField("réceptionné", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_ordered", "-created_at", "-id"]
        verbose_name = "article de la liste de courses"
        verbose_name_plural = "articles de la liste de courses"

    def __str__(self):
        return self.name


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
        OTHER = "other", "Divers"
        CONSUMABLE = "consumable", "Consommable"

    name = models.CharField("nom", max_length=120)
    kind = models.CharField("type", max_length=10, choices=Kind.choices)
    quantity_available = models.IntegerField("quantité disponible", default=0)
    manufacturer = models.CharField("fournisseur", max_length=120, blank=True)
    product_id = models.CharField("référence produit", max_length=120, blank=True)
    form = models.CharField("forme", max_length=60, blank=True)
    color_ebc = models.DecimalField("couleur (EBC)", max_digits=7, decimal_places=1, default=0)
    potential_yield = models.DecimalField("rendement potentiel (%)", max_digits=5, decimal_places=1, default=80)
    alpha_acid = models.DecimalField("acides alpha (%)", max_digits=5, decimal_places=2, default=5)
    attenuation = models.DecimalField("atténuation (%)", max_digits=5, decimal_places=2, default=78)

    class Meta:
        ordering = ["kind", "name"]
        verbose_name = "ingrédient du catalogue"
        verbose_name_plural = "ingrédients du catalogue"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity_available__gte=0),
                name="catalog_quantity_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class Ingredient(models.Model):
    class Kind(models.TextChoices):
        MALT = "malt", "Malt"
        HOP = "hop", "Houblon"
        YEAST = "yeast", "Levure"
        OTHER = "other", "Divers"

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
    manufacturer = models.CharField("fournisseur", max_length=120, blank=True)
    product_id = models.CharField("référence produit", max_length=120, blank=True)
    form = models.CharField("forme", max_length=60, blank=True)
    addition = models.CharField("ajout", max_length=100, blank=True)
    notes = models.CharField("notes", max_length=300, blank=True)
    color_ebc = models.DecimalField("couleur (EBC)", max_digits=7, decimal_places=1, default=0)
    cost_total = models.DecimalField("coût total", max_digits=8, decimal_places=2, default=0)
    potential_yield = models.DecimalField("rendement potentiel (%)", max_digits=5, decimal_places=1, default=80)
    alpha_acid = models.DecimalField("acides alpha (%)", max_digits=5, decimal_places=2, default=5)
    boil_minutes = models.PositiveIntegerField("ébullition (min)", default=60)
    addition_temperature_c = models.DecimalField(
        "température d'ajout (°C)",
        max_digits=5,
        decimal_places=1,
        blank=True,
        null=True,
    )
    for_bottling = models.BooleanField("ajoutée à l'embouteillage", default=False)
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
        constraints = [
            models.CheckConstraint(
                condition=models.Q(temperature_c__gte=35) & models.Q(temperature_c__lte=100),
                name="mash_temperature_between_35_100",
            ),
            models.CheckConstraint(condition=models.Q(duration_min__gt=0), name="mash_duration_positive"),
        ]

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

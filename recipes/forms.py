from decimal import Decimal
import math

from django import forms

from .models import BeerCategory, Brew, EquipmentSettings, FermentationStep, Ingredient, IngredientCatalog, MashStep, Recipe, RecipeVersion, ShoppingItem

MALT_FORMS = [
    ("Grains", "Grains"),
    ("Flocons", "Flocons"),
    ("Farine", "Farine"),
    ("Extrait sec", "Extrait sec"),
    ("Extrait liquide", "Extrait liquide"),
    ("Sucre solide", "Sucre solide"),
    ("Sirop", "Sirop"),
]
HOP_FORMS = [
    ("Pellets", "Pellets"),
    ("Cônes", "Cônes"),
    ("Fleurs", "Fleurs"),
    ("Cryo", "Cryo"),
]
YEAST_FORMS = [
    ("Sèche", "Sèche"),
    ("Liquide", "Liquide"),
    ("Pâte", "Pâte"),
]
OTHER_FORMS = [
    ("Épice", "Épice"),
    ("Additif", "Additif"),
    ("Fruit", "Fruit"),
    ("Agent de clarification", "Agent de clarification"),
    ("Autre", "Autre"),
]
CONSUMABLE_FORMS = [
    ("Capsules", "Capsules"),
    ("Autre", "Autre"),
]
FORM_CHOICES_BY_KIND = {
    "malt": MALT_FORMS,
    "hop": HOP_FORMS,
    "yeast": YEAST_FORMS,
    "other": OTHER_FORMS,
}
ADDITION_CHOICES = [
    ("Ébullition", "Ébullition"),
    ("Refroidissement", "Refroidissement"),
    ("Dry hop", "Dry hop"),
]
MALT_ADDITION_CHOICES = [
    ("Brassage", "Brassage"),
    ("Ébullition", "Ébullition"),
]


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.equipment_settings = kwargs.pop("equipment_settings", None)
        super().__init__(*args, **kwargs)
        for optional_field in ("manufacturer", "form", "addition", "color_ebc", "cost_total", "quantity_available"):
            if optional_field in self.fields:
                self.fields[optional_field].required = False
        if "catalog" in self.fields:
            self.fields["catalog"].label = "Stock"
        if "potential_yield" in self.fields:
            self.fields["potential_yield"].label = "Rendement"
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                css_class = "form-check-input"
            else:
                css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css_class

    def clean_cost_total(self):
        value = self.cleaned_data.get("cost_total")
        if value is not None and value < 0:
            raise forms.ValidationError("Le coût ne peut pas être négatif.")
        return value

    def clean_quantity_available(self):
        quantity = self.cleaned_data.get("quantity_available")
        if quantity is not None and quantity < 0:
            raise forms.ValidationError("La quantité disponible ne peut pas être négative.")
        return quantity or 0


class RecipeForm(StyledModelForm):
    class Meta:
        model = Recipe
        fields = ["name", "category", "batch_size_l", "efficiency", "target_og", "target_ibu", "target_carbonation", "boil_time_min", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex. Pale Ale du dimanche"}),
            "batch_size_l": forms.NumberInput(attrs={"step": "0.1", "min": "1"}),
            "efficiency": forms.NumberInput(attrs={"step": "1", "min": "1", "max": "100"}),
            "target_og": forms.NumberInput(attrs={"step": "0.001", "min": "1"}),
            "target_ibu": forms.NumberInput(attrs={"step": "1", "min": "0"}),
            "target_carbonation": forms.NumberInput(attrs={"step": "0.1", "min": "0", "max": "6"}),
            "boil_time_min": forms.NumberInput(attrs={"min": "1", "max": "240", "step": "1"}),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Notes générales sur cette recette"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["boil_time_min"].required = False
        self.fields["target_carbonation"].required = False
        self.fields["efficiency"].label = "Efficacité (%)"

    def clean_boil_time_min(self):
        return self.cleaned_data.get("boil_time_min") or 60

    def clean_target_carbonation(self):
        return self.cleaned_data.get("target_carbonation") or Decimal("2.40")


class EquipmentSettingsForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["style_tolerance_percent"].required = False
        self.fields["cost_management_enabled"].help_text = (
            "Les coûts inconnus restent vides et ne sont pas inclus dans l’estimation."
        )

    def clean_style_tolerance_percent(self):
        value = self.cleaned_data.get("style_tolerance_percent")
        if value is None:
            return 10
        if value < 0 or value > 100:
            raise forms.ValidationError("La tolérance doit être comprise entre 0 et 100 %.")
        return value

    class Meta:
        model = EquipmentSettings
        fields = [
            "diameter_cm",
            "height_cm",
            "bag_weight_g",
            "evaporation_l_h",
            "grain_absorption_l_kg",
            "dead_space_l",
            "mash_efficiency",
            "style_tolerance_percent",
            "cost_management_enabled",
        ]
        widgets = {
            "diameter_cm": forms.NumberInput(attrs={"min": "1", "step": "0.1"}),
            "height_cm": forms.NumberInput(attrs={"min": "1", "step": "0.1"}),
            "bag_weight_g": forms.NumberInput(attrs={"min": "0", "step": "1"}),
            "evaporation_l_h": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "grain_absorption_l_kg": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "dead_space_l": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "mash_efficiency": forms.NumberInput(attrs={"min": "1", "max": "100", "step": "0.1"}),
            "style_tolerance_percent": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "0.1"}),
            "cost_management_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "evaporation_l_h": "évaporation (L/h)",
            "style_tolerance_percent": "tolérance de compatibilité des styles (%)",
        }


class ShoppingItemForm(StyledModelForm):
    class Meta:
        model = ShoppingItem
        fields = ["name", "planned_quantity", "unit"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex. capsules rouges"}),
            "planned_quantity": forms.NumberInput(attrs={"min": "1", "step": "1", "placeholder": "Quantité"}),
            "unit": forms.TextInput(attrs={"placeholder": "g, paquets, unités"}),
        }


class BackupUploadForm(forms.Form):
    file = forms.FileField(
        label="Fichier de sauvegarde JSON",
        widget=forms.ClearableFileInput(
            attrs={"accept": ".json,application/json", "class": "form-control"}
        ),
    )


class RecipeVersionChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, version):
        return f"V{version.version_number} — {version.created_at:%d/%m/%Y à %H:%M} — {version.reason}"


class RecipeVersionSelect(forms.Select):
    def __init__(self, *args, **kwargs):
        self.version_recipe_ids = {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        version_id = str(getattr(value, "value", value))
        recipe_id = self.version_recipe_ids.get(version_id)
        if recipe_id:
            option["attrs"]["data-recipe-id"] = str(recipe_id)
        return option


class BrewForm(StyledModelForm):
    VOLUME_INPUT_MODES = (
        ("liters", "Litrage direct"),
        ("headspace", "Mesure jusqu’au haut de la cuve"),
    )
    recipe_version = RecipeVersionChoiceField(
        label="Version de la recette",
        queryset=RecipeVersion.objects.select_related("recipe").all(),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recipe"].label = "Recette"
        self.fields["preboil_volume_mode"] = forms.ChoiceField(
            label="Mode de saisie du volume pré-ébullition",
            choices=self.VOLUME_INPUT_MODES,
            required=False,
            initial="liters",
        )
        self.fields["preboil_headspace_cm"] = forms.DecimalField(
            label="Distance jusqu’au haut de la cuve (cm)",
            required=False,
            min_value=0,
            decimal_places=1,
            max_digits=6,
        )
        self.fields["batch_volume_mode"] = forms.ChoiceField(
            label="Mode de saisie du volume final",
            choices=self.VOLUME_INPUT_MODES,
            required=False,
            initial="liters",
        )
        self.fields["batch_headspace_cm"] = forms.DecimalField(
            label="Distance jusqu’au haut de la cuve (cm)",
            required=False,
            min_value=0,
            decimal_places=1,
            max_digits=6,
        )
        self.fields["recipe_version"].widget = RecipeVersionSelect()
        self.fields["recipe_version"].widget.choices = self.fields["recipe_version"].choices
        self.fields["recipe_version"].widget.version_recipe_ids = {
            str(version.pk): version.recipe_id
            for version in RecipeVersion.objects.all()
        }
        self.fields["capsule_catalog"].queryset = IngredientCatalog.objects.filter(
            kind=IngredientCatalog.Kind.CONSUMABLE
        )

    def clean(self):
        cleaned_data = super().clean()
        brew_date = cleaned_data.get("planned_date")
        bottling_date = cleaned_data.get("completed_date")
        if brew_date and bottling_date and bottling_date < brew_date:
            self.add_error(
                "completed_date",
                "La date de mise en bouteille ne peut pas être antérieure à la date du brassage.",
            )
        equipment = self.equipment_settings or EquipmentSettings.objects.first()
        if equipment is None:
            return cleaned_data
        diameter = Decimal(equipment.diameter_cm)
        height = Decimal(equipment.height_cm)
        cylinder_area = Decimal(str(math.pi)) * (diameter / 2) ** 2
        for mode_name, gap_name, volume_name in (
            ("preboil_volume_mode", "preboil_headspace_cm", "actual_preboil_volume_l"),
            ("batch_volume_mode", "batch_headspace_cm", "actual_batch_size_l"),
        ):
            if cleaned_data.get(mode_name) != "headspace":
                continue
            gap = cleaned_data.get(gap_name)
            if gap is None:
                self.add_error(gap_name, "Indiquez la distance jusqu’au haut de la cuve.")
                continue
            if gap > height:
                self.add_error(gap_name, "La distance ne peut pas dépasser la hauteur de la cuve.")
                continue
            cleaned_data[volume_name] = (cylinder_area * (height - gap) / 1000).quantize(Decimal("0.01"))
        return cleaned_data

    class Meta:
        model = Brew
        fields = [
            "recipe", "recipe_version", "status", "planned_date", "completed_date",
            "bottled_bottle_count", "capsule_catalog",
            "actual_preboil_volume_l", "actual_batch_size_l", "actual_og",
            "actual_spent_grains_weight_kg",
            "actual_fg", "notes",
        ]
        widgets = {
            "planned_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "completed_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "actual_batch_size_l": forms.NumberInput(attrs={"min": "0", "step": "0.1"}),
            "actual_preboil_volume_l": forms.NumberInput(attrs={"min": "0", "step": "0.1"}),
            "actual_spent_grains_weight_kg": forms.NumberInput(attrs={"min": "0", "step": "0.001"}),
            "bottled_bottle_count": forms.NumberInput(attrs={"min": "1", "step": "1"}),
            "actual_og": forms.NumberInput(attrs={"min": "0.9", "step": "0.001"}),
            "actual_fg": forms.NumberInput(attrs={"min": "0.9", "step": "0.001"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def save(self, commit=True):
        brew = super().save(commit=False)
        if brew.recipe:
            brew.recipe_name = brew.recipe.name
            if not brew.recipe_version:
                brew.recipe_version = brew.recipe.versions.first()
            if brew.recipe_version:
                from .calculations import estimate_snapshot

                estimates = estimate_snapshot(brew.recipe_version.snapshot)
                brew.recipe_version_label = (
                    f"V{brew.recipe_version.version_number} · {brew.recipe_version.created_at:%d/%m/%Y %H:%M} · "
                    f"{brew.recipe_version.reason}"
                )
                brew.planned_batch_size_l = estimates["volume_l"]
                brew.planned_og = estimates["og"]
                brew.planned_fg = estimates["fg"]
                brew.planned_abv = estimates["abv"]
                brew.planned_efficiency = estimates["efficiency"]
        if commit:
            brew.save()
        return brew

    def clean_recipe_version(self):
        version = self.cleaned_data.get("recipe_version")
        recipe = self.cleaned_data.get("recipe")
        if version and (not recipe or version.recipe_id != recipe.pk):
            raise forms.ValidationError("Cette version n’appartient pas à la recette sélectionnée.")
        return version


class BeerCategoryForm(StyledModelForm):
    class Meta:
        model = BeerCategory
        fields = [
            "code", "name", "description",
            "og_min", "og_max", "fg_min", "fg_max",
            "ibu_min", "ibu_max", "ebc_min", "ebc_max",
            "abv_min", "abv_max",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "Ex. 21"}),
            "name": forms.TextInput(attrs={"placeholder": "IPA"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "og_min": forms.NumberInput(attrs={"step": "0.001", "min": "1"}),
            "og_max": forms.NumberInput(attrs={"step": "0.001", "min": "1"}),
            "fg_min": forms.NumberInput(attrs={"step": "0.001", "min": "0.9"}),
            "fg_max": forms.NumberInput(attrs={"step": "0.001", "min": "0.9"}),
            "ibu_min": forms.NumberInput(attrs={"step": "1", "min": "0"}),
            "ibu_max": forms.NumberInput(attrs={"step": "1", "min": "0"}),
            "ebc_min": forms.NumberInput(attrs={"step": "0.1", "min": "0"}),
            "ebc_max": forms.NumberInput(attrs={"step": "0.1", "min": "0"}),
            "abv_min": forms.NumberInput(attrs={"step": "0.1", "min": "0"}),
            "abv_max": forms.NumberInput(attrs={"step": "0.1", "min": "0"}),
        }


class FermentationStepForm(StyledModelForm):
    class Meta:
        model = FermentationStep
        fields = ["phase", "temperature_c", "duration_days", "action"]
        widgets = {
            "phase": forms.Select(),
            "temperature_c": forms.NumberInput(attrs={"min": "-5", "max": "40", "step": "0.1"}),
            "duration_days": forms.NumberInput(attrs={"min": "0", "step": "1"}),
            "action": forms.TextInput(attrs={"placeholder": "Ex. transférer, ajouter le houblon..."}),
        }


class BoilSettingsForm(StyledModelForm):
    class Meta:
        model = Recipe
        fields = ["boil_time_min"]
        widgets = {"boil_time_min": forms.NumberInput(attrs={"min": "1", "max": "240", "step": "1"})}


class MashGraphSettingsForm(StyledModelForm):
    class Meta:
        model = Recipe
        fields = [
            "mash_time_min",
            "mash_time_max",
            "mash_temperature_min",
            "mash_temperature_max",
            "mash_time_grid",
            "mash_temperature_grid",
        ]
        widgets = {
            "mash_time_min": forms.NumberInput(attrs={"min": "0", "max": "1440", "step": "1"}),
            "mash_time_max": forms.NumberInput(attrs={"min": "1", "max": "1440", "step": "1"}),
            "mash_temperature_min": forms.NumberInput(attrs={"min": "0", "max": "120", "step": "1"}),
            "mash_temperature_max": forms.NumberInput(attrs={"min": "1", "max": "120", "step": "1"}),
            "mash_time_grid": forms.NumberInput(attrs={"min": "1", "max": "120", "step": "1"}),
            "mash_temperature_grid": forms.NumberInput(attrs={"min": "1", "max": "30", "step": "1"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("mash_time_min", 0) >= cleaned_data.get("mash_time_max", 0):
            self.add_error("mash_time_max", "La borne maximale doit être supérieure à la borne minimale.")
        if cleaned_data.get("mash_temperature_min", 0) >= cleaned_data.get("mash_temperature_max", 0):
            self.add_error("mash_temperature_max", "La borne maximale doit être supérieure à la borne minimale.")
        return cleaned_data


class RecipeEfficiencyForm(StyledModelForm):
    class Meta:
        model = Recipe
        fields = ["efficiency"]
        widgets = {"efficiency": forms.NumberInput(attrs={"min": "1", "max": "100", "step": "0.1"})}


class RecipeNameForm(StyledModelForm):
    class Meta:
        model = Recipe
        fields = ["name"]


class RecipeCategoryForm(StyledModelForm):
    class Meta:
        model = Recipe
        fields = ["category"]


class RecipeNotesForm(StyledModelForm):
    class Meta:
        model = Recipe
        fields = ["notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 5, "placeholder": "Notes générales sur cette recette"})}


class ScaleForm(forms.Form):
    batch_size_l = forms.DecimalField(
        label="Volume final (L)",
        min_value=1,
        max_value=1000,
        decimal_places=2,
        max_digits=6,
        widget=forms.NumberInput(attrs={"step": "0.5", "min": "1"}),
    )


class RecipeTastingForm(StyledModelForm):
    def clean_tasting_rating(self):
        rating = self.cleaned_data.get("tasting_rating")
        if rating is not None:
            if not 0 <= rating <= 5:
                raise forms.ValidationError("La note doit être comprise entre 0 et 5.")
            if rating * 2 != (rating * 2).to_integral_value():
                raise forms.ValidationError("La note doit avancer par demi-étoile.")
        return rating

    class Meta:
        model = Recipe
        fields = [
            "tasting_malt",
            "tasting_bitterness",
            "tasting_hops",
            "tasting_body",
            "tasting_alcohol",
            "tasting_acidity",
            "tasting_rating",
            "tasting_notes",
        ]
        widgets = {
            "tasting_rating": forms.HiddenInput(),
            "tasting_notes": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Arômes, équilibre, longueur en bouche…"}
            ),
        }


class IngredientForm(StyledModelForm):
    class Meta:
        model = Ingredient
        fields = ["name", "kind", "amount_g", "cost_total", "potential_yield", "alpha_acid", "boil_minutes", "attenuation"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0"}),
            "cost_total": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "potential_yield": forms.NumberInput(attrs={"step": "0.1", "min": "0", "max": "100"}),
            "alpha_acid": forms.NumberInput(attrs={"step": "0.1", "min": "0"}),
            "boil_minutes": forms.NumberInput(attrs={"min": "0"}),
            "attenuation": forms.NumberInput(attrs={"step": "1", "min": "0", "max": "100"}),
        }


class IngredientCostForm(forms.Form):
    cost_total = forms.DecimalField(
        label="Coût de cette quantité (€)",
        required=False,
        min_value=0,
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "0", "step": "0.01"}),
    )


class CatalogIngredientForm(StyledModelForm):
    catalog_kind = None

    def __init__(self, *args, **kwargs):
        self.cost_tracking_enabled = kwargs.pop("cost_tracking_enabled", False)
        super().__init__(*args, **kwargs)
        if not self.cost_tracking_enabled:
            self.fields.pop("cost_total", None)
        else:
            self.fields["cost_total"].widget.attrs.update(
                {"min": "0", "step": "0.01", "placeholder": "Inconnu"}
            )
        catalog_queryset = IngredientCatalog.objects.filter(kind=self.catalog_kind)
        self.fields["catalog"].queryset = catalog_queryset
        self.fields["catalog"].required = False
        self.fields["catalog"].widget = forms.HiddenInput()
        self.fields["name"] = forms.ModelChoiceField(
            label="Ingrédient du stock",
            queryset=catalog_queryset,
            required=False,
            empty_label="Sélectionner une fiche de stock",
            initial=self.instance.catalog if self.instance and self.instance.catalog_id else None,
            widget=forms.Select(attrs={"class": "form-select", "data-catalog-name": "true"}),
        )

    def order_add_fields(self, field_names):
        self.order_fields(field_names)

    def limit_edit_fields(self, editable_fields=("amount_g",)):
        if self.instance and self.instance.pk:
            allowed_fields = set(editable_fields)
            if self.cost_tracking_enabled:
                allowed_fields.add("cost_total")
            for field_name in list(self.fields):
                if field_name not in allowed_fields:
                    del self.fields[field_name]

    def clean(self):
        cleaned_data = super().clean()
        catalog = (
            cleaned_data.get("catalog")
            or cleaned_data.get("name")
            or (self.instance.catalog if self.instance and self.instance.catalog_id else None)
        )
        if catalog is None:
            if "name" in self.fields:
                self.add_error("name", "Ce champ est obligatoire.")
        else:
            cleaned_data["catalog"] = catalog
        return cleaned_data

    def save(self, commit=True):
        ingredient = super().save(commit=False)
        catalog = ingredient.catalog
        ingredient.name = catalog.name
        ingredient.manufacturer = catalog.manufacturer
        ingredient.product_id = catalog.product_id
        ingredient.form = catalog.form
        if catalog.kind == IngredientCatalog.Kind.MALT:
            ingredient.color_ebc = catalog.color_ebc
            ingredient.potential_yield = catalog.potential_yield
        elif catalog.kind == IngredientCatalog.Kind.HOP:
            ingredient.alpha_acid = catalog.alpha_acid
        elif catalog.kind == IngredientCatalog.Kind.YEAST:
            ingredient.attenuation = catalog.attenuation
        if commit:
            ingredient.save()
        return ingredient


class MaltForm(CatalogIngredientForm):
    catalog_kind = IngredientCatalog.Kind.MALT

    class Meta:
        model = Ingredient
        fields = ["amount_g", "catalog", "addition", "cost_total"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "5000"}),
            "potential_yield": forms.NumberInput(attrs={"step": "0.1", "min": "0", "max": "100", "placeholder": "80"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount_g"] = forms.IntegerField(
            label="Quantité (g)", min_value=1,
            widget=forms.NumberInput(attrs={"step": "1", "min": "1", "class": "form-control"}),
        )
        self.fields["addition"] = forms.ChoiceField(
            label="Ajout",
            choices=[("", "---------")] + MALT_ADDITION_CHOICES,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.order_add_fields(["name", "amount_g", "addition", "cost_total", "catalog"])
        self.limit_edit_fields()


class HopForm(CatalogIngredientForm):
    catalog_kind = IngredientCatalog.Kind.HOP

    class Meta:
        model = Ingredient
        fields = ["amount_g", "catalog", "addition", "boil_minutes", "addition_temperature_c", "cost_total"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "25"}),
            "alpha_acid": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "5.0"}),
            "boil_minutes": forms.NumberInput(attrs={"min": "0", "placeholder": "60"}),
            "addition_temperature_c": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "0.5"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount_g"] = forms.IntegerField(
            label="Quantité (g)", min_value=1,
            widget=forms.NumberInput(attrs={"step": "1", "min": "1", "class": "form-control"}),
        )
        self.fields["addition"] = forms.ChoiceField(
            label="Ajout",
            choices=[("", "---------")] + ADDITION_CHOICES,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.order_add_fields(["name", "amount_g", "addition", "boil_minutes", "addition_temperature_c", "cost_total", "catalog"])
        self.limit_edit_fields()

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("addition") == "Refroidissement"
            and cleaned_data.get("addition_temperature_c") is None
        ):
            self.add_error(
                "addition_temperature_c",
                "Indiquez la température d'ajout pendant le refroidissement.",
            )
        return cleaned_data


class YeastForm(CatalogIngredientForm):
    catalog_kind = IngredientCatalog.Kind.YEAST

    class Meta:
        model = Ingredient
        fields = ["amount_g", "catalog", "for_bottling", "cost_total"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "11.5"}),
            "attenuation": forms.NumberInput(attrs={"step": "1", "min": "0", "max": "100", "placeholder": "78"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount_g"] = forms.IntegerField(
            label="Nombre de paquets", min_value=1,
            widget=forms.NumberInput(attrs={"step": "1", "min": "1", "class": "form-control"}),
        )
        if "manufacturer" in self.fields:
            self.fields["manufacturer"].label = "Laboratoire"
        if "for_bottling" in self.fields:
            self.fields["for_bottling"].label = "Ajoutée à l'embouteillage"
            self.fields["for_bottling"].widget.attrs["class"] = "form-check-input"
        self.order_add_fields(["name", "amount_g", "for_bottling", "cost_total", "catalog"])
        self.limit_edit_fields()


class OtherForm(CatalogIngredientForm):
    catalog_kind = IngredientCatalog.Kind.OTHER

    class Meta:
        model = Ingredient
        fields = ["amount_g", "catalog", "addition", "boil_minutes", "notes", "cost_total"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "10"}),
            "boil_minutes": forms.NumberInput(attrs={"min": "0", "step": "1"}),
            "notes": forms.TextInput(attrs={"placeholder": "Ex. ajouter avec les écorces fraîches"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount_g"].label = "Quantité"
        self.fields["addition"] = forms.ChoiceField(
            label="Ajout",
            choices=[("", "---------")] + ADDITION_CHOICES,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["boil_minutes"].label = "Minutes avant fin d’ébullition"
        self.order_add_fields(["name", "amount_g", "addition", "boil_minutes", "notes", "cost_total", "catalog"])
        self.limit_edit_fields(("amount_g", "addition", "boil_minutes"))


class CatalogForm(StyledModelForm):
    class Meta:
        model = IngredientCatalog
        fields = [
            "name", "kind", "quantity_available", "manufacturer", "product_id", "form", "color_ebc", "potential_yield",
            "alpha_acid", "attenuation",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        kind = self.data.get("kind") or getattr(self.instance, "kind", None)
        if kind == IngredientCatalog.Kind.CONSUMABLE:
            for field_name in list(self.fields):
                if field_name not in ("name", "quantity_available"):
                    self.fields.pop(field_name)
            self.fields["quantity_available"].label = "Quantité disponible (unités)"
            return
        choices = FORM_CHOICES_BY_KIND.get(kind, MALT_FORMS + HOP_FORMS + YEAST_FORMS)
        current_form = self.initial.get("form", "")
        self.fields["form"] = forms.ChoiceField(
            label="Forme",
            choices=[("", "---------")] + choices,
            required=False,
            initial=current_form,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["quantity_available"].label = (
            "Quantité disponible (paquets)" if kind == "yeast" else "Quantité disponible (g)"
        )


class CatalogMaltForm(StyledModelForm):
    class Meta:
        model = IngredientCatalog
        fields = ["name", "manufacturer", "form", "quantity_available", "color_ebc", "potential_yield"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["form"] = forms.ChoiceField(
            label="Forme",
            choices=[("", "---------")] + MALT_FORMS,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["quantity_available"].label = "Quantité disponible (g)"


class CatalogHopForm(StyledModelForm):
    class Meta:
        model = IngredientCatalog
        fields = ["name", "manufacturer", "form", "quantity_available", "alpha_acid"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["form"] = forms.ChoiceField(
            label="Forme",
            choices=[("", "---------")] + HOP_FORMS,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["quantity_available"].label = "Quantité disponible (g)"


class CatalogYeastForm(StyledModelForm):
    class Meta:
        model = IngredientCatalog
        fields = ["name", "manufacturer", "product_id", "form", "quantity_available", "attenuation"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["form"] = forms.ChoiceField(
            label="Forme",
            choices=[("", "---------")] + YEAST_FORMS,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["manufacturer"].label = "Laboratoire"
        self.fields["quantity_available"].label = "Quantité disponible (paquets)"


class CatalogOtherForm(StyledModelForm):
    class Meta:
        model = IngredientCatalog
        fields = ["name", "form", "quantity_available"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["form"] = forms.ChoiceField(
            label="Forme",
            choices=[("", "---------")] + OTHER_FORMS,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["quantity_available"].label = "Quantité disponible"


class CatalogConsumableForm(StyledModelForm):
    class Meta:
        model = IngredientCatalog
        fields = ["name", "quantity_available"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["quantity_available"].label = "Quantité disponible (unités)"


class MultipleBeerXMLFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleBeerXMLField(forms.FileField):
    widget = MultipleBeerXMLFileInput

    def clean(self, data, initial=None):
        if not data:
            if self.required:
                raise forms.ValidationError(self.error_messages["required"], code="required")
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super().clean(file, initial) for file in files]


class BeerXMLUploadForm(forms.Form):
    file = MultipleBeerXMLField(
        label="Fichier BeerXML",
        widget=MultipleBeerXMLFileInput(
            attrs={"class": "form-control", "accept": ".xml,application/xml,text/xml"}
        ),
    )


class MashStepForm(StyledModelForm):
    class Meta:
        model = MashStep
        fields = ["name", "temperature_c", "duration_min"]
        widgets = {
            "temperature_c": forms.NumberInput(attrs={"step": "0.5", "min": "35", "max": "100", "placeholder": "65"}),
            "duration_min": forms.NumberInput(attrs={"min": "1", "placeholder": "60"}),
        }

    def clean_temperature_c(self):
        temperature = self.cleaned_data["temperature_c"]
        if not 35 <= temperature <= 100:
            raise forms.ValidationError("La température doit être comprise entre 35 et 100 °C.")
        return temperature

    def clean_duration_min(self):
        duration = self.cleaned_data["duration_min"]
        if duration < 1:
            raise forms.ValidationError("La durée doit être positive.")
        return duration

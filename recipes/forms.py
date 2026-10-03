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
FORM_CHOICES_BY_KIND = {
    "malt": MALT_FORMS,
    "hop": HOP_FORMS,
    "yeast": YEAST_FORMS,
    "other": OTHER_FORMS,
}
ADDITION_CHOICES = [
    ("Brassage", "Brassage"),
    ("Empâtage", "Empâtage"),
    ("Mash-out", "Mash-out"),
    ("Ébullition", "Ébullition"),
    ("Whirlpool", "Whirlpool"),
    ("Fermentation primaire", "Fermentation primaire"),
    ("Dry hop", "Dry hop"),
    ("Garde", "Garde"),
    ("Conditionnement", "Conditionnement"),
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
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css_class

    def clean_cost_total(self):
        return self.cleaned_data.get("cost_total") or Decimal("0")

    def clean_quantity_available(self):
        return self.cleaned_data.get("quantity_available") or 0


class RecipeForm(StyledModelForm):
    class Meta:
        model = Recipe
        fields = ["name", "category", "batch_size_l", "efficiency", "target_og", "target_ibu", "boil_time_min", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex. Pale Ale du dimanche"}),
            "batch_size_l": forms.NumberInput(attrs={"step": "0.1", "min": "1"}),
            "efficiency": forms.NumberInput(attrs={"step": "1", "min": "1", "max": "100"}),
            "target_og": forms.NumberInput(attrs={"step": "0.001", "min": "1"}),
            "target_ibu": forms.NumberInput(attrs={"step": "1", "min": "0"}),
            "boil_time_min": forms.NumberInput(attrs={"min": "1", "max": "240", "step": "1"}),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Notes générales sur cette recette"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["boil_time_min"].required = False
        self.fields["efficiency"].label = "Efficacité (%)"

    def clean_boil_time_min(self):
        return self.cleaned_data.get("boil_time_min") or 60


class EquipmentSettingsForm(StyledModelForm):
    class Meta:
        model = EquipmentSettings
        fields = [
            "diameter_cm",
            "height_cm",
            "bag_weight_kg",
            "evaporation_l_min",
            "grain_absorption_l_kg",
            "dead_space_l",
            "mash_efficiency",
        ]
        widgets = {
            "diameter_cm": forms.NumberInput(attrs={"min": "1", "step": "0.1"}),
            "height_cm": forms.NumberInput(attrs={"min": "1", "step": "0.1"}),
            "bag_weight_kg": forms.NumberInput(attrs={"min": "0", "step": "1"}),
            "evaporation_l_min": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "grain_absorption_l_kg": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "dead_space_l": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "mash_efficiency": forms.NumberInput(attrs={"min": "1", "max": "100", "step": "0.1"}),
        }
        labels = {"evaporation_l_min": "évaporation (L/h)"}


class ShoppingItemForm(StyledModelForm):
    class Meta:
        model = ShoppingItem
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex. capsules rouges"}),
        }


class BackupUploadForm(forms.Form):
    file = forms.FileField(
        label="Fichier de sauvegarde JSON",
        widget=forms.ClearableFileInput(attrs={"accept": ".json,application/json"}),
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

    def clean(self):
        cleaned_data = super().clean()
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
            "actual_preboil_volume_l", "actual_batch_size_l", "actual_og",
            "actual_spent_grains_weight_kg",
            "actual_fg", "fermentation_temperature_c", "notes",
        ]
        widgets = {
            "planned_date": forms.DateInput(attrs={"type": "date"}),
            "completed_date": forms.DateInput(attrs={"type": "date"}),
            "actual_batch_size_l": forms.NumberInput(attrs={"min": "0", "step": "0.1"}),
            "actual_preboil_volume_l": forms.NumberInput(attrs={"min": "0", "step": "0.1"}),
            "actual_spent_grains_weight_kg": forms.NumberInput(attrs={"min": "0", "step": "0.001"}),
            "actual_og": forms.NumberInput(attrs={"min": "0.9", "step": "0.001"}),
            "actual_fg": forms.NumberInput(attrs={"min": "0.9", "step": "0.001"}),
            "fermentation_temperature_c": forms.NumberInput(attrs={"min": "0", "max": "40", "step": "0.1"}),
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


class IngredientForm(StyledModelForm):
    class Meta:
        model = Ingredient
        fields = ["name", "kind", "amount_g", "potential_yield", "alpha_acid", "boil_minutes", "attenuation"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0"}),
            "potential_yield": forms.NumberInput(attrs={"step": "0.1", "min": "0", "max": "100"}),
            "alpha_acid": forms.NumberInput(attrs={"step": "0.1", "min": "0"}),
            "boil_minutes": forms.NumberInput(attrs={"min": "0"}),
            "attenuation": forms.NumberInput(attrs={"step": "1", "min": "0", "max": "100"}),
        }


class MaltForm(StyledModelForm):
    class Meta:
        model = Ingredient
        fields = ["amount_g", "catalog", "name", "manufacturer", "form", "addition", "color_ebc", "potential_yield"]
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
        current_form = self.initial.get("form", "")
        self.fields["form"] = forms.ChoiceField(
            label="Forme",
            choices=[("", "---------")] + MALT_FORMS,
            required=False,
            initial=current_form,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["addition"] = forms.ChoiceField(
            label="Ajout",
            choices=[("", "---------")] + ADDITION_CHOICES,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class HopForm(StyledModelForm):
    class Meta:
        model = Ingredient
        fields = ["amount_g", "catalog", "name", "form", "alpha_acid", "addition", "boil_minutes"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "25"}),
            "alpha_acid": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "5.0"}),
            "boil_minutes": forms.NumberInput(attrs={"min": "0", "placeholder": "60"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount_g"] = forms.IntegerField(
            label="Quantité (g)", min_value=1,
            widget=forms.NumberInput(attrs={"step": "1", "min": "1", "class": "form-control"}),
        )
        current_form = self.initial.get("form", "")
        self.fields["form"] = forms.ChoiceField(
            label="Forme",
            choices=[("", "---------")] + HOP_FORMS,
            required=False,
            initial=current_form,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["addition"] = forms.ChoiceField(
            label="Ajout",
            choices=[("", "---------")] + ADDITION_CHOICES,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class YeastForm(StyledModelForm):
    class Meta:
        model = Ingredient
        fields = ["amount_g", "catalog", "name", "manufacturer", "product_id", "form", "attenuation"]
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
        self.fields["manufacturer"].label = "Laboratoire"
        current_form = self.initial.get("form", "")
        self.fields["form"] = forms.ChoiceField(
            label="Forme",
            choices=[("", "---------")] + YEAST_FORMS,
            required=False,
            initial=current_form,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class OtherForm(StyledModelForm):
    class Meta:
        model = Ingredient
        fields = ["amount_g", "catalog", "name", "form", "addition", "notes"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "10"}),
            "notes": forms.TextInput(attrs={"placeholder": "Ex. ajouter avec les écorces fraîches"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount_g"].label = "Quantité"
        current_form = self.initial.get("form", "")
        self.fields["form"] = forms.ChoiceField(
            label="Forme",
            choices=[("", "---------")] + OTHER_FORMS,
            required=False,
            initial=current_form,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["addition"] = forms.ChoiceField(
            label="Ajout",
            choices=[("", "---------")] + ADDITION_CHOICES,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


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


def _catalog_form_init(form_class, kind):
    original_init = form_class.__init__

    def init_with_catalog(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.fields["catalog"].queryset = IngredientCatalog.objects.filter(kind=kind)
        self.fields["catalog"].required = False
        self.fields["name"].required = False
        self.fields["name"].widget.attrs["data-catalog-name"] = "true"

    return init_with_catalog


MaltForm.__init__ = _catalog_form_init(MaltForm, "malt")
HopForm.__init__ = _catalog_form_init(HopForm, "hop")
YeastForm.__init__ = _catalog_form_init(YeastForm, "yeast")
OtherForm.__init__ = _catalog_form_init(OtherForm, "other")

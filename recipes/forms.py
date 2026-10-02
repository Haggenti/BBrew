from decimal import Decimal

from django import forms

from .models import EquipmentSettings, FermentationStep, Ingredient, IngredientCatalog, MashStep, Recipe

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
FORM_CHOICES_BY_KIND = {
    "malt": MALT_FORMS,
    "hop": HOP_FORMS,
    "yeast": YEAST_FORMS,
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
        super().__init__(*args, **kwargs)
        for optional_field in ("manufacturer", "form", "addition", "color_ebc", "cost_total"):
            if optional_field in self.fields:
                self.fields[optional_field].required = False
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css_class

    def clean_cost_total(self):
        return self.cleaned_data.get("cost_total") or Decimal("0")


class RecipeForm(StyledModelForm):
    class Meta:
        model = Recipe
        fields = ["name", "batch_size_l", "efficiency", "target_og", "target_ibu", "boil_time_min", "notes"]
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

    def clean_boil_time_min(self):
        return self.cleaned_data.get("boil_time_min") or 60


class EquipmentSettingsForm(StyledModelForm):
    class Meta:
        model = EquipmentSettings
        fields = [
            "diameter_cm",
            "height_cm",
            "evaporation_l_min",
            "grain_absorption_l_kg",
            "dead_space_l",
            "mash_efficiency",
        ]
        widgets = {
            "diameter_cm": forms.NumberInput(attrs={"min": "1", "step": "0.1"}),
            "height_cm": forms.NumberInput(attrs={"min": "1", "step": "0.1"}),
            "evaporation_l_min": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "grain_absorption_l_kg": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "dead_space_l": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "mash_efficiency": forms.NumberInput(attrs={"min": "1", "max": "100", "step": "0.1"}),
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


class RecipeNameForm(StyledModelForm):
    class Meta:
        model = Recipe
        fields = ["name"]


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
        fields = ["catalog", "name", "amount_g", "manufacturer", "form", "addition", "color_ebc", "potential_yield"]
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
            choices=[("", "---------")] + MALT_FORMS,
            required=False,
            initial=current_form,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["addition"] = forms.ChoiceField(
            choices=[("", "---------")] + ADDITION_CHOICES,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class HopForm(StyledModelForm):
    class Meta:
        model = Ingredient
        fields = ["catalog", "name", "amount_g", "form", "addition", "alpha_acid", "boil_minutes"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "25"}),
            "alpha_acid": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "5.0"}),
            "boil_minutes": forms.NumberInput(attrs={"min": "0", "placeholder": "60"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount_g"] = forms.IntegerField(
            label="Nombre de paquets", min_value=1,
            widget=forms.NumberInput(attrs={"step": "1", "min": "1", "class": "form-control"}),
        )
        current_form = self.initial.get("form", "")
        self.fields["form"] = forms.ChoiceField(
            choices=[("", "---------")] + HOP_FORMS,
            required=False,
            initial=current_form,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["addition"] = forms.ChoiceField(
            choices=[("", "---------")] + ADDITION_CHOICES,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class YeastForm(StyledModelForm):
    class Meta:
        model = Ingredient
        fields = ["catalog", "name", "amount_g", "manufacturer", "form", "attenuation"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "11.5"}),
            "attenuation": forms.NumberInput(attrs={"step": "1", "min": "0", "max": "100", "placeholder": "78"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_form = self.initial.get("form", "")
        self.fields["form"] = forms.ChoiceField(
            choices=[("", "---------")] + YEAST_FORMS,
            required=False,
            initial=current_form,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class CatalogForm(StyledModelForm):
    class Meta:
        model = IngredientCatalog
        fields = [
            "name", "kind", "manufacturer", "form", "color_ebc", "potential_yield",
            "alpha_acid", "attenuation",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        kind = self.data.get("kind") or getattr(self.instance, "kind", None)
        choices = FORM_CHOICES_BY_KIND.get(kind, MALT_FORMS + HOP_FORMS + YEAST_FORMS)
        current_form = self.initial.get("form", "")
        self.fields["form"] = forms.ChoiceField(
            choices=[("", "---------")] + choices,
            required=False,
            initial=current_form,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class CatalogMaltForm(StyledModelForm):
    class Meta:
        model = IngredientCatalog
        fields = ["name", "manufacturer", "form", "color_ebc", "potential_yield"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["form"] = forms.ChoiceField(
            choices=[("", "---------")] + MALT_FORMS,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class CatalogHopForm(StyledModelForm):
    class Meta:
        model = IngredientCatalog
        fields = ["name", "manufacturer", "form", "alpha_acid"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["form"] = forms.ChoiceField(
            choices=[("", "---------")] + HOP_FORMS,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class CatalogYeastForm(StyledModelForm):
    class Meta:
        model = IngredientCatalog
        fields = ["name", "manufacturer", "form", "attenuation"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["form"] = forms.ChoiceField(
            choices=[("", "---------")] + YEAST_FORMS,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class BeerXMLUploadForm(forms.Form):
    file = forms.FileField(label="Fichier BeerXML")


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

    return init_with_catalog


MaltForm.__init__ = _catalog_form_init(MaltForm, "malt")
HopForm.__init__ = _catalog_form_init(HopForm, "hop")
YeastForm.__init__ = _catalog_form_init(YeastForm, "yeast")

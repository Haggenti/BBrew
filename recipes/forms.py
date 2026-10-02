from django import forms

from .models import Ingredient, IngredientCatalog, Recipe

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


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for optional_field in ("manufacturer", "form", "addition", "color_ebc", "cost_total"):
            if optional_field in self.fields:
                self.fields[optional_field].required = False
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css_class


class RecipeForm(StyledModelForm):
    class Meta:
        model = Recipe
        fields = ["name", "batch_size_l", "efficiency", "target_og", "target_ibu"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex. Pale Ale du dimanche"}),
            "batch_size_l": forms.NumberInput(attrs={"step": "0.1", "min": "1"}),
            "efficiency": forms.NumberInput(attrs={"step": "1", "min": "1", "max": "100"}),
            "target_og": forms.NumberInput(attrs={"step": "0.001", "min": "1"}),
            "target_ibu": forms.NumberInput(attrs={"step": "1", "min": "0"}),
        }


class IngredientForm(StyledModelForm):
    class Meta:
        model = Ingredient
        fields = ["name", "kind", "amount_g", "ppg", "alpha_acid", "boil_minutes", "attenuation"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0"}),
            "ppg": forms.NumberInput(attrs={"step": "0.1", "min": "0"}),
            "alpha_acid": forms.NumberInput(attrs={"step": "0.1", "min": "0"}),
            "boil_minutes": forms.NumberInput(attrs={"min": "0"}),
            "attenuation": forms.NumberInput(attrs={"step": "1", "min": "0", "max": "100"}),
        }


class MaltForm(StyledModelForm):
    class Meta:
        model = Ingredient
        fields = ["catalog", "name", "amount_g", "manufacturer", "form", "addition", "color_ebc", "cost_total", "ppg"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "5000"}),
            "ppg": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "37"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_form = self.initial.get("form", "")
        self.fields["form"] = forms.ChoiceField(
            choices=[("", "---------")] + MALT_FORMS,
            required=False,
            initial=current_form,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class HopForm(StyledModelForm):
    class Meta:
        model = Ingredient
        fields = ["catalog", "name", "amount_g", "form", "addition", "alpha_acid", "boil_minutes", "cost_total"]
        widgets = {
            "amount_g": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "25"}),
            "alpha_acid": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "5.0"}),
            "boil_minutes": forms.NumberInput(attrs={"min": "0", "placeholder": "60"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_form = self.initial.get("form", "")
        self.fields["form"] = forms.ChoiceField(
            choices=[("", "---------")] + HOP_FORMS,
            required=False,
            initial=current_form,
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class YeastForm(StyledModelForm):
    class Meta:
        model = Ingredient
        fields = ["catalog", "name", "amount_g", "manufacturer", "form", "cost_total", "attenuation"]
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
            "name", "kind", "manufacturer", "form", "color_ebc", "ppg",
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

from django import forms

from .models import Ingredient, Recipe


class RecipeForm(forms.ModelForm):
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


class IngredientForm(forms.ModelForm):
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

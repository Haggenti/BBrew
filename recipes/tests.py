from decimal import Decimal

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from .calculations import (
    abv_from_gravity,
    estimated_abv,
    estimated_attenuation,
    estimated_color_ebc,
    estimated_final_gravity,
    gravity_points,
    average_mash_temperature,
    ibu_final_gravity_comment,
    ibu_final_gravity_ratio,
    mash_fermentability_limit,
    plato_from_gravity,
    tinseth_ibu,
)
from .forms import ADDITION_CHOICES, HopForm, MaltForm, YeastForm
from .models import BeerCategory, EquipmentSettings, FermentationStep, Ingredient, IngredientCatalog, MashStep, Recipe, RecipeVersion


class CalculationTests(TestCase):
    def test_abv_from_gravity(self):
        self.assertEqual(abv_from_gravity(1.050, 1.010), 5.25)

    def test_gravity_points_are_positive(self):
        self.assertAlmostEqual(gravity_points(5, 80, 20, 75), 57.85, places=1)

    def test_tinseth_ibu_uses_reference_formula_and_ignores_dry_hop(self):
        recipe = Recipe.objects.create(name="IBU test")
        hop = Ingredient.objects.create(
            recipe=recipe,
            name="Cascade",
            kind=Ingredient.Kind.HOP,
            amount_g=28.4,
            alpha_acid=8,
            boil_minutes=60,
        )
        self.assertAlmostEqual(tinseth_ibu([hop], 20, 1.050), 26.2, places=1)
        hop.addition = "Dry hop"
        self.assertEqual(tinseth_ibu([hop], 20, 1.050), 0)

    def test_color_and_abv_use_recipe_ingredients(self):
        recipe = Recipe.objects.create(name="Amber Ale", batch_size_l=20, efficiency=75)
        malt = Ingredient.objects.create(
            recipe=recipe,
            name="Crystal",
            kind=Ingredient.Kind.MALT,
            amount_g=5000,
            color_ebc=50,
        )
        yeast = Ingredient.objects.create(
            recipe=recipe,
            name="Ale yeast",
            kind=Ingredient.Kind.YEAST,
            amount_g=11.5,
            attenuation=80,
        )
        self.assertGreater(estimated_color_ebc([malt], 20), 0)
        self.assertAlmostEqual(estimated_abv(1.050, [yeast]), 5.25)
        self.assertAlmostEqual(estimated_final_gravity(1.050, [yeast]), 1.010, places=3)
        yeast.attenuation = 60
        lower_attenuation_fg = estimated_final_gravity(1.050, [yeast])
        lower_attenuation_abv = estimated_abv(1.050, [yeast])
        self.assertGreater(lower_attenuation_fg, 1.010)
        self.assertLess(lower_attenuation_abv, 5.25)
        self.assertAlmostEqual(plato_from_gravity(1.050), 12.4, places=1)
        self.assertEqual(ibu_final_gravity_ratio(50, 1.010), 49.5)
        self.assertIsNone(ibu_final_gravity_ratio(50, None))
        self.assertEqual(ibu_final_gravity_comment(49.5, 1.010), "équilibrée, finale sèche")
        self.assertEqual(ibu_final_gravity_comment(60, 1.022), "amère, finale liquoreuse")
        self.assertEqual(average_mash_temperature([]), 65.0)
        self.assertAlmostEqual(mash_fermentability_limit(64.5), 85.5)
        self.assertEqual(mash_fermentability_limit(75), 72.0)
        attenuation_at_60c = estimated_attenuation([yeast], [
            MashStep(temperature_c=60, duration_min=60),
        ])
        attenuation_at_70c = estimated_attenuation([yeast], [
            MashStep(temperature_c=70, duration_min=60),
        ])
        self.assertGreater(attenuation_at_60c, attenuation_at_70c)
        self.assertGreater(
            estimated_final_gravity(1.050, [yeast], [
                MashStep(temperature_c=70, duration_min=60),
            ]),
            estimated_final_gravity(1.050, [yeast], [
                MashStep(temperature_c=60, duration_min=60),
            ]),
        )


class RecipeWorkflowTests(TestCase):
    def test_recipe_category_shows_style_indicators(self):
        category = BeerCategory.objects.get(code="21A")
        category.name = "IPA"
        category.og_min = "1.000"
        category.og_max = "1.200"
        category.fg_min = "1.010"
        category.fg_max = "1.018"
        category.ibu_min = 40
        category.ibu_max = 70
        category.ebc_min = 10
        category.ebc_max = 30
        category.abv_min = 5
        category.abv_max = 7.5
        category.save()
        recipe = Recipe.objects.create(name="IPA", category=category, batch_size_l=20, efficiency=75)
        Ingredient.objects.create(
            recipe=recipe,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=5000,
            potential_yield=37,
        )
        response = self.client.post(
            f"/recettes/{recipe.pk}/categorie/",
            {"category": category.pk},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        response = self.client.get(f"/recettes/{recipe.pk}/")
        self.assertContains(response, "Profil de la bière")
        self.assertContains(response, "IPA")
        indicators = response.context["style_indicators"]
        self.assertTrue(0 < indicators[0]["position"] < 100)
        self.assertContains(response, f'width: {indicators[0]["position"]}%')

    def test_recipe_creation_uses_mash_efficiency_as_default(self):
        EquipmentSettings.objects.create(mash_efficiency=82)
        response = self.client.get("/recettes/nouvelle/")
        self.assertEqual(response.context["form"].initial["efficiency"], 82)

    def test_recipe_efficiency_can_be_updated_from_detail(self):
        recipe = Recipe.objects.create(name="Efficiency test", efficiency=75)
        response = self.client.post(
            f"/recettes/{recipe.pk}/efficacite/",
            {"efficiency": "82.5"},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        self.assertEqual(recipe.efficiency, Decimal("82.50"))

    def test_bjcp_categories_are_available_and_manageable(self):
        self.assertEqual(BeerCategory.objects.count(), 110)
        style = BeerCategory.objects.get(code="1A")
        self.assertEqual(style.name, "American Light Lager")
        self.assertEqual(style.og_min, Decimal("1.028"))
        response = self.client.post(
            "/categories/ajouter/",
            {
                "code": "99",
                "name": "Catégorie personnalisée",
                "description": "Test",
                "og_min": "1.040",
                "og_max": "1.060",
                "fg_min": "1.008",
                "fg_max": "1.015",
                "ibu_min": "20",
                "ibu_max": "40",
                "ebc_min": "8",
                "ebc_max": "20",
                "abv_min": "4.0",
                "abv_max": "6.0",
            },
        )
        self.assertRedirects(response, "/categories/")
        category = BeerCategory.objects.get(code="99")
        self.assertEqual(category.og_min, Decimal("1.040"))
        self.assertEqual(category.ibu_max, Decimal("40.0"))

    def test_equipment_settings_can_be_saved(self):
        response = self.client.get("/parametres/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/parametres/",
            {
                "diameter_cm": "50",
                "height_cm": "60",
                "evaporation_l_min": "0.30",
                "grain_absorption_l_kg": "0.80",
                "dead_space_l": "1.5",
                "mash_efficiency": "78",
            },
        )
        self.assertRedirects(response, "/parametres/")
        settings = EquipmentSettings.objects.get()
        self.assertEqual(settings.diameter_cm, 50)
        self.assertEqual(settings.grain_absorption_l_kg, Decimal("0.80"))

    def test_recipe_history_can_restore_a_version(self):
        recipe = Recipe.objects.create(name="Version one")
        ingredient = Ingredient.objects.create(
            recipe=recipe,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=1000,
            potential_yield=37,
        )
        version = RecipeVersion.objects.filter(recipe=recipe).latest("created_at")
        recipe.name = "Version two"
        recipe.save()

        response = self.client.post(
            f"/recettes/{recipe.pk}/historique/{version.pk}/restaurer/",
        )

        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        self.assertEqual(recipe.name, "Version one")
        self.assertEqual(recipe.ingredients.count(), 1)
        self.assertEqual(recipe.ingredients.get().name, ingredient.name)

    def test_fermentation_steps_can_be_added_and_edited(self):
        recipe = Recipe.objects.create(name="Fermented Ale")
        response = self.client.post(
            f"/recettes/{recipe.pk}/fermentation/ajouter/",
            {
                "phase": "Fermentation primaire",
                "temperature_c": "19",
                "duration_days": "7",
                "action": "Contrôler la densité",
            },
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        step = FermentationStep.objects.get(recipe=recipe)
        self.assertEqual(step.position, 1)
        response = self.client.post(
            f"/fermentation/{step.pk}/modifier/",
            {
                "phase": "Cold crash",
                "temperature_c": "4",
                "duration_days": "2",
                "action": "",
            },
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        step.refresh_from_db()
        self.assertEqual(step.phase, "Cold crash")

    def test_create_recipe_page_and_submission(self):
        response = self.client.get("/recettes/nouvelle/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/recettes/nouvelle/",
            {
                "name": "Pale Ale",
                "batch_size_l": "20",
                "efficiency": "75",
                "target_og": "1.050",
                "target_ibu": "25",
            },
        )
        self.assertRedirects(response, "/")
        self.assertTrue(Recipe.objects.filter(name="Pale Ale").exists())

    def test_recipe_detail_contains_estimates_without_chart(self):
        recipe = Recipe.objects.create(name="IPA", batch_size_l=20, efficiency=75)
        Ingredient.objects.create(
            recipe=recipe,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=5000,
            potential_yield=37,
        )
        Ingredient.objects.create(
            recipe=recipe,
            name="Cascade",
            kind=Ingredient.Kind.HOP,
            amount_g=50,
            alpha_acid=5,
            boil_minutes=60,
        )
        response = self.client.get(f"/recettes/{recipe.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "recipe-chart-data")
        self.assertContains(response, "Carbonatation")
        self.assertContains(response, "carb-result")
        self.assertContains(response, "Eau d’empâtage BIAB")
        self.assertContains(response, "water-result")
        self.assertContains(response, "water-preboil")
        self.assertContains(response, "water-capacity-warning")
        self.assertContains(response, "ebc-color-swatch")
        self.assertIsNotNone(response.context["estimated_og"])
        self.assertIsNotNone(response.context["estimated_ibu"])

    def test_delete_recipe_removes_its_ingredients(self):
        recipe = Recipe.objects.create(name="À supprimer")
        Ingredient.objects.create(
            recipe=recipe,
            name="Malt",
            kind=Ingredient.Kind.MALT,
            amount_g=1000,
        )

        response = self.client.post(f"/recettes/{recipe.pk}/supprimer/")

        self.assertRedirects(response, "/")
        self.assertFalse(Recipe.objects.filter(pk=recipe.pk).exists())
        self.assertFalse(Ingredient.objects.filter(recipe_id=recipe.pk).exists())

    def test_ingredient_forms_create_their_own_kind(self):
        recipe = Recipe.objects.create(name="Session IPA")
        response = self.client.post(
            f"/recettes/{recipe.pk}/ingredients/ajouter/",
            {"kind": "hop", "name": "Cascade", "amount_g": "25", "alpha_acid": "5.5", "boil_minutes": "10"},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        ingredient = Ingredient.objects.get(recipe=recipe)
        self.assertEqual(ingredient.kind, Ingredient.Kind.HOP)

    def test_ingredient_can_be_edited_and_deleted(self):
        recipe = Recipe.objects.create(name="Porter")
        ingredient = Ingredient.objects.create(
            recipe=recipe,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=1000,
        )
        response = self.client.post(
            f"/ingredients/{ingredient.pk}/modifier/",
            {"name": "Pale malt bio", "amount_g": "1200", "potential_yield": "37"},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.name, "Pale malt bio")
        self.assertEqual(ingredient.amount_g, 1200)

        response = self.client.post(f"/ingredients/{ingredient.pk}/supprimer/")
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        self.assertFalse(Ingredient.objects.filter(pk=ingredient.pk).exists())

    def test_invalid_ingredient_edit_stays_inline_on_recipe_detail(self):
        recipe = Recipe.objects.create(name="Invalid edit")
        ingredient = Ingredient.objects.create(
            recipe=recipe,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=1000,
            potential_yield=37,
        )

        response = self.client.post(
            f"/ingredients/{ingredient.pk}/modifier/",
            {"name": "", "amount_g": "0", "potential_yield": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "recipes/detail.html")
        self.assertContains(response, f'id="edit-malt-{ingredient.pk}"')
        self.assertContains(response, "Ce champ est obligatoire.")

    def test_catalog_item_populates_recipe_ingredient(self):
        catalog_item = IngredientCatalog.objects.create(
            name="Pilsner 2RP",
            kind=IngredientCatalog.Kind.MALT,
            manufacturer="Château",
            form="Grains",
            color_ebc=3,
            potential_yield=40,
        )
        recipe = Recipe.objects.create(name="Pils")
        response = self.client.post(
            f"/recettes/{recipe.pk}/ingredients/ajouter/",
            {"kind": "malt", "catalog": catalog_item.pk, "name": "", "amount_g": "2500", "potential_yield": "37"},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        ingredient = Ingredient.objects.get(recipe=recipe)
        self.assertEqual(ingredient.catalog, catalog_item)
        self.assertEqual(ingredient.name, "Pilsner 2RP")
        self.assertEqual(ingredient.manufacturer, "Château")
        self.assertEqual(ingredient.color_ebc, 3)
        self.assertEqual(ingredient.potential_yield, 40)

    def test_catalog_item_can_be_edited_and_deleted(self):
        item = IngredientCatalog.objects.create(
            name="Cascade",
            kind=IngredientCatalog.Kind.HOP,
            alpha_acid=5,
        )
        response = self.client.post(
            f"/catalogue/{item.pk}/modifier/",
            {
                "name": "Cascade US",
                "kind": "hop",
                "manufacturer": "Yakima",
                "form": "Pellets",
                "color_ebc": "0",
                "potential_yield": "37",
                "alpha_acid": "6",
                "attenuation": "78",
            },
        )
        self.assertRedirects(response, "/catalogue/")
        item.refresh_from_db()
        self.assertEqual(item.name, "Cascade US")
        self.assertEqual(item.alpha_acid, 6)

        response = self.client.post(f"/catalogue/{item.pk}/supprimer/")
        self.assertRedirects(response, "/catalogue/")
        self.assertFalse(IngredientCatalog.objects.filter(pk=item.pk).exists())

    def test_beerxml_export_and_import(self):
        recipe = Recipe.objects.create(
            name="Export Ale",
            batch_size_l=20,
            efficiency=75,
            target_og=1.050,
            target_ibu=30,
        )
        Ingredient.objects.create(
            recipe=recipe,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=5000,
            color_ebc=6,
        )
        Ingredient.objects.create(
            recipe=recipe,
            name="Cascade",
            kind=Ingredient.Kind.HOP,
            amount_g=25,
            alpha_acid=5.5,
            boil_minutes=10,
        )
        export_response = self.client.get(f"/recettes/{recipe.pk}/exporter/")
        self.assertEqual(export_response.status_code, 200)
        self.assertIn(b"<NAME>Export Ale</NAME>", export_response.content)

        import_response = self.client.post(
            "/recettes/importer/",
            {"file": SimpleUploadedFile("recipe.xml", export_response.content, content_type="application/xml")},
        )
        self.assertEqual(import_response.status_code, 200)
        self.assertContains(import_response, "Ingrédients absents du stock")
        import_response = self.client.post(
            "/recettes/importer/",
            {"confirm_catalog": "1", "add_to_catalog": ["0", "1"]},
        )
        imported = Recipe.objects.exclude(pk=recipe.pk).get()
        self.assertRedirects(import_response, f"/recettes/{imported.pk}/")
        self.assertEqual(imported.ingredients.count(), 2)
        self.assertEqual(IngredientCatalog.objects.filter(name__in=["Pale malt", "Cascade"]).count(), 2)

    def test_global_boil_time_can_be_updated(self):
        recipe = Recipe.objects.create(name="Boil test", boil_time_min=60)
        response = self.client.post(
            f"/recettes/{recipe.pk}/ebullition/",
            {"boil_time_min": "90"},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        self.assertEqual(recipe.boil_time_min, 90)

    def test_recipe_name_and_notes_can_be_updated(self):
        recipe = Recipe.objects.create(name="Ancien nom")
        response = self.client.post(f"/recettes/{recipe.pk}/nom/", {"name": "Nouveau nom"})
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        response = self.client.post(f"/recettes/{recipe.pk}/notes/", {"notes": "Empâtage à surveiller."})
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        self.assertEqual(recipe.name, "Nouveau nom")
        self.assertEqual(recipe.notes, "Empâtage à surveiller.")

    def test_scale_adjusts_ingredient_amounts_and_volume(self):
        recipe = Recipe.objects.create(name="Scaled Ale", batch_size_l=20)
        ingredient = Ingredient.objects.create(
            recipe=recipe,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=5000,
            cost_total=10,
        )
        response = self.client.post(f"/recettes/{recipe.pk}/scale/", {"batch_size_l": "25"})
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        ingredient.refresh_from_db()
        self.assertEqual(recipe.batch_size_l, 25)
        self.assertEqual(ingredient.amount_g, 6250)
        self.assertEqual(ingredient.cost_total, 12.50)

    def test_ingredient_forms_constrain_the_form_choices(self):
        self.assertEqual(
            list(MaltForm().fields["form"].choices)[1:],
            [("Grains", "Grains"), ("Flocons", "Flocons"), ("Farine", "Farine"),
             ("Extrait sec", "Extrait sec"), ("Extrait liquide", "Extrait liquide"),
             ("Sucre solide", "Sucre solide"), ("Sirop", "Sirop")],
        )
        self.assertEqual(
            list(HopForm().fields["form"].choices)[1:],
            [("Pellets", "Pellets"), ("Cônes", "Cônes"), ("Fleurs", "Fleurs"), ("Cryo", "Cryo")],
        )
        self.assertEqual(
            list(YeastForm().fields["form"].choices)[1:],
            [("Sèche", "Sèche"), ("Liquide", "Liquide"), ("Pâte", "Pâte")],
        )
        self.assertEqual(list(MaltForm().fields["addition"].choices)[1:], ADDITION_CHOICES)
        self.assertEqual(list(HopForm().fields["addition"].choices)[1:], ADDITION_CHOICES)

    def test_biab_mash_steps_can_be_created_edited_and_deleted(self):
        recipe = Recipe.objects.create(name="BIAB Pale Ale")
        response = self.client.post(
            f"/recettes/{recipe.pk}/brassage/ajouter/",
            {"name": "Palier principal", "temperature_c": "65", "duration_min": "60"},
        )
        step = MashStep.objects.get(recipe=recipe)
        self.assertEqual(step.position, 1)
        self.assertRedirects(response, f"/recettes/{recipe.pk}/brassage/")

        response = self.client.post(
            f"/paliers/{step.pk}/modifier/",
            {"name": "Palier saccharification", "temperature_c": "67", "duration_min": "60"},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/brassage/")
        step.refresh_from_db()
        self.assertEqual(step.temperature_c, 67)

        response = self.client.post(f"/paliers/{step.pk}/supprimer/")
        self.assertRedirects(response, f"/recettes/{recipe.pk}/brassage/")
        self.assertFalse(MashStep.objects.filter(pk=step.pk).exists())

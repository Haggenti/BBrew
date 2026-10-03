from decimal import Decimal
import json

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
from .forms import ADDITION_CHOICES, CatalogOtherForm, CatalogYeastForm, HopForm, MaltForm, OtherForm, YeastForm
from .beerxml import import_recipe
from .models import BeerCategory, Brew, EquipmentSettings, FermentationStep, Ingredient, IngredientCatalog, MashStep, Recipe, RecipeVersion, ShoppingItem


class CalculationTests(TestCase):
    def test_beerxml_import_reads_littlebock_mash_steps(self):
        data = import_recipe(
            b"""<?xml version="1.0" encoding="ISO-8859-1"?><RECIPES><RECIPE>
            <NAME>Brune</NAME><BATCH_SIZE>22</BATCH_SIZE><STYLE><NAME>Belgian Dark Strong Ale</NAME><CATEGORY_NUMBER>26</CATEGORY_NUMBER></STYLE><MASH><MASH_STEPS>
            <MASH_STEP><NAME>1</NAME><TYPE>Temperature</TYPE><STEP_TIME>60</STEP_TIME><STEP_TEMP>63</STEP_TEMP></MASH_STEP>
            <MASH_STEP><NAME>2</NAME><TYPE>Temperature</TYPE><STEP_TIME>20</STEP_TIME><STEP_TEMP>72</STEP_TEMP></MASH_STEP>
            </MASH_STEPS></MASH><MISCS><MISC><NAME>&#xC9;corce d'orange</NAME><AMOUNT>0.02</AMOUNT><TYPE>&#xC9;pice</TYPE><USE>&#xC9;bullition</USE></MISC></MISCS><PRIMARY_AGE>2</PRIMARY_AGE><PRIMARY_TEMP>16</PRIMARY_TEMP>
            </RECIPE></RECIPES>"""
        )
        self.assertEqual(data["mash_steps"][0]["temperature_c"], 63)
        self.assertEqual(data["mash_steps"][1]["duration_min"], 20)
        self.assertEqual(data["fermentation_steps"][0]["duration_days"], 2)
        self.assertEqual(data["category_code"], "26")
        self.assertEqual(data["category_name"], "Belgian Dark Strong Ale")
        self.assertEqual(data["ingredients"][-1]["kind"], "other")
        self.assertEqual(data["ingredients"][-1]["amount_g"], 20)

    def test_beerxml_import_reads_malt_form(self):
        data = import_recipe(
            b"""<RECIPES><RECIPE><NAME>Malt</NAME><FERMENTABLES><FERMENTABLE>
            <NAME>Pilsen</NAME><AMOUNT>2</AMOUNT><FORM>Grain</FORM><COLOR>5</COLOR><YIELD>80</YIELD>
            </FERMENTABLE></FERMENTABLES></RECIPE></RECIPES>"""
        )
        self.assertEqual(data["ingredients"][0]["form"], "Grains")

    def test_beerxml_import_reads_malt_type_as_form(self):
        data = import_recipe(
            b"""<RECIPES><RECIPE><NAME>Malt</NAME><FERMENTABLES><FERMENTABLE>
            <NAME>Pilsen</NAME><AMOUNT>2</AMOUNT><TYPE>Grain</TYPE><COLOR>5</COLOR><YIELD>80</YIELD>
            </FERMENTABLE></FERMENTABLES></RECIPE></RECIPES>"""
        )
        self.assertEqual(data["ingredients"][0]["form"], "Grains")

    def test_beerxml_import_maps_yeast_form_and_laboratory(self):
        data = import_recipe(
            b"""<RECIPES><RECIPE><NAME>Levure</NAME><YEASTS><YEAST>
            <NAME>SafBrew Ale</NAME><AMOUNT>0.001</AMOUNT><AMOUNT_IS_WEIGHT>TRUE</AMOUNT_IS_WEIGHT>
            <FORM>Dry</FORM><PRODUCT_ID>S-33</PRODUCT_ID><LABORATORY>Fermentis</LABORATORY>
            <ATTENUATION>73.0</ATTENUATION></YEAST></YEASTS></RECIPE></RECIPES>"""
        )
        yeast = data["ingredients"][0]
        self.assertEqual(yeast["name"], "SafBrew Ale (S-33)")
        self.assertEqual(yeast["form"], "Sèche")
        self.assertEqual(yeast["product_id"], "S-33")
        self.assertEqual(yeast["manufacturer"], "Fermentis")

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
        category.fg_min = "1.000"
        category.fg_max = "1.100"
        category.ibu_min = 0
        category.ibu_max = 100
        category.ebc_min = 0
        category.ebc_max = 100
        category.abv_min = 0
        category.abv_max = 20
        category.save()
        recipe = Recipe.objects.create(name="IPA", category=category, batch_size_l=20, efficiency=75)
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
            amount_g=25,
            alpha_acid=5,
            boil_minutes=60,
        )
        Ingredient.objects.create(
            recipe=recipe,
            name="Ale yeast",
            kind=Ingredient.Kind.YEAST,
            amount_g=11.5,
            attenuation=80,
        )
        response = self.client.post(
            f"/recettes/{recipe.pk}/categorie/",
            {"category": category.pk},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        response = self.client.get(f"/recettes/{recipe.pk}/")
        self.assertContains(response, "Profil de la bière")
        self.assertContains(response, "IPA")
        self.assertContains(response, "Styles compatibles avec la recette")
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
                "bag_weight_kg": "1250",
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
        self.assertEqual(settings.bag_weight_kg, Decimal("1250.0"))

    def test_database_reset_requires_confirmation_and_selected_sections(self):
        recipe = Recipe.objects.create(name="À conserver")
        Brew.objects.create(recipe=recipe, recipe_name=recipe.name)
        IngredientCatalog.objects.create(name="Pale malt", kind=IngredientCatalog.Kind.MALT)

        response = self.client.post(
            "/parametres/remise-a-zero/",
            {"reset_section": ["recipes"], "confirmation": "incorrect"},
        )
        self.assertRedirects(response, "/parametres/")
        self.assertTrue(Recipe.objects.filter(pk=recipe.pk).exists())

        response = self.client.post(
            "/parametres/remise-a-zero/",
            {"reset_section": ["recipes"], "confirmation": "SUPPRIMER"},
        )
        self.assertRedirects(response, "/parametres/")
        self.assertFalse(Recipe.objects.filter(pk=recipe.pk).exists())
        self.assertTrue(Brew.objects.exists())
        self.assertTrue(IngredientCatalog.objects.exists())

    def test_recipe_history_can_restore_a_version(self):
        recipe = Recipe.objects.create(name="Version one")
        catalog = IngredientCatalog.objects.create(
            name="Pale malt",
            kind=IngredientCatalog.Kind.MALT,
        )
        ingredient = Ingredient.objects.create(
            recipe=recipe,
            catalog=catalog,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=1000,
            potential_yield=37,
        )
        self.client.post(f"/recettes/{recipe.pk}/versions/ajouter/", {"reason": "Version avec ingrédient"})
        version = RecipeVersion.objects.filter(recipe=recipe).latest("version_number")
        recipe.name = "Version two"
        recipe.save()
        version_count_before_restore = RecipeVersion.objects.filter(recipe=recipe).count()

        response = self.client.post(
            f"/recettes/{recipe.pk}/historique/{version.pk}/restaurer/",
        )

        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        self.assertEqual(recipe.name, "Version one")
        self.assertEqual(recipe.ingredients.count(), 1)
        self.assertEqual(recipe.ingredients.get().name, ingredient.name)
        self.assertEqual(recipe.ingredients.get().catalog_id, catalog.pk)
        self.assertEqual(
            RecipeVersion.objects.filter(recipe=recipe).count(),
            version_count_before_restore,
        )

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

    def test_fermentation_steps_can_be_reordered(self):
        recipe = Recipe.objects.create(name="Ordre fermentation")
        first = FermentationStep.objects.create(
            recipe=recipe, position=1, phase="Fermentation primaire",
            temperature_c=19, duration_days=7,
        )
        second = FermentationStep.objects.create(
            recipe=recipe, position=2, phase="Cold crash",
            temperature_c=4, duration_days=2,
        )
        response = self.client.post(
            f"/recettes/{recipe.pk}/fermentation/reordonner/",
            {"step_order": [str(second.pk), str(first.pk)]},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(second.position, 1)
        self.assertEqual(first.position, 2)

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
        self.assertFalse(RecipeVersion.objects.filter(recipe_id=recipe.pk).exists())

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
        self.assertContains(import_response, "Une recette porte déjà ce nom")
        import_response = self.client.post(
            "/recettes/importer/",
            {
                "confirm_catalog": "1",
                "add_to_catalog": ["0", "1"],
                "import_name": "Export Ale importée",
                "conflict_action": "rename",
            },
        )
        imported = Recipe.objects.exclude(pk=recipe.pk).get()
        self.assertRedirects(import_response, f"/recettes/{imported.pk}/")
        self.assertEqual(imported.ingredients.count(), 2)
        self.assertEqual(IngredientCatalog.objects.filter(name__in=["Pale malt", "Cascade"]).count(), 2)
        self.assertEqual(RecipeVersion.objects.filter(recipe=imported).count(), 1)
        self.assertIn("Import BeerXML", RecipeVersion.objects.get(recipe=imported).reason)

    def test_beerxml_multiple_files_can_be_imported(self):
        xml_template = b"""<?xml version="1.0"?><RECIPES><RECIPE><NAME>%s</NAME>
        <BATCH_SIZE>20</BATCH_SIZE><EFFICIENCY>75</EFFICIENCY><OG>1.050</OG>
        <IBU>25</IBU><BOIL_TIME>60</BOIL_TIME></RECIPE></RECIPES>"""
        response = self.client.post(
            "/recettes/importer/",
            {
                "file": [
                    SimpleUploadedFile("one.xml", xml_template % b"One", content_type="application/xml"),
                    SimpleUploadedFile("two.xml", xml_template % b"Two", content_type="application/xml"),
                ]
            },
        )
        self.assertRedirects(response, "/")
        self.assertEqual(Recipe.objects.filter(name__in=["One", "Two"]).count(), 2)

    def test_backup_can_be_downloaded_and_restored(self):
        catalog = IngredientCatalog.objects.create(
            name="Pale malt",
            kind=IngredientCatalog.Kind.MALT,
            quantity_available=5000,
        )
        recipe = Recipe.objects.create(name="Sauvegarde Ale")
        Ingredient.objects.create(
            recipe=recipe,
            catalog=catalog,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=2500,
        )

        backup_response = self.client.get("/parametres/sauvegarde.json")
        self.assertEqual(backup_response.status_code, 200)
        self.assertEqual(backup_response["Content-Type"], "application/json")

        recipe.name = "Données à remplacer"
        recipe.save()
        restore_response = self.client.post(
            "/parametres/restaurer/",
            {"file": SimpleUploadedFile("bbrew.json", backup_response.content, content_type="application/json")},
        )

        self.assertRedirects(restore_response, "/")
        restored = Recipe.objects.get()
        self.assertEqual(restored.name, "Sauvegarde Ale")
        self.assertEqual(restored.ingredients.get().catalog.name, "Pale malt")
        self.assertFalse(Recipe.objects.filter(name="Données à remplacer").exists())

    def test_brew_can_be_created_viewed_and_updated(self):
        recipe = Recipe.objects.create(name="Bière de test")
        response = self.client.post(
            "/brassins/ajouter/",
            {
                "recipe": recipe.pk,
                "status": "planned",
                "planned_date": "2026-10-10",
                "completed_date": "",
                "actual_preboil_volume_l": "28",
                "actual_og": "1.052",
                "actual_fg": "1.010",
                "fermentation_temperature_c": "19",
                "actual_batch_size_l": "",
                "actual_spent_grains_weight_kg": "",
                "notes": "Prévoir un palier de 66 °C.",
            },
        )
        brew = Brew.objects.get()
        self.assertRedirects(response, "/brassins/")
        self.assertEqual(brew.recipe_name, "Bière de test")
        self.assertIsNotNone(brew.recipe_version)
        self.assertIn("V1", brew.recipe_version_label)
        form_response = self.client.get("/brassins/ajouter/")
        self.assertContains(form_response, "Version initiale")
        self.assertEqual(form_response.context["latest_versions"][recipe.pk], brew.recipe_version.pk)

        response = self.client.get(f"/brassins/{brew.pk}/")
        self.assertContains(response, "Prévoir un palier de 66 °C.")

        response = self.client.post(
            f"/brassins/{brew.pk}/modifier/",
            {
                "recipe": recipe.pk,
                "status": "brewing",
                "planned_date": "2026-10-10",
                "completed_date": "",
                "actual_preboil_volume_l": "28",
                "actual_og": "1.052",
                "actual_fg": "1.010",
                "fermentation_temperature_c": "19",
                "actual_batch_size_l": "19.5",
                "actual_spent_grains_weight_kg": "",
                "notes": "Brassage démarré.",
            },
        )
        self.assertRedirects(response, f"/brassins/{brew.pk}/")
        brew.refresh_from_db()
        self.assertEqual(brew.status, Brew.Status.BREWING)
        self.assertEqual(brew.actual_batch_size_l, Decimal("19.5"))
        self.assertEqual(brew.actual_abv, 5.51)
        detail_response = self.client.get(f"/brassins/{brew.pk}/")
        self.assertContains(detail_response, "Évaporation totale")
        self.assertContains(detail_response, "8,50 L")
        self.assertContains(detail_response, "8,50 L/h")

        response = self.client.post(f"/brassins/{brew.pk}/supprimer/")
        self.assertRedirects(response, "/brassins/")
        self.assertFalse(Brew.objects.filter(pk=brew.pk).exists())
        self.assertTrue(Recipe.objects.filter(pk=recipe.pk).exists())

    def test_brew_volume_can_be_entered_as_headspace_measurement(self):
        EquipmentSettings.objects.create(diameter_cm=40, height_cm=45)
        recipe = Recipe.objects.create(name="Mesure cuve")
        response = self.client.post(
            "/brassins/ajouter/",
            {
                "recipe": recipe.pk,
                "status": "planned",
                "planned_date": "",
                "actual_preboil_volume_l": "",
                "preboil_volume_mode": "headspace",
                "preboil_headspace_cm": "5",
                "actual_batch_size_l": "",
                "batch_volume_mode": "headspace",
                "batch_headspace_cm": "10",
            },
        )
        self.assertRedirects(response, "/brassins/")
        brew = Brew.objects.get()
        self.assertAlmostEqual(float(brew.actual_preboil_volume_l), 50.27, places=2)
        self.assertAlmostEqual(float(brew.actual_batch_size_l), 43.98, places=2)

    def test_brew_calculates_residual_water_from_spent_grains(self):
        EquipmentSettings.objects.create(bag_weight_kg=1200)
        recipe = Recipe.objects.create(name="Drêches")
        Ingredient.objects.create(
            recipe=recipe,
            name="Pilsen",
            kind=Ingredient.Kind.MALT,
            amount_g=5000,
        )
        brew = Brew.objects.create(
            recipe=recipe,
            recipe_name=recipe.name,
            actual_spent_grains_weight_kg=8.7,
        )
        from .views import _brew_comparison

        comparison = _brew_comparison(brew)
        self.assertAlmostEqual(comparison["grain_weight_kg"], 5)
        self.assertAlmostEqual(comparison["residual_water_kg"], 2.5)
        self.assertAlmostEqual(comparison["absorption_l_per_kg"], 0.5)

    def test_shopping_list_items_can_be_added_checked_and_deleted(self):
        response = self.client.get("/courses/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/courses/ajouter/", {"name": "Capsules rouges"})
        self.assertRedirects(response, "/courses/")
        item = ShoppingItem.objects.get()
        self.assertFalse(item.is_completed)

        response = self.client.post(f"/courses/{item.pk}/cocher/")
        self.assertRedirects(response, "/courses/")
        item.refresh_from_db()
        self.assertTrue(item.is_completed)

        response = self.client.post(f"/courses/{item.pk}/supprimer/")
        self.assertRedirects(response, "/courses/")
        self.assertFalse(ShoppingItem.objects.filter(pk=item.pk).exists())

    def test_beerxml_import_can_replace_existing_recipe(self):
        recipe = Recipe.objects.create(name="Même nom", target_ibu=10)
        Ingredient.objects.create(
            recipe=recipe,
            name="Ancien ingrédient",
            kind=Ingredient.Kind.MALT,
            amount_g=1000,
        )
        xml = """<?xml version="1.0"?><RECIPES><RECIPE><NAME>Même nom</NAME>
        <BATCH_SIZE>20</BATCH_SIZE><EFFICIENCY>75</EFFICIENCY>
        <OG>1.050</OG><IBU>30</IBU><BOIL_TIME>60</BOIL_TIME>
        <FERMENTABLES><FERMENTABLE><NAME>Nouveau malt</NAME><AMOUNT>2</AMOUNT>
        <COLOR>5</COLOR><YIELD>80</YIELD></FERMENTABLE></FERMENTABLES>
        </RECIPE></RECIPES>""".encode()

        response = self.client.post(
            "/recettes/importer/",
            {"file": SimpleUploadedFile("recipe.xml", xml, content_type="application/xml")},
        )
        self.assertContains(response, "Une recette porte déjà ce nom")
        response = self.client.post(
            "/recettes/importer/",
            {"confirm_catalog": "1", "conflict_action": "replace", "import_name": "Même nom"},
        )

        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        self.assertEqual(recipe.target_ibu, 30)
        self.assertEqual(list(recipe.ingredients.values_list("name", flat=True)), ["Nouveau malt"])

    def test_beerxml_import_fills_existing_stock_malt_form(self):
        catalog = IngredientCatalog.objects.create(
            name="Pilsen",
            kind=IngredientCatalog.Kind.MALT,
            form="",
        )
        data = import_recipe(
            b"""<RECIPES><RECIPE><NAME>Stock form</NAME><FERMENTABLES><FERMENTABLE>
            <NAME>Pilsen</NAME><AMOUNT>2</AMOUNT><FORM>Grain</FORM><COLOR>5</COLOR><YIELD>80</YIELD>
            </FERMENTABLE></FERMENTABLES></RECIPE></RECIPES>"""
        )
        from .views import _finish_recipe_import

        _finish_recipe_import(data, set())
        catalog.refresh_from_db()
        self.assertEqual(catalog.form, "Grains")

    def test_brew_can_consume_stock_once(self):
        catalog = IngredientCatalog.objects.create(
            name="Pale malt",
            kind=IngredientCatalog.Kind.MALT,
            quantity_available=5000,
        )
        recipe = Recipe.objects.create(name="Brassin stock")
        Ingredient.objects.create(
            recipe=recipe,
            catalog=catalog,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=2500,
        )
        self.client.post(f"/recettes/{recipe.pk}/versions/ajouter/", {"reason": "Version de brassage"})
        response = self.client.post(
            "/brassins/ajouter/",
            {"recipe": recipe.pk, "status": "planned", "planned_date": ""},
        )
        brew = Brew.objects.get()

        response = self.client.post(
            f"/brassins/{brew.pk}/consommer-stock/",
            {"stock_item": f"{catalog.pk}:{Ingredient.Kind.MALT}"},
        )

        self.assertRedirects(response, f"/brassins/{brew.pk}/")
        catalog.refresh_from_db()
        brew.refresh_from_db()
        self.assertEqual(catalog.quantity_available, 2500)
        self.assertIsNotNone(brew.stock_consumed_at)

        self.client.post(f"/brassins/{brew.pk}/consommer-stock/")
        catalog.refresh_from_db()
        self.assertEqual(catalog.quantity_available, 2500)

        response = self.client.post(
            f"/brassins/{brew.pk}/annuler-consommation-stock/",
            {"stock_item": f"{catalog.pk}:{Ingredient.Kind.MALT}"},
        )
        self.assertRedirects(response, f"/brassins/{brew.pk}/")
        catalog.refresh_from_db()
        brew.refresh_from_db()
        self.assertEqual(catalog.quantity_available, 5000)
        self.assertIsNone(brew.stock_consumed_at)

    def test_global_boil_time_can_be_updated(self):
        recipe = Recipe.objects.create(name="Boil test", boil_time_min=60)
        response = self.client.post(
            f"/recettes/{recipe.pk}/ebullition/",
            {"boil_time_min": "90"},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        self.assertEqual(recipe.boil_time_min, 90)

    def test_boil_timeline_is_in_chronological_countdown_order(self):
        recipe = Recipe.objects.create(name="Chronological boil")
        late_hop = Ingredient.objects.create(
            recipe=recipe,
            name="Late hop",
            kind=Ingredient.Kind.HOP,
            amount_g=20,
            boil_minutes=5,
        )
        early_hop = Ingredient.objects.create(
            recipe=recipe,
            name="Early hop",
            kind=Ingredient.Kind.HOP,
            amount_g=30,
            boil_minutes=60,
        )
        same_time_hop = Ingredient.objects.create(
            recipe=recipe,
            name="Second early hop",
            kind=Ingredient.Kind.HOP,
            amount_g=15,
            boil_minutes=60,
        )

        response = self.client.get(f"/recettes/{recipe.pk}/")

        events = response.context["boil_events"]
        self.assertEqual(
            [event["type"] for event in events],
            ["start", "timer", "hop", "hop", "timer", "hop", "cool"],
        )
        self.assertEqual(events[1]["minutes"], 60)
        self.assertEqual(events[4]["minutes"], 5)
        self.assertEqual(events[2]["row"]["ingredient"], early_hop)
        self.assertEqual(events[3]["row"]["ingredient"], same_time_hop)
        self.assertEqual(events[5]["row"]["ingredient"], late_hop)

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

    def test_recipe_volume_can_change_without_scaling_ingredients(self):
        recipe = Recipe.objects.create(name="Volume seul", batch_size_l=20)
        ingredient = Ingredient.objects.create(
            recipe=recipe,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=5000,
        )
        response = self.client.post(
            f"/recettes/{recipe.pk}/scale/",
            {"batch_size_l": "25", "action": "volume_only"},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        ingredient.refresh_from_db()
        self.assertEqual(recipe.batch_size_l, Decimal("25"))
        self.assertEqual(ingredient.amount_g, Decimal("5000.0"))

    def test_ingredient_forms_constrain_the_form_choices(self):
        self.assertEqual(MaltForm().fields["catalog"].label, "Stock")
        self.assertEqual(MaltForm().fields["potential_yield"].label, "Rendement")
        self.assertEqual(MaltForm().fields["form"].label, "Forme")
        self.assertEqual(MaltForm().fields["addition"].label, "Ajout")
        self.assertEqual(HopForm().fields["form"].label, "Forme")
        self.assertEqual(HopForm().fields["addition"].label, "Ajout")
        self.assertEqual(YeastForm().fields["form"].label, "Forme")
        self.assertEqual(OtherForm().fields["form"].label, "Forme")
        self.assertEqual(OtherForm().fields["addition"].label, "Ajout")
        self.assertEqual(OtherForm().fields["amount_g"].label, "Quantité")
        self.assertNotIn("manufacturer", OtherForm().fields)
        self.assertEqual(YeastForm().fields["manufacturer"].label, "Laboratoire")
        self.assertEqual(CatalogYeastForm().fields["manufacturer"].label, "Laboratoire")
        self.assertNotIn("manufacturer", CatalogOtherForm().fields)
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

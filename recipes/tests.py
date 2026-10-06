from decimal import Decimal
from datetime import date
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import connection
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import translation
from django.utils import timezone

from bbrew.session_lifecycle import invalidate_sessions_on_startup

from .calculations import (
    abv_from_gravity,
    estimated_abv,
    estimated_attenuation,
    estimated_color_ebc,
    estimated_final_gravity,
    gravity_points,
    average_mash_temperature,
    ebc_color_rgb,
    ibu_final_gravity_comment,
    ibu_final_gravity_ratio,
    mash_fermentability_limit,
    plato_from_gravity,
    tinseth_ibu,
)
from .forms import ADDITION_CHOICES, MALT_ADDITION_CHOICES, BrewForm, CatalogForm, CatalogOtherForm, CatalogYeastForm, HopForm, MaltForm, MashStepForm, OtherForm, YeastForm
from .beerxml import import_recipe
from .backup import validate_backup
from .models import ActivityEvent, BeerCategory, Brew, EquipmentSettings, FermentationStep, Ingredient, IngredientCatalog, MashStep, Recipe, RecipeVersion, ShoppingItem
from .templatetags.recipe_formatting import compact_number


class RecipeFormattingTests(TestCase):
    def test_compact_number_trims_zeros_and_keeps_french_decimal_separator(self):
        with translation.override("fr-fr"):
            self.assertEqual(compact_number(1.010), "1,01")
            self.assertEqual(compact_number(31.100), "31,1")
            self.assertEqual(compact_number(19.100), "19,1")
            self.assertEqual(compact_number(18), "18")
            self.assertEqual(compact_number(4.200), "4,2")


class AuthenticationTests(TestCase):
    def test_anonymous_users_are_redirected_to_login(self):
        response = self.client.get("/")

        self.assertRedirects(response, "/accounts/login/?next=/")
        self.assertRedirects(
            self.client.get("/a-propos/"),
            "/accounts/login/?next=/a-propos/",
        )

    def test_login_page_displays_full_bbs_logo(self):
        response = self.client.get("/accounts/login/")

        self.assertContains(response, 'src="/static/recipes/bbs-logo.svg"')
        self.assertContains(response, 'alt="BBS — Brewing Brain System"')
        self.assertContains(response, "Le BBS des brasseurs.")
        self.assertNotContains(response, "Modem 56k facultatif")
        self.assertContains(response, "#0055aa")

    def test_default_credentials_can_log_in_and_log_out(self):
        response = self.client.post(
            "/accounts/login/",
            {"username": "brewer", "password": "brewer"},
        )

        self.assertRedirects(response, "/")
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        response = self.client.post("/accounts/logout/")
        self.assertRedirects(response, "/accounts/login/")
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(SESSION_EXPIRE_AT_BROWSER_CLOSE=True)
    def test_session_cookie_expires_when_browser_closes(self):
        response = self.client.post(
            "/accounts/login/",
            {"username": "brewer", "password": "brewer"},
        )

        session_cookie = response.cookies["sessionid"]
        self.assertEqual(session_cookie["expires"], "")
        self.assertEqual(session_cookie["max-age"], "")

    def test_server_start_invalidates_existing_sessions(self):
        self.client.login(username="brewer", password="brewer")
        session_key = self.client.session.session_key
        self.assertTrue(Session.objects.filter(session_key=session_key).exists())

        invalidate_sessions_on_startup()

        self.assertFalse(Session.objects.filter(session_key=session_key).exists())
        response = self.client.get("/")
        self.assertRedirects(response, "/accounts/login/?next=/")

    def test_user_can_change_default_password(self):
        self.assertTrue(self.client.login(username="brewer", password="brewer"))

        response = self.client.post(
            "/accounts/password_change/",
            {
                "old_password": "brewer",
                "new_password1": "new-secure-password-2026",
                "new_password2": "new-secure-password-2026",
            },
        )

        self.assertRedirects(response, "/accounts/password_change/done/")
        user = get_user_model().objects.get(username="brewer")
        self.assertTrue(user.check_password("new-secure-password-2026"))


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

    def test_beerxml_import_omits_empty_yeast_product_reference(self):
        data = import_recipe(
            b"""<RECIPES><RECIPE><NAME>Levure</NAME><YEASTS><YEAST>
            <NAME>Abbaye Belgian</NAME><AMOUNT>0.001</AMOUNT><PRODUCT_ID>-</PRODUCT_ID>
            </YEAST></YEASTS></RECIPE></RECIPES>"""
        )
        yeast = data["ingredients"][0]
        self.assertEqual(yeast["name"], "Abbaye Belgian")
        self.assertEqual(yeast["product_id"], "")

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

    def test_ebc_color_around_thirty_is_red(self):
        color = ebc_color_rgb(31)
        red, green, blue = (int(channel) for channel in color[4:-1].split(", "))
        self.assertGreater(red, green * 2)
        self.assertGreater(red, blue * 2)


class RecipeWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="workflow-test",
            password="test-password",
        )
        self.client.force_login(self.user)

    def test_dashboard_alerts_only_planned_brew_stock_deficits(self):
        catalog = IngredientCatalog.objects.create(
            name="Pale malt",
            kind=IngredientCatalog.Kind.MALT,
            quantity_available=0,
        )
        response = self.client.get("/")
        self.assertContains(response, 'src="/static/recipes/bbs-logo-dashboard.svg"')
        self.assertContains(response, 'src="/static/recipes/bbs-logo-curseur.svg"')
        self.assertNotContains(response, "boingball_10_80x80_64.gif")
        self.assertEqual(response.context["dashboard"]["stock_alert_count"], 0)

        recipe = Recipe.objects.create(name="Brassin prévu")
        version = recipe.versions.first()
        version.snapshot = {
            "ingredients": [
                {"catalog": catalog.pk, "kind": Ingredient.Kind.MALT, "amount_g": 1000}
            ]
        }
        version.save(update_fields=["snapshot"])
        Brew.objects.create(
            recipe=recipe,
            recipe_version=version,
            recipe_name=recipe.name,
            planned_date=timezone.localdate(),
            status=Brew.Status.PLANNED,
        )

        response = self.client.get("/")
        self.assertEqual(response.context["dashboard"]["stock_alert_count"], 1)

        Brew.objects.update(status=Brew.Status.BREWING)
        response = self.client.get("/")
        self.assertEqual(response.context["dashboard"]["stock_alert_count"], 0)

    def test_about_page_has_bbs_design_and_navigation_link(self):
        response = self.client.get("/a-propos/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Brewing Brain System")
        self.assertContains(response, "BBS des brasseurs")
        self.assertContains(response, "CONNECT")
        self.assertContains(response, 'href="/a-propos/"')
        self.assertContains(response, "VERSION Développement")
        self.assertContains(
            response,
            'href="https://github.com/Haggenti/BBrew"',
        )

    def test_brew_calendar_navigation_allows_month_and_year_selection(self):
        response = self.client.get("/brassins/", {"month": "2026-10"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["calendar_month"], "octobre 2026")
        self.assertContains(response, 'id="calendar-month-picker"')
        self.assertContains(response, 'aria-label="Mois précédent"')
        self.assertContains(response, 'aria-label="Mois suivant"')
        self.assertContains(
            response,
            f'href="?month={response.context["today_month"]}">Aujourd’hui</a>',
            html=False,
        )
        self.assertContains(response, '<option value="10" selected>octobre</option>', html=False)
        self.assertContains(response, '<option value="2026" selected>2026</option>', html=False)

        selected_response = self.client.get(
            "/brassins/",
            {"month_number": "3", "year": "2027"},
        )
        self.assertEqual(selected_response.context["calendar_month"], "mars 2027")

    def test_brew_number_and_bottling_date_are_shown_in_calendar(self):
        brew = Brew.objects.create(
            recipe_name="Brassin test",
            planned_date=date(2026, 10, 10),
            completed_date=date(2026, 10, 25),
        )
        later_brew = Brew.objects.create(recipe_name="Brassin suivant")
        self.assertGreater(later_brew.pk, brew.pk)

        response = self.client.get("/brassins/", {"month": "2026-10"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"N° {brew.pk}")
        self.assertContains(response, f"Brassin n°{brew.pk} — Brassin test")
        self.assertContains(
            response,
            f"Embouteillage — Brassin n°{brew.pk} — Brassin test",
        )
        self.assertContains(response, "brew-calendar-span")
        self.assertContains(response, "span-end")
        self.assertContains(response, 'class="brew-calendar-bottling d-inline-block me-1"')
        self.assertNotContains(response, "<svg")
        self.assertEqual(
            response.context["calendar_days"][date(2026, 10, 10)],
            [brew],
        )
        bottling_day = next(
            day
            for week in response.context["calendar_weeks"]
            for day in week["days"]
            if day["date"] == date(2026, 10, 25)
        )
        self.assertEqual(bottling_day["bottlings"], [])
        self.assertEqual(len(bottling_day["brew_spans"]), 1)
        self.assertTrue(bottling_day["brew_spans"][0]["ends"])
        brewing_day = next(
            day
            for week in response.context["calendar_weeks"]
            for day in week["days"]
            if day["date"] == date(2026, 10, 10)
        )
        self.assertTrue(brewing_day["brew_spans"][0]["starts"])
        middle_day = next(
            day
            for week in response.context["calendar_weeks"]
            for day in week["days"]
            if day["date"] == date(2026, 10, 18)
        )
        self.assertEqual(middle_day["brew_spans"][0]["brew"], brew)
        self.assertFalse(middle_day["brew_spans"][0]["starts"])
        self.assertFalse(middle_day["brew_spans"][0]["ends"])

    def test_brew_number_restarts_at_one_when_all_brews_are_deleted(self):
        first = Brew.objects.create(recipe_name="Premier brassin")
        second = Brew.objects.create(recipe_name="Deuxième brassin")
        first.delete()

        next_brew = Brew.objects.create(recipe_name="Brassin suivant")
        self.assertEqual(next_brew.pk, second.pk + 1)

        Brew.objects.all().delete()

        restarted_brew = Brew.objects.create(recipe_name="Nouvelle série")
        self.assertEqual(restarted_brew.pk, 1)

    def test_empty_brew_table_starts_at_one_even_with_a_stale_sequence(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO sqlite_sequence (name, seq) VALUES (%s, %s)",
                [Brew._meta.db_table, 42],
            )

        brew = Brew.objects.create(recipe_name="Premier brassin")

        self.assertEqual(brew.pk, 1)

    def test_catalog_groups_stock_deficits_by_planned_brew(self):
        malt = IngredientCatalog.objects.create(
            name="Pale malt",
            kind=IngredientCatalog.Kind.MALT,
            quantity_available=0,
        )
        hop = IngredientCatalog.objects.create(
            name="Cascade",
            kind=IngredientCatalog.Kind.HOP,
            quantity_available=2,
        )
        recipe = Recipe.objects.create(name="Bière de Noël")
        version = recipe.versions.first()
        version.snapshot = {
            "ingredients": [
                {
                    "catalog": malt.pk,
                    "kind": Ingredient.Kind.MALT,
                    "name": malt.name,
                    "amount_g": 1000,
                },
                {
                    "catalog": hop.pk,
                    "kind": Ingredient.Kind.HOP,
                    "name": hop.name,
                    "amount_g": 5,
                },
            ]
        }
        version.save(update_fields=["snapshot"])
        brew = Brew.objects.create(
            recipe=recipe,
            recipe_version=version,
            recipe_name=recipe.name,
            planned_date=timezone.localdate(),
            status=Brew.Status.PLANNED,
        )

        response = self.client.get("/catalogue/")

        alerts = response.context["stock_alert_brews"]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["brew"], brew)
        self.assertEqual(
            [(item["name"], item["deficit"]) for item in alerts[0]["missing_items"]],
            [("Pale malt", 1000), ("Cascade", 3)],
        )
        self.assertContains(response, f"Pour <a class=\"fw-semibold\" href=\"/brassins/{brew.pk}/\">{brew.recipe_name}</a>")
        self.assertContains(response, "Pale malt")
        self.assertContains(response, "Cascade")

    def test_brew_form_rejects_bottling_before_brew_date(self):
        form = BrewForm(
            data={
                "planned_date": "2026-10-10",
                "completed_date": "2026-10-09",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("completed_date", form.errors)

    def test_mash_step_form_rejects_temperature_outside_brewing_range(self):
        form = MashStepForm(data={"name": "Empâtage", "temperature_c": "101", "duration_min": "60"})

        self.assertFalse(form.is_valid())
        self.assertIn("temperature_c", form.errors)
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
        self.assertContains(response, "Profil")
        self.assertContains(response, "IPA")
        self.assertContains(response, "Styles compatibles avec la recette")
        indicators = response.context["style_indicators"]
        alcohol_indicator = next(item for item in indicators if item["label"] == "Alcool")
        self.assertEqual(alcohol_indicator["precision"], 1)
        self.assertContains(response, "ABV estimé")
        self.assertContains(response, 'toFixed(1).replace(".", ",")')
        self.assertTrue(0 < indicators[0]["position"] < 100)
        self.assertLess(indicators[0]["scale_minimum"], indicators[0]["minimum"])
        self.assertGreater(indicators[0]["scale_maximum"], indicators[0]["maximum"])
        self.assertGreater(indicators[0]["style_start"], 0)
        self.assertLess(indicators[0]["style_start"] + indicators[0]["style_width"], 100)
        self.assertLessEqual(indicators[0]["scale_minimum"], indicators[0]["value"])
        self.assertGreaterEqual(indicators[0]["scale_maximum"], indicators[0]["value"])
        self.assertContains(response, 'class="profile-style-range"')
        self.assertContains(response, 'class="profile-value-cursor')
        self.assertContains(response, 'class="profile-value-label')
        self.assertNotContains(response, "dans la fourchette")
        self.assertNotContains(response, "au-dessus")
        self.assertNotContains(response, "en dessous")

    def test_recipe_without_category_gets_default_18a_profile(self):
        recipe = Recipe.objects.create(name="Sans profil")

        response = self.client.get(f"/recettes/{recipe.pk}/")

        recipe.refresh_from_db()
        self.assertEqual(recipe.category.code, "18A")
        self.assertContains(response, "Profil")
        self.assertContains(response, "18A")
        self.assertEqual(response.context["style_indicators"], [])

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

        target = BeerCategory.objects.get(code="1B")
        target_name = target.name
        response = self.client.post(
            f"/categories/{target.pk}/copier-fourchettes/",
            {"source_id": category.pk},
        )
        self.assertRedirects(response, "/categories/")
        target.refresh_from_db()
        self.assertEqual(target.og_min, category.og_min)
        self.assertEqual(target.og_max, category.og_max)
        self.assertEqual(target.ibu_min, category.ibu_min)
        self.assertEqual(target.ibu_max, category.ibu_max)
        self.assertEqual(target.name, target_name)

    def test_equipment_settings_can_be_saved(self):
        response = self.client.get("/parametres/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/parametres/",
            {
                "diameter_cm": "50",
                "height_cm": "60",
                "bag_weight_g": "1250",
                "evaporation_l_h": "0.30",
                "grain_absorption_l_kg": "0.80",
                "dead_space_l": "1.5",
                "mash_efficiency": "78",
                "cost_management_enabled": "on",
            },
        )
        self.assertRedirects(response, "/parametres/")
        settings = EquipmentSettings.objects.get()
        self.assertEqual(settings.diameter_cm, 50)
        self.assertEqual(settings.grain_absorption_l_kg, Decimal("0.80"))
        self.assertEqual(settings.bag_weight_g, Decimal("1250.0"))
        self.assertTrue(settings.cost_management_enabled)

    def test_activity_log_records_model_creation_updates_and_deletions(self):
        recipe = Recipe.objects.create(name="Journal Ale")
        self.assertTrue(
            ActivityEvent.objects.filter(
                event_type=ActivityEvent.EventType.CREATE,
                description="Création — recette : Journal Ale",
            ).exists()
        )

        recipe.name = "Journal IPA"
        recipe.save(update_fields=["name"])
        self.assertTrue(
            ActivityEvent.objects.filter(
                event_type=ActivityEvent.EventType.UPDATE,
                description="Modification — recette : Journal IPA",
            ).exists()
        )

        response = self.client.get("/parametres/journal/?q=Journal+IPA")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Modification — recette : Journal IPA")
        self.assertNotContains(response, "Création — recette : Journal Ale")
        self.assertContains(self.client.get("/parametres/"), "Ouvrir le journal")

        recipe.delete()
        self.assertTrue(
            ActivityEvent.objects.filter(
                event_type=ActivityEvent.EventType.DELETE,
                description="Suppression — recette : Journal IPA",
            ).exists()
        )

    def test_activity_log_can_be_cleared(self):
        Recipe.objects.create(name="Journal à vider")
        self.assertTrue(ActivityEvent.objects.exists())

        response = self.client.post("/parametres/journal/vider/")

        self.assertRedirects(response, "/parametres/journal/")
        self.assertFalse(ActivityEvent.objects.exists())

    def test_activity_log_records_shopping_brew_relationship_changes(self):
        brew = Brew.objects.create(recipe_name="Brassin lié")
        item = ShoppingItem.objects.create(name="Houblon à acheter")
        item.source_brews.add(brew)

        self.assertTrue(
            ActivityEvent.objects.filter(
                event_type=ActivityEvent.EventType.UPDATE,
                description__contains="Brassins associés",
            ).exists()
        )

    def test_recipe_cost_estimate_uses_unit_costs_from_stock(self):
        EquipmentSettings.objects.create(cost_management_enabled=True)
        recipe = Recipe.objects.create(name="Coût stock", batch_size_l=20)
        ingredients = [
            (Ingredient.Kind.MALT, 3000, Decimal("2.0000"), Decimal("99.00"), Decimal("6.00")),
            (Ingredient.Kind.HOP, 20, Decimal("0.0500"), Decimal("99.00"), Decimal("1.00")),
            (Ingredient.Kind.YEAST, 2, Decimal("3.0000"), Decimal("99.00"), Decimal("6.00")),
            (Ingredient.Kind.OTHER, 3, Decimal("4.0000"), Decimal("99.00"), Decimal("12.00")),
        ]
        for index, (kind, quantity, unit_cost, legacy_cost, _) in enumerate(ingredients):
            catalog = IngredientCatalog.objects.create(
                name=f"Ingrédient {index}",
                kind=kind,
                unit_cost=unit_cost,
            )
            Ingredient.objects.create(
                recipe=recipe,
                catalog=catalog,
                name=catalog.name,
                kind=kind,
                amount_g=quantity,
                cost_total=legacy_cost,
            )
        unpriced_malt = IngredientCatalog.objects.create(
            name="Malt sans prix",
            kind=IngredientCatalog.Kind.MALT,
        )
        Ingredient.objects.create(
            recipe=recipe,
            catalog=unpriced_malt,
            name=unpriced_malt.name,
            kind=Ingredient.Kind.MALT,
            amount_g=1000,
        )

        response = self.client.get(f"/recettes/{recipe.pk}/")

        self.assertEqual(response.context["malt_cost_total"], Decimal("6.00"))
        self.assertEqual(response.context["hop_cost_total"], Decimal("1.00"))
        self.assertEqual(response.context["yeast_cost_total"], Decimal("6.00"))
        self.assertEqual(response.context["other_cost_total"], Decimal("12.00"))
        self.assertEqual(
            response.context["estimated_recipe_cost"],
            Decimal("25.00"),
        )
        self.assertEqual(response.context["malt_rows"][0]["stock_cost"], Decimal("6.00"))
        self.assertIsNone(response.context["malt_rows"][1]["stock_cost"])
        self.assertContains(response, "6,00 €")
        self.assertContains(response, "1,00 €")
        self.assertContains(response, "12,00 €")
        self.assertContains(response, "Coût total estimé des ingrédients")
        self.assertContains(response, "25,00 €")
        self.assertContains(
            response,
            '<small class="ingredient-display d-block text-secondary">6,00 €</small>',
        )
        self.assertNotContains(
            response,
            '[data-drop-zone="malt"] td:nth-child(2) > .ingredient-display.d-block',
        )
        self.assertContains(response, "Coût non renseigné")
        self.assertNotContains(response, "Coût estimé des ingrédients")
        self.assertNotContains(response, "Coût total manuel")
        self.assertNotIn("cost_total", MaltForm().fields)
        self.assertNotIn("cost_total", HopForm().fields)
        self.assertNotIn("cost_total", YeastForm().fields)
        self.assertNotIn("cost_total", OtherForm().fields)

    def test_brew_detail_places_planned_actual_next_to_analysis(self):
        recipe = Recipe.objects.create(name="Ale à analyser")
        brew = Brew.objects.create(recipe=recipe, recipe_name=recipe.name)

        response = self.client.get(f"/brassins/{brew.pk}/")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        bottling_position = content.index("Mise en bouteille")
        comparison_row_position = content.index('<div class="row g-3 mt-0 align-items-stretch">')
        analysis_position = content.index("Analyse du brassin")
        comparison_position = content.index("<h2 class=\"h5 mb-0\">Prévu / réel</h2>")
        self.assertLess(bottling_position, comparison_row_position)
        self.assertLess(comparison_row_position, analysis_position)
        self.assertLess(analysis_position, comparison_position)
        self.assertContains(response, f"Brassin n°{brew.pk} · créé le")
        self.assertContains(response, 'data-bs-target="#bottling-modal"')
        self.assertContains(response, 'id="bottling-modal"')
        self.assertContains(response, f'action="/brassins/{brew.pk}/mise-en-bouteille/"')
        self.assertContains(response, f'action="/brassins/{brew.pk}/cycle-statut/"')
        self.assertContains(response, "brew-status-badge status-planned")

        response = self.client.post(
            f"/brassins/{brew.pk}/cycle-statut/",
            {"return_to": "detail"},
        )
        self.assertRedirects(response, f"/brassins/{brew.pk}/")
        brew.refresh_from_db()
        self.assertEqual(brew.status, Brew.Status.BREWING)
        response = self.client.get(f"/brassins/{brew.pk}/")
        self.assertContains(response, "brew-status-badge status-brewing")

    def test_brew_status_can_be_cycled_from_brew_list(self):
        brew = Brew.objects.create(recipe_name="Statut cyclique")
        self.assertEqual(brew.status, Brew.Status.PLANNED)

        response = self.client.get("/brassins/")
        self.assertContains(response, f'action="/brassins/{brew.pk}/cycle-statut/"')
        self.assertContains(response, "Cliquer pour passer à l’étape suivante")

        expected_statuses = [
            Brew.Status.BREWING,
            Brew.Status.FERMENTING,
            Brew.Status.CONDITIONING,
            Brew.Status.COMPLETED,
            Brew.Status.CANCELLED,
            Brew.Status.PLANNED,
        ]
        for expected_status in expected_statuses:
            response = self.client.post(f"/brassins/{brew.pk}/cycle-statut/")
            self.assertRedirects(response, "/brassins/")
            brew.refresh_from_db()
            self.assertEqual(brew.status, expected_status)

        response = self.client.get(f"/brassins/{brew.pk}/cycle-statut/")
        self.assertEqual(response.status_code, 405)

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

    def test_fermentation_graph_updates_temperature_duration_and_order(self):
        recipe = Recipe.objects.create(name="Graphique fermentation")
        yeast_catalog = IngredientCatalog.objects.create(
            name="Levure de test",
            kind=IngredientCatalog.Kind.YEAST,
            fermentation_temperature_min_c=18,
            fermentation_temperature_max_c=22,
        )
        Ingredient.objects.create(
            recipe=recipe,
            catalog=yeast_catalog,
            name=yeast_catalog.name,
            kind=Ingredient.Kind.YEAST,
            amount_g=11.5,
        )
        first = FermentationStep.objects.create(
            recipe=recipe,
            position=1,
            phase=FermentationStep.Phase.PRIMARY,
            temperature_c=19,
            duration_days=7,
            action="Contrôler la densité",
        )
        second = FermentationStep.objects.create(
            recipe=recipe,
            position=2,
            phase=FermentationStep.Phase.COLD_CRASH,
            temperature_c=4,
            duration_days=2,
        )

        detail_response = self.client.get(f"/recettes/{recipe.pk}/")
        rendered = detail_response.content.decode()
        self.assertEqual(
            detail_response.context["fermentation_temperature_zones"][0]["name"],
            "Levure de test",
        )
        self.assertEqual(
            (
                detail_response.context["fermentation_temperature_zones"][0]["min"],
                detail_response.context["fermentation_temperature_zones"][0]["max"],
            ),
            (18.0, 22.0),
        )
        self.assertEqual(
            detail_response.context["fermentation_temperature_zones"][0]["fill_color"],
            "rgba(255, 235, 140, 0.4)",
        )
        self.assertContains(detail_response, "<th>Plage de fermentation</th>")
        self.assertContains(detail_response, "18–22 °C")
        self.assertContains(detail_response, "Levure de test : 18–22 °C")
        self.assertContains(detail_response, "beforeDatasetsDraw(chart)")
        self.assertContains(detail_response, "fermentationTemperatureZones")
        self.assertContains(detail_response, "scales.y.getPixelForValue(0)")
        self.assertContains(detail_response, 'ctx.setLineDash([4, 4])')
        self.assertContains(detail_response, 'ctx.strokeStyle = "#dc3545"')
        self.assertContains(detail_response, "chart.tooltip.setActiveElements(activeTooltipElement")
        self.assertContains(detail_response, "chart.update(\"none\")")
        self.assertContains(detail_response, "steps[stepIndex - 1].duration = boundedElapsed - previousStart")
        self.assertContains(detail_response, "remainingDays = steps.slice(stepIndex).reduce")
        self.assertContains(detail_response, "endpoint: true")
        self.assertContains(detail_response, "steps[stepIndex].duration = Math.max(1, Math.min(dayMaximum() - previousDays, requestedElapsed - previousDays))")
        self.assertContains(detail_response, "stepIndex + (draggedFermentationEndpoint ? 1 : 0)")
        self.assertContains(detail_response, "déplacez le début d’un palier")
        fermentation_section = rendered.split("Fermentation", 1)[1].split("Carbonatation", 1)[0]
        self.assertLess(
            fermentation_section.index("fermentation-summary-table"),
            fermentation_section.index("fermentation-profile-chart"),
        )
        self.assertContains(detail_response, ".fermentation-layout { display: grid; grid-template-columns: minmax(0, max-content) minmax(0, 1fr);")
        self.assertContains(detail_response, ".fermentation-summary-column .table-responsive { max-width: 100%; width: max-content; }")
        self.assertContains(detail_response, ".fermentation-summary-table { max-width: 100%; width: auto; }")
        self.assertContains(detail_response, "Math.min(40, Math.max(5, totalDays() + 5))")
        self.assertContains(detail_response, "max: 30")
        self.assertContains(detail_response, "min: -2")
        self.assertContains(detail_response, "stepSize: 1, autoSkip: false")
        self.assertContains(detail_response, "ticks: { stepSize: 1, autoSkip: false, font: { size: 9 }, padding: 2 }")
        self.assertContains(detail_response, "Math.round(value)")
        self.assertContains(detail_response, 'style="height: 440px"')
        self.assertContains(detail_response, 'id="fermentation-step-modal"')
        self.assertNotContains(detail_response, 'data-bs-target="#add-fermentation"')
        self.assertContains(detail_response, 'form="fermentation-graph-form"')
        self.assertContains(detail_response, 'form="mash-graph-form"')
        summary_markup = rendered.split('id="fermentation-steps-list"', 1)[1].split("</tbody>", 1)[0]
        self.assertNotIn('draggable="true"', summary_markup)
        self.assertNotIn("/supprimer/", summary_markup)
        self.assertIn('<td class="text-secondary text-nowrap">1.</td>', summary_markup)
        self.assertContains(detail_response, "actionPoint: index + 1 < steps.length")
        self.assertContains(detail_response, 'context.raw?.actionPoint ? "#fd7e14"')

        response = self.client.post(
            f"/recettes/{recipe.pk}/fermentation/graphique/",
            {
                "step_id": [str(first.pk), str(second.pk)],
                "step_phase": ["Fermentation primaire", "Cold crash"],
                "step_temperature": ["20", "3"],
                "step_duration": ["6", "3"],
                "step_action": ["Contrôler la densité", "Refroidissement"],
            },
        )

        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.position, first.temperature_c, first.duration_days), (1, 20, 6))
        self.assertEqual(first.action, "Contrôler la densité")
        self.assertEqual((second.position, second.temperature_c, second.duration_days), (2, 3, 3))
        self.assertEqual(second.phase, FermentationStep.Phase.COLD_CRASH)
        self.assertEqual(second.action, "Refroidissement")

    def test_fermentation_graph_can_add_and_remove_steps(self):
        recipe = Recipe.objects.create(name="Graphique vide")

        response = self.client.get(f"/recettes/{recipe.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fermentation-profile-chart")
        self.assertContains(response, "fermentation-graph-form")
        response = self.client.post(
            f"/recettes/{recipe.pk}/fermentation/graphique/",
            {
                "step_id": ["new-1"],
                "step_phase": ["Dry hop"],
                "step_temperature": ["18"],
                "step_duration": ["5"],
                "step_action": ["Ajouter 50 g de houblon"],
            },
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        step = FermentationStep.objects.get(recipe=recipe)
        self.assertEqual(step.phase, "Dry hop")
        self.assertEqual(step.temperature_c, 18)
        self.assertEqual(step.duration_days, 5)
        self.assertEqual(step.action, "Ajouter 50 g de houblon")

        self.client.post(
            f"/recettes/{recipe.pk}/fermentation/graphique/",
            {
                "step_id": [],
                "step_phase": [],
                "step_temperature": [],
                "step_duration": [],
                "step_action": [],
            },
        )

        self.assertFalse(FermentationStep.objects.filter(recipe=recipe).exists())

    def test_fermentation_graph_rejects_temperature_outside_integer_range(self):
        recipe = Recipe.objects.create(name="Température hors échelle")
        step = FermentationStep.objects.create(
            recipe=recipe,
            phase=FermentationStep.Phase.PRIMARY,
            temperature_c=20,
            duration_days=5,
        )

        self.client.post(
            f"/recettes/{recipe.pk}/fermentation/graphique/",
            {
                "step_id": [str(step.pk)],
                "step_phase": ["Fermentation primaire"],
                "step_temperature": ["20.5"],
                "step_duration": ["5"],
                "step_action": [""],
            },
        )

        step.refresh_from_db()
        self.assertEqual(step.temperature_c, 20)

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
        self.assertRedirects(response, "/recettes/")
        self.assertTrue(Recipe.objects.filter(name="Pale Ale").exists())

    def test_brew_creation_can_start_from_recipe_detail(self):
        recipe = Recipe.objects.create(name="Recipe de départ")

        response = self.client.get(f"/brassins/ajouter/?recipe={recipe.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ">Recette<")
        self.assertEqual(response.context["form"].initial["recipe"], recipe)

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
        rendered_detail = response.content.decode()
        settings_position = rendered_detail.index("Paramètres de brassage")
        notes_position = rendered_detail.index(">Notes</h2>")
        self.assertLess(settings_position, notes_position)
        self.assertIn(
            '<div class="col-12 col-lg-4">\n    <section class="card card-body h-100 border-secondary-subtle">',
            rendered_detail,
        )
        self.assertIn('<div class="col-12 col-lg-8">\n    <section class="card card-body h-100">', rendered_detail)
        self.assertContains(response, "carb-result")
        self.assertContains(response, 'data-bs-target="#carbonation-settings-modal"')
        self.assertContains(response, 'id="carbonation-settings-modal"')
        self.assertContains(response, "Réglages de carbonatation")
        rendered_detail = response.content.decode()
        carbonation_controls = rendered_detail.split(
            'id="carbonation-settings-modal"',
            1,
        )[1].split("</div>\n</div>\n<script>", 1)[0]
        self.assertIn('id="carb-result"', rendered_detail.split(
            'id="carbonation-settings-modal"',
            1,
        )[0])
        self.assertIn('id="carb-volume"', carbonation_controls)
        self.assertIn('id="carb-target"', carbonation_controls)
        self.assertIn('id="carb-temperature"', carbonation_controls)
        self.assertIn('id="carb-sugar"', carbonation_controls)
        self.assertContains(response, "Eau de départ nécessaire")
        self.assertContains(response, "water-result")
        self.assertNotContains(response, "water-preboil")
        self.assertNotContains(response, "water-capacity-warning")
        self.assertContains(response, "beer-color-card")
        self.assertContains(response, ".beer-glass-preview.ebc-preview { width: 6rem; height: 8rem;")
        self.assertContains(response, "beer-glass-preview")
        profile_section = response.content.decode().split(
            '<h2 class="h5 mb-0">Profil</h2>',
            1,
        )[1].split("</section>", 1)[0]
        self.assertNotIn("beer-glass-preview", profile_section)
        self.assertIsNotNone(response.context["estimated_ebc_color"])
        self.assertIsNotNone(response.context["estimated_og"])
        self.assertIsNotNone(response.context["estimated_ibu"])
        self.assertContains(response, "tasting-profile-chart")
        self.assertContains(response, 'data-bs-target="#tasting-profile-modal"')
        self.assertContains(response, 'id="tasting-profile-modal"')
        self.assertContains(response, "data-tasting-stars")
        self.assertEqual(len(response.context["tasting_stars"]), 5)
        notes_section = response.content.decode().split('action="/recettes/%s/notes/"' % recipe.pk, 1)[1]
        self.assertIn('data-bs-target="#tasting-profile-modal"', notes_section.split("</form>", 1)[0])
        self.assertContains(response, "Non noté")
        self.assertContains(response, "Cliquez ou faites glisser sur un axe")
        self.assertNotContains(response, 'data-tasting-range')

    def test_recipe_tasting_profile_saves_optional_scores_and_notes(self):
        recipe = Recipe.objects.create(name="Dégustation")
        version_count = recipe.versions.count()

        response = self.client.post(
            f"/recettes/{recipe.pk}/degustation/",
            {
                "tasting_malt": "4",
                "tasting_bitterness": "2",
                "tasting_hops": "5",
                "tasting_body": "",
                "tasting_alcohol": "1",
                "tasting_acidity": "",
                "tasting_rating": "4.5",
                "tasting_notes": "Notes d’agrumes et finale sèche.",
            },
        )

        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        self.assertEqual(recipe.tasting_malt, 4)
        self.assertEqual(recipe.tasting_bitterness, 2)
        self.assertEqual(recipe.tasting_hops, 5)
        self.assertIsNone(recipe.tasting_body)
        self.assertEqual(recipe.tasting_alcohol, 1)
        self.assertIsNone(recipe.tasting_acidity)
        self.assertEqual(recipe.tasting_rating, Decimal("4.5"))
        self.assertEqual(recipe.tasting_notes, "Notes d’agrumes et finale sèche.")
        self.assertEqual(recipe.versions.count(), version_count)

    def test_recipe_tasting_profile_rejects_scores_above_five(self):
        recipe = Recipe.objects.create(name="Note invalide")

        response = self.client.post(
            f"/recettes/{recipe.pk}/degustation/",
            {"tasting_malt": "6"},
        )

        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        self.assertIsNone(recipe.tasting_malt)

    def test_recipe_tasting_rating_rejects_non_half_steps_and_out_of_range(self):
        recipe = Recipe.objects.create(name="Note invalide")
        for rating in ("4.2", "5.5", "-0.5"):
            with self.subTest(rating=rating):
                response = self.client.post(
                    f"/recettes/{recipe.pk}/degustation/",
                    {"tasting_rating": rating},
                )
                self.assertRedirects(response, f"/recettes/{recipe.pk}/")
                recipe.refresh_from_db()
                self.assertIsNone(recipe.tasting_rating)

    def test_recipe_detail_marks_ingredients_missing_from_stock(self):
        recipe = Recipe.objects.create(name="Ingrédient non référencé")
        catalog = IngredientCatalog.objects.create(name="Pale malt", kind=IngredientCatalog.Kind.MALT)
        Ingredient.objects.create(
            recipe=recipe,
            catalog=catalog,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=1000,
        )
        Ingredient.objects.create(
            recipe=recipe,
            name="Houblon local",
            kind=Ingredient.Kind.HOP,
            amount_g=25,
        )

        response = self.client.get(f"/recettes/{recipe.pk}/")

        self.assertContains(response, 'title="Ingrédient absent du stock"')
        self.assertContains(response, 'aria-label="Ingrédient absent du stock"')
        self.assertContains(response, ">Houblon local</span>")

    def test_delete_recipe_removes_its_ingredients(self):
        recipe = Recipe.objects.create(name="À supprimer")
        Ingredient.objects.create(
            recipe=recipe,
            name="Malt",
            kind=Ingredient.Kind.MALT,
            amount_g=1000,
        )

        response = self.client.post(f"/recettes/{recipe.pk}/supprimer/")

        self.assertRedirects(response, "/recettes/")
        self.assertFalse(Recipe.objects.filter(pk=recipe.pk).exists())
        self.assertFalse(Ingredient.objects.filter(recipe_id=recipe.pk).exists())
        self.assertFalse(RecipeVersion.objects.filter(recipe_id=recipe.pk).exists())

    def test_ingredient_forms_create_their_own_kind(self):
        recipe = Recipe.objects.create(name="Session IPA")
        catalog = IngredientCatalog.objects.create(name="Cascade", kind=IngredientCatalog.Kind.HOP)
        response = self.client.post(
            f"/recettes/{recipe.pk}/ingredients/ajouter/",
            {"kind": "hop", "catalog": catalog.pk, "amount_g": "25", "addition": "Ébullition", "boil_minutes": "10"},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        ingredient = Ingredient.objects.get(recipe=recipe)
        self.assertEqual(ingredient.kind, Ingredient.Kind.HOP)

    def test_other_ingredient_can_be_added_at_a_specific_boil_time(self):
        recipe = Recipe.objects.create(name="Épices à l’ébullition")
        catalog = IngredientCatalog.objects.create(name="Coriandre", kind=IngredientCatalog.Kind.OTHER)

        response = self.client.post(
            f"/recettes/{recipe.pk}/ingredients/ajouter/",
            {
                "kind": "other",
                "catalog": catalog.pk,
                "amount_g": "5",
                "addition": "Ébullition",
                "boil_minutes": "15",
            },
        )

        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        ingredient = Ingredient.objects.get(recipe=recipe)
        self.assertEqual(ingredient.boil_minutes, 15)
        timeline_response = self.client.get(f"/recettes/{recipe.pk}/")
        additions = [
            event for event in timeline_response.context["boil_events"]
            if event["type"] == "addition"
        ]
        self.assertEqual(additions[-1]["rows"][0]["ingredient"], ingredient)
        self.assertContains(timeline_response, "Coriandre")
        self.assertContains(timeline_response, "15 min")

    def test_ingredient_create_rejects_catalog_of_wrong_kind(self):
        recipe = Recipe.objects.create(name="Validation")
        malt = IngredientCatalog.objects.create(name="Pilsner", kind=IngredientCatalog.Kind.MALT)
        response = self.client.post(
            f"/recettes/{recipe.pk}/ingredients/ajouter/",
            {"kind": "hop", "catalog": malt.pk, "amount_g": "25"},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        self.assertFalse(Ingredient.objects.filter(recipe=recipe).exists())

    def test_recipe_detail_renders_inventory_and_drop_zone_hooks(self):
        recipe = Recipe.objects.create(name="Drag and drop")
        catalog = IngredientCatalog.objects.create(
            name="Pale malt", kind=IngredientCatalog.Kind.MALT, quantity_available=5000
        )
        Ingredient.objects.create(
            recipe=recipe,
            catalog=catalog,
            name=catalog.name,
            kind=Ingredient.Kind.MALT,
            amount_g=1000,
        )
        response = self.client.get(f"/recettes/{recipe.pk}/")
        self.assertContains(response, 'id="recipe-inventory"')
        self.assertContains(response, "Ingrédients référencés")
        self.assertContains(response, 'data-bs-scroll="true"')
        self.assertContains(response, 'data-bs-backdrop="false"')
        self.assertContains(response, 'data-catalog-id=')
        self.assertContains(response, 'data-drop-zone="malt"')
        self.assertContains(response, 'data-drop-zone="hop"')
        self.assertContains(response, 'data-inventory-kind="malt"')
        self.assertContains(response, 'data-inventory-kind="hop"')
        self.assertContains(response, 'data-sortable-table')
        self.assertContains(response, 'data-sort-types="number,text')
        self.assertContains(response, "recipe-sort:")
        self.assertContains(response, "window.localStorage.setItem")
        self.assertContains(response, 'quantityCell.addEventListener("dblclick"')
        self.assertContains(response, 'input.form?.requestSubmit()')
        self.assertContains(response, "recipe-scroll:")
        self.assertContains(response, "window.scrollTo(0, Number(savedScroll))")
        self.assertNotContains(response, 'id="add-malt"')
        self.assertNotContains(response, 'id="add-hop"')
        self.assertContains(response, 'id="inventory-add-modal"')

    def test_ingredient_can_be_edited_and_deleted(self):
        recipe = Recipe.objects.create(name="Porter")
        catalog = IngredientCatalog.objects.create(name="Pale malt bio", kind=IngredientCatalog.Kind.MALT)
        ingredient = Ingredient.objects.create(
            recipe=recipe,
            catalog=catalog,
            name=catalog.name,
            kind=Ingredient.Kind.MALT,
            amount_g=1000,
        )
        response = self.client.post(
            f"/ingredients/{ingredient.pk}/modifier/",
            {"catalog": catalog.pk, "amount_g": "1200", "addition": "Brassage"},
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
            {"name": "", "amount_g": "", "potential_yield": ""},
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

    def test_catalog_name_change_is_propagated_to_recipe_ingredients(self):
        item = IngredientCatalog.objects.create(
            name="Cascade",
            kind=IngredientCatalog.Kind.HOP,
            alpha_acid=5,
        )
        recipe = Recipe.objects.create(name="IPA liée au catalogue")
        ingredient = Ingredient.objects.create(
            recipe=recipe,
            catalog=item,
            name="Cascade",
            kind=Ingredient.Kind.HOP,
            amount_g=50,
        )
        unrelated_ingredient = Ingredient.objects.create(
            recipe=recipe,
            name="Nom indépendant",
            kind=Ingredient.Kind.HOP,
            amount_g=25,
        )

        response = self.client.post(
            f"/catalogue/{item.pk}/modifier/",
            {
                "name": "Cascade US",
                "kind": "hop",
                "manufacturer": "",
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
        self.assertEqual(Ingredient.objects.filter(catalog_id=item.pk).count(), 1)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.name, "Cascade US")
        unrelated_ingredient.refresh_from_db()
        self.assertEqual(unrelated_ingredient.name, "Nom indépendant")

    def test_beerxml_export_and_import(self):
        recipe = Recipe.objects.create(
            name="Export Ale",
            batch_size_l=20,
            efficiency=75,
            target_og=1.050,
            target_ibu=30,
            target_carbonation=3.1,
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
        self.assertEqual(imported.target_carbonation, Decimal("3.10"))
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
        self.assertRedirects(response, "/recettes/")
        self.assertEqual(Recipe.objects.filter(name__in=["One", "Two"]).count(), 2)

    def test_backup_can_be_downloaded_and_restored(self):
        catalog = IngredientCatalog.objects.create(
            name="Pale malt",
            kind=IngredientCatalog.Kind.MALT,
            quantity_available=5000,
        )
        recipe = Recipe.objects.create(
            name="Sauvegarde Ale",
            tasting_malt=3,
            tasting_hops=5,
            tasting_notes="Notes d’agrumes.",
        )
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

        self.assertRedirects(restore_response, "/recettes/")
        restored = Recipe.objects.get()
        self.assertEqual(restored.name, "Sauvegarde Ale")
        self.assertEqual(restored.tasting_malt, 3)
        self.assertEqual(restored.tasting_hops, 5)
        self.assertEqual(restored.tasting_notes, "Notes d’agrumes.")
        self.assertEqual(restored.ingredients.get().catalog.name, "Pale malt")
        self.assertFalse(Recipe.objects.filter(name="Données à remplacer").exists())

    def test_backup_accepts_legacy_bbrew_format(self):
        validate_backup({"format": "BBrew backup", "version": 2, "records": []})

    def test_backup_restores_shopping_item_source_brews(self):
        recipe = Recipe.objects.create(name="Brassin sauvegardé")
        brew = Brew.objects.create(recipe=recipe, recipe_name=recipe.name)
        item = ShoppingItem.objects.create(name="Malt sauvegardé")
        item.source_brews.add(brew)

        backup_response = self.client.get("/parametres/sauvegarde.json")
        item.delete()
        brew.delete()
        recipe.delete()

        restore_response = self.client.post(
            "/parametres/restaurer/",
            {"file": SimpleUploadedFile("bbrew.json", backup_response.content, content_type="application/json")},
        )

        self.assertRedirects(restore_response, "/recettes/")
        restored_item = ShoppingItem.objects.get(name="Malt sauvegardé")
        self.assertEqual(list(restored_item.source_brews.values_list("recipe_name", flat=True)), ["Brassin sauvegardé"])

    def test_brew_capsules_can_be_consumed_and_rolled_back(self):
        capsules = IngredientCatalog.objects.create(
            name="Capsules noires",
            kind=IngredientCatalog.Kind.CONSUMABLE,
            quantity_available=100,
        )
        brew = Brew.objects.create(
            recipe_name="Capsule Ale",
        )

        response = self.client.post(
            f"/brassins/{brew.pk}/mise-en-bouteille/",
            {
                "bottled_bottle_count": "10",
                "capsule_catalog": capsules.pk,
                "completed_date": "2026-10-20",
            },
        )
        self.assertRedirects(response, f"/brassins/{brew.pk}/")
        brew.refresh_from_db()
        self.assertEqual(brew.completed_date, date(2026, 10, 20))

        response = self.client.post(f"/brassins/{brew.pk}/consommer-capsules/")

        self.assertRedirects(response, f"/brassins/{brew.pk}/")
        capsules.refresh_from_db()
        brew.refresh_from_db()
        self.assertEqual(capsules.quantity_available, 90)
        self.assertEqual(brew.capsules_consumed, 10)
        self.assertIsNotNone(brew.capsules_consumed_at)

        response = self.client.post(f"/brassins/{brew.pk}/annuler-consommation-capsules/")

        self.assertRedirects(response, f"/brassins/{brew.pk}/")
        capsules.refresh_from_db()
        brew.refresh_from_db()
        self.assertEqual(capsules.quantity_available, 100)
        self.assertEqual(brew.capsules_consumed, 0)
        self.assertIsNone(brew.capsules_consumed_at)

    def test_brew_capsules_cannot_make_stock_negative(self):
        capsules = IngredientCatalog.objects.create(
            name="Capsules rouges",
            kind=IngredientCatalog.Kind.CONSUMABLE,
            quantity_available=5,
        )
        brew = Brew.objects.create(
            recipe_name="Stock Ale",
            bottled_bottle_count=10,
            capsule_catalog=capsules,
        )

        response = self.client.post(f"/brassins/{brew.pk}/consommer-capsules/")

        self.assertRedirects(response, f"/brassins/{brew.pk}/")
        capsules.refresh_from_db()
        self.assertEqual(capsules.quantity_available, 5)

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
        brews_response = self.client.get("/brassins/")
        self.assertNotContains(brews_response, "Ajouter un brassin")
        self.assertEqual(brew.recipe_name, "Bière de test")
        self.assertIsNotNone(brew.recipe_version)
        self.assertIn("V1", brew.recipe_version_label)
        form_response = self.client.get("/brassins/ajouter/")
        self.assertContains(form_response, "Version initiale")
        self.assertEqual(form_response.context["latest_versions"][recipe.pk], brew.recipe_version.pk)
        edit_response = self.client.get(f"/brassins/{brew.pk}/modifier/")
        self.assertContains(edit_response, 'value="2026-10-10"')

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
        EquipmentSettings.objects.create(bag_weight_g=1200)
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
        self.assertContains(response, "Liste de courses")
        self.assertContains(response, "À intégrer au stock")
        response = self.client.post("/courses/ajouter/", {"name": "Capsules rouges"})
        self.assertRedirects(response, "/courses/")
        item = ShoppingItem.objects.get()
        self.assertFalse(item.is_ordered)

        response = self.client.post(f"/courses/{item.pk}/cocher/")
        self.assertRedirects(response, "/courses/")
        item.refresh_from_db()
        self.assertTrue(item.is_ordered)

        response = self.client.get("/courses/")
        self.assertNotContains(response, ">Tous</a>")
        self.assertNotContains(response, "text-decoration-line-through")
        self.assertContains(response, "Capsules rouges")

        response = self.client.post(f"/courses/{item.pk}/supprimer/")
        self.assertRedirects(response, "/courses/")
        self.assertFalse(ShoppingItem.objects.filter(pk=item.pk).exists())

    def test_shopping_receive_offers_kind_specific_quantity_presets(self):
        pilsen = IngredientCatalog.objects.create(name="Pilsen", kind=IngredientCatalog.Kind.MALT)
        IngredientCatalog.objects.create(name="Cascade", kind=IngredientCatalog.Kind.HOP)
        IngredientCatalog.objects.create(name="US-05", kind=IngredientCatalog.Kind.YEAST)
        IngredientCatalog.objects.create(
            name="Malt Cara Gold",
            kind=IngredientCatalog.Kind.MALT,
            unit_cost=Decimal("3.9900"),
        )
        item = ShoppingItem.objects.create(name="Pilsen", is_ordered=True, received_quantity=5000)

        response = self.client.get("/courses/")

        self.assertContains(response, '"5000", "5000 g"')
        self.assertContains(response, '"250", "250 g"')
        self.assertContains(response, "Nombre de paquets")
        self.assertContains(response, f'name="catalog_id" value="{pilsen.pk}"')
        self.assertContains(response, 'id="receive-modal-')
        self.assertContains(response, 'name="total_price"')
        self.assertContains(response, "data-bs-toggle=\"modal\"")
        self.assertContains(response, "data-unit-cost-preview")
        stock_response = self.client.get("/catalogue/")
        self.assertContains(stock_response, "3,99 €/kg")
        self.assertNotContains(stock_response, "3,9900")
        item.delete()

    def test_shopping_item_can_be_marked_received_before_stock_integration(self):
        item = ShoppingItem.objects.create(
            name="Malt Pilsen",
            is_ordered=True,
            planned_quantity=5000,
            unit="g",
        )

        response = self.client.post(
            f"/courses/{item.pk}/receptionner-commande/",
        )

        self.assertRedirects(response, "/courses/")
        item.refresh_from_db()
        self.assertTrue(item.is_received)
        self.assertIsNone(item.received_quantity)
        response = self.client.get("/courses/")
        self.assertContains(response, "À intégrer au stock")
        self.assertContains(response, "Malt Pilsen")
        self.assertContains(response, "Nouvelle fiche de stock")

    def test_shopping_list_can_be_cleared(self):
        ShoppingItem.objects.create(name="Malt")
        ShoppingItem.objects.create(name="Houblon")
        ordered_item = ShoppingItem.objects.create(name="Commande en cours", is_ordered=True)

        response = self.client.post("/courses/vider/")

        self.assertRedirects(response, "/courses/")
        self.assertFalse(ShoppingItem.objects.filter(is_ordered=False).exists())
        self.assertTrue(ShoppingItem.objects.filter(pk=ordered_item.pk).exists())

    def test_shopping_item_can_be_received_into_catalog_stock(self):
        catalog = IngredientCatalog.objects.create(
            name="Malt Pilsen",
            kind=IngredientCatalog.Kind.MALT,
            quantity_available=1000,
        )
        item = ShoppingItem.objects.create(name="Malt Pilsen", planned_quantity=5000, unit="g")
        item.is_ordered = True
        item.save(update_fields=["is_ordered"])

        response = self.client.post(
            f"/courses/{item.pk}/receptionner/",
            {"quantity": "4000", "total_price": "8.00"},
        )

        self.assertRedirects(response, "/courses/")
        catalog.refresh_from_db()
        self.assertEqual(catalog.quantity_available, 5000)
        self.assertEqual(catalog.unit_cost, Decimal("2.0000"))
        self.assertFalse(ShoppingItem.objects.filter(pk=item.pk).exists())

    def test_shopping_item_receipt_calculates_cost_per_catalog_unit(self):
        cases = [
            (IngredientCatalog.Kind.MALT, 5000, "10.00", Decimal("2.0000")),
            (IngredientCatalog.Kind.HOP, 100, "5.00", Decimal("0.0500")),
            (IngredientCatalog.Kind.YEAST, 2, "12.00", Decimal("6.0000")),
            (IngredientCatalog.Kind.OTHER, 4, "8.00", Decimal("2.0000")),
            (IngredientCatalog.Kind.CONSUMABLE, 10, "15.00", Decimal("1.5000")),
        ]
        for kind, quantity, total_price, expected_unit_cost in cases:
            with self.subTest(kind=kind):
                item = ShoppingItem.objects.create(name=f"Article {kind}", is_ordered=True)
                response = self.client.post(
                    f"/courses/{item.pk}/receptionner/",
                    {
                        "catalog_id": "new",
                        "new_kind": kind,
                        "quantity": str(quantity),
                        "total_price": total_price,
                    },
                )

                self.assertRedirects(response, "/courses/")
                catalog = IngredientCatalog.objects.get(name=f"Article {kind}")
                self.assertEqual(catalog.quantity_available, quantity)
                self.assertEqual(catalog.unit_cost, expected_unit_cost)
                stock_events = ActivityEvent.objects.filter(
                    model_name="fiche de stock",
                    object_id=str(catalog.pk),
                )
                self.assertEqual(stock_events.count(), 1)
                self.assertEqual(
                    stock_events.get().event_type,
                    ActivityEvent.EventType.CREATE,
                )

    def test_receiving_without_price_preserves_existing_catalog_unit_cost(self):
        catalog = IngredientCatalog.objects.create(
            name="Malt Pilsen",
            kind=IngredientCatalog.Kind.MALT,
            quantity_available=1000,
            unit_cost=Decimal("2.5000"),
        )
        item = ShoppingItem.objects.create(name="Malt Pilsen", is_ordered=True)

        self.client.post(
            f"/courses/{item.pk}/receptionner/",
            {"catalog_id": catalog.pk, "quantity": "2000"},
        )

        catalog.refresh_from_db()
        self.assertEqual(catalog.quantity_available, 3000)
        self.assertEqual(catalog.unit_cost, Decimal("2.5000"))

    def test_shopping_item_receive_rolls_back_stock_when_deletion_fails(self):
        catalog = IngredientCatalog.objects.create(
            name="Malt Pilsen",
            kind=IngredientCatalog.Kind.MALT,
            quantity_available=1000,
        )
        item = ShoppingItem.objects.create(name="Malt Pilsen", is_ordered=True)

        with patch("recipes.views.ShoppingItem.delete", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    f"/courses/{item.pk}/receptionner/",
                    {"catalog_id": catalog.pk, "quantity": "4000"},
                )

        catalog.refresh_from_db()
        self.assertEqual(catalog.quantity_available, 1000)
        self.assertTrue(ShoppingItem.objects.filter(pk=item.pk).exists())

    def test_shopping_item_can_create_missing_catalog_when_received(self):
        item = ShoppingItem.objects.create(name="Houblon Nelson", planned_quantity=100, unit="g")
        item.is_ordered = True
        item.save(update_fields=["is_ordered"])

        response = self.client.post(
            f"/courses/{item.pk}/receptionner/",
            {"catalog_id": "new", "new_kind": IngredientCatalog.Kind.HOP, "quantity": "100"},
        )

        self.assertRedirects(response, "/courses/")
        catalog = IngredientCatalog.objects.get(name="Houblon Nelson")
        self.assertEqual(catalog.kind, IngredientCatalog.Kind.HOP)
        self.assertEqual(catalog.quantity_available, 100)
        self.assertFalse(ShoppingItem.objects.filter(pk=item.pk).exists())

    def test_shopping_item_cannot_be_received_before_being_ordered(self):
        catalog = IngredientCatalog.objects.create(
            name="Malt Pilsen",
            kind=IngredientCatalog.Kind.MALT,
            quantity_available=1000,
        )
        item = ShoppingItem.objects.create(name="Malt Pilsen", planned_quantity=5000)

        response = self.client.post(
            f"/courses/{item.pk}/receptionner/",
            {"catalog_id": catalog.pk, "quantity": "5000"},
        )

        self.assertRedirects(response, "/courses/")
        catalog.refresh_from_db()
        self.assertEqual(catalog.quantity_available, 1000)
        self.assertTrue(ShoppingItem.objects.filter(pk=item.pk).exists())

    def test_received_shopping_items_can_be_cleared(self):
        ShoppingItem.objects.create(name="Reçu", is_ordered=True)
        ShoppingItem.objects.create(name="À acheter", is_ordered=False)

        response = self.client.post("/courses/vider-recus/")

        self.assertRedirects(response, "/courses/")
        self.assertFalse(ShoppingItem.objects.filter(name="Reçu").exists())
        self.assertTrue(ShoppingItem.objects.filter(name="À acheter").exists())

    def test_catalog_quantity_can_be_added_without_editing_item(self):
        item = IngredientCatalog.objects.create(
            name="Pilsen",
            kind=IngredientCatalog.Kind.MALT,
            quantity_available=1000,
        )

        response = self.client.post(
            f"/catalogue/{item.pk}/ajouter-quantite/",
            {"quantity": "500"},
        )

        self.assertRedirects(response, "/catalogue/")
        item.refresh_from_db()
        self.assertEqual(item.quantity_available, 1500)

        response = self.client.post(
            f"/catalogue/{item.pk}/ajouter-quantite/",
            {"quantity": "-200"},
        )

        self.assertRedirects(response, "/catalogue/")
        item.refresh_from_db()
        self.assertEqual(item.quantity_available, 1300)

    def test_consumable_catalog_item_can_be_created(self):
        response = self.client.post(
            "/catalogue/ajouter/",
            {
                "kind": IngredientCatalog.Kind.CONSUMABLE,
                "name": "Capsules 26 mm",
                "form": "Capsules",
                "quantity_available": "100",
            },
        )

        self.assertRedirects(response, "/catalogue/")
        item = IngredientCatalog.objects.get(name="Capsules 26 mm")
        self.assertEqual(item.kind, IngredientCatalog.Kind.CONSUMABLE)
        self.assertEqual(item.quantity_available, 100)

    def test_consumable_catalog_forms_only_expose_name_and_quantity(self):
        self.assertEqual(
            set(CatalogForm(instance=IngredientCatalog(kind=IngredientCatalog.Kind.CONSUMABLE)).fields),
            {"name", "quantity_available", "unit_cost"},
        )

    def test_missing_stock_can_add_selected_items_without_duplicates(self):
        brew = Brew.objects.create(recipe_name="Brassin test")
        ShoppingItem.objects.create(name="Houblon déjà prévu")

        response = self.client.post(
            f"/brassins/{brew.pk}/stock-manquant-courses/",
            {"names": ["Houblon déjà prévu", "Levure nouvelle", "Levure nouvelle"]},
        )

        self.assertRedirects(response, "/brassins/")
        self.assertEqual(
            set(ShoppingItem.objects.values_list("name", flat=True)),
            {"Houblon déjà prévu", "Levure nouvelle"},
        )

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

    def test_brew_stock_consumption_rejects_insufficient_stock(self):
        catalog = IngredientCatalog.objects.create(
            name="Pale malt",
            kind=IngredientCatalog.Kind.MALT,
            quantity_available=1000,
        )
        recipe = Recipe.objects.create(name="Brassin stock insuffisant")
        Ingredient.objects.create(
            recipe=recipe,
            catalog=catalog,
            name="Pale malt",
            kind=Ingredient.Kind.MALT,
            amount_g=2500,
        )
        self.client.post(f"/recettes/{recipe.pk}/versions/ajouter/", {"reason": "Version de brassage"})
        self.client.post(
            "/brassins/ajouter/",
            {"recipe": recipe.pk, "status": "planned", "planned_date": ""},
        )
        brew = Brew.objects.get()

        response = self.client.post(
            f"/brassins/{brew.pk}/consommer-stock/",
            {"stock_item": f"{catalog.pk}:{Ingredient.Kind.MALT}"},
            follow=True,
        )

        self.assertRedirects(response, f"/brassins/{brew.pk}/")
        catalog.refresh_from_db()
        brew.refresh_from_db()
        self.assertEqual(catalog.quantity_available, 1000)
        self.assertEqual(brew.stock_consumed_items, [])
        self.assertIsNone(brew.stock_consumed_at)
        self.assertContains(response, "Stock insuffisant")

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
        spice = Ingredient.objects.create(
            recipe=recipe,
            name="Coriandre",
            kind=Ingredient.Kind.OTHER,
            amount_g=5,
            addition="Ébullition",
            boil_minutes=60,
        )

        response = self.client.get(f"/recettes/{recipe.pk}/")

        events = response.context["boil_events"]
        self.assertContains(response, ".boil-event { position: relative; z-index: 1; display: flex; flex: 0 1 10rem;")
        self.assertContains(response, ".boil-event:not(:last-child)::after { content: \"→\"; position: absolute; top: 50%;")
        self.assertContains(response, "font-weight: 700;")
        self.assertContains(response, "transform: translateY(-50%);")
        self.assertContains(response, ".boil-event-start, .boil-event-cool { background: rgba(220, 53, 69, .06); }")
        self.assertContains(response, 'class="boil-event boil-event-start"')
        self.assertContains(response, 'class="boil-event boil-event-timer"')
        self.assertEqual(
            [event["type"] for event in events],
            ["start", "addition", "timer", "addition", "timer", "cool"],
        )
        self.assertEqual(events[2]["minutes"], 55)
        self.assertEqual(events[4]["minutes"], 5)
        self.assertEqual(
            [row["ingredient"] for row in events[1]["rows"]],
            [early_hop, same_time_hop, spice],
        )
        self.assertEqual(events[3]["rows"][0]["ingredient"], late_hop)
        self.assertContains(response, 'class="boil-event boil-event-hop"')
        self.assertContains(response, "Second early hop")

    def test_cooling_hops_are_ordered_from_highest_to_lowest_temperature(self):
        recipe = Recipe.objects.create(name="Cooling hop order")
        cold_hop = Ingredient.objects.create(
            recipe=recipe,
            name="Cold hop",
            kind=Ingredient.Kind.HOP,
            amount_g=10,
            addition="Refroidissement",
            addition_temperature_c=70,
        )
        hot_hop = Ingredient.objects.create(
            recipe=recipe,
            name="Hot hop",
            kind=Ingredient.Kind.HOP,
            amount_g=10,
            addition="Refroidissement",
            addition_temperature_c=80,
        )
        same_temperature_hop = Ingredient.objects.create(
            recipe=recipe,
            name="Another hot hop",
            kind=Ingredient.Kind.HOP,
            amount_g=5,
            addition="Refroidissement",
            addition_temperature_c=80,
        )

        response = self.client.get(f"/recettes/{recipe.pk}/")

        cooling_events = [
            event for event in response.context["boil_events"]
            if event["type"] == "cooling_hop"
        ]
        self.assertEqual(len(cooling_events), 2)
        self.assertEqual(cooling_events[0]["temperature"], 80)
        self.assertEqual(
            [row["ingredient"] for row in cooling_events[0]["rows"]],
            [hot_hop, same_temperature_hop],
        )
        self.assertEqual(cooling_events[1]["rows"][0]["ingredient"], cold_hop)
        self.assertContains(response, "Another hot hop")

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
        detail_response = self.client.get(f"/recettes/{recipe.pk}/")
        self.assertContains(detail_response, 'title="Double-cliquez pour modifier">20 L</strong>')
        self.assertContains(detail_response, 'name="batch_size_l"')

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
        self.assertNotIn("form", MaltForm().fields)
        self.assertNotIn("form", HopForm().fields)
        self.assertNotIn("form", YeastForm().fields)
        self.assertNotIn("form", OtherForm().fields)
        self.assertEqual(MaltForm().fields["addition"].label, "Ajout")
        self.assertEqual(HopForm().fields["addition"].label, "Ajout")
        self.assertEqual(OtherForm().fields["addition"].label, "Ajout")
        self.assertEqual(OtherForm().fields["amount_g"].label, "Quantité")
        self.assertEqual(OtherForm().fields["boil_minutes"].label, "Minutes avant fin d’ébullition")
        self.assertIn("boil_minutes", OtherForm().fields)
        self.assertNotIn("manufacturer", OtherForm().fields)
        self.assertEqual(CatalogYeastForm().fields["manufacturer"].label, "Laboratoire")
        self.assertIn("fermentation_temperature_min_c", CatalogYeastForm().fields)
        self.assertIn("fermentation_temperature_max_c", CatalogYeastForm().fields)
        self.assertNotIn(
            "fermentation_temperature_min_c",
            CatalogForm(instance=IngredientCatalog(kind=IngredientCatalog.Kind.MALT)).fields,
        )
        self.assertNotIn("manufacturer", CatalogOtherForm().fields)
        self.assertEqual(list(MaltForm().fields["addition"].choices)[1:], MALT_ADDITION_CHOICES)
        self.assertEqual(list(HopForm().fields["addition"].choices)[1:], ADDITION_CHOICES)

    def test_yeast_catalog_form_saves_a_valid_fermentation_temperature_range(self):
        response = self.client.post(
            "/catalogue/ajouter/",
            {
                "kind": IngredientCatalog.Kind.YEAST,
                "name": "Levure température",
                "manufacturer": "Laboratoire",
                "product_id": "",
                "form": "Sèche",
                "quantity_available": "2",
                "attenuation": "78",
                "fermentation_temperature_min_c": "17",
                "fermentation_temperature_max_c": "21",
            },
        )

        self.assertRedirects(response, "/catalogue/")
        yeast = IngredientCatalog.objects.get(name="Levure température")
        self.assertEqual(yeast.fermentation_temperature_min_c, Decimal("17.0"))
        self.assertEqual(yeast.fermentation_temperature_max_c, Decimal("21.0"))
        self.assertContains(self.client.get("/catalogue/"), "17–21 °C")

    def test_yeast_catalog_form_rejects_inverted_fermentation_range(self):
        form = CatalogYeastForm(
            data={
                "name": "Levure invalide",
                "manufacturer": "",
                "product_id": "",
                "form": "",
                "quantity_available": "1",
                "attenuation": "78",
                "fermentation_temperature_min_c": "22",
                "fermentation_temperature_max_c": "18",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("fermentation_temperature_max_c", form.errors)

    def test_yeast_catalog_form_requires_both_fermentation_temperature_bounds(self):
        form = CatalogYeastForm(
            data={
                "name": "Levure partielle",
                "manufacturer": "",
                "product_id": "",
                "form": "",
                "quantity_available": "1",
                "attenuation": "78",
                "fermentation_temperature_min_c": "18",
                "fermentation_temperature_max_c": "",
            }
        )

        self.assertFalse(form.is_valid())

    def test_ingredient_edit_form_only_exposes_quantity(self):
        recipe = Recipe.objects.create(name="Quantité")
        catalog = IngredientCatalog.objects.create(name="Pale malt", kind=IngredientCatalog.Kind.MALT)
        ingredient = Ingredient.objects.create(
            recipe=recipe,
            catalog=catalog,
            name=catalog.name,
            kind=Ingredient.Kind.MALT,
            amount_g=1000,
        )

        self.assertEqual(set(MaltForm(instance=ingredient).fields), {"amount_g"})

    def test_biab_mash_steps_can_be_created_edited_and_deleted(self):
        recipe = Recipe.objects.create(name="BIAB Pale Ale")
        response = self.client.post(
            f"/recettes/{recipe.pk}/brassage/ajouter/",
            {"name": "Palier principal", "temperature_c": "65", "duration_min": "60"},
        )
        step = MashStep.objects.get(recipe=recipe)
        self.assertEqual(step.position, 1)
        self.assertRedirects(response, f"/recettes/{recipe.pk}/brassage/")
        detail_response = self.client.get(f"/recettes/{recipe.pk}/")
        self.assertContains(detail_response, "Paliers de brassage BIAB")
        self.assertNotContains(detail_response, "<th>Palier</th>")
        self.assertContains(detail_response, "Palier principal")
        self.assertNotContains(detail_response, f'href="/paliers/{step.pk}/modifier/"')

        response = self.client.post(
            f"/paliers/{step.pk}/modifier/",
            {"name": "Palier saccharification", "temperature_c": "67", "duration_min": "60"},
        )
        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        step.refresh_from_db()
        self.assertEqual(step.temperature_c, 67)

        response = self.client.post(f"/paliers/{step.pk}/supprimer/")
        self.assertRedirects(response, f"/recettes/{recipe.pk}/brassage/")
        self.assertFalse(MashStep.objects.filter(pk=step.pk).exists())

    def test_mash_profile_updates_step_temperatures(self):
        recipe = Recipe.objects.create(name="Profil interactif")
        first = MashStep.objects.create(recipe=recipe, position=1, name="Palier 1", temperature_c=63, duration_min=30)
        second = MashStep.objects.create(recipe=recipe, position=2, name="Palier 2", temperature_c=68, duration_min=30)

        response = self.client.post(
            f"/recettes/{recipe.pk}/brassage/profil/",
            {
                f"temperature_{first.pk}": "64.5",
                f"duration_{first.pk}": "40",
                f"temperature_{second.pk}": "70",
                f"duration_{second.pk}": "25",
            },
        )

        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.temperature_c, 64.5)
        self.assertEqual(second.temperature_c, 70)
        self.assertEqual(first.duration_min, 40)
        self.assertEqual(second.duration_min, 25)

    def test_mash_graph_update_can_add_edit_and_delete_steps(self):
        recipe = Recipe.objects.create(name="Profil graphique")
        first = MashStep.objects.create(recipe=recipe, position=1, name="Palier 1", temperature_c=63, duration_min=30)
        second = MashStep.objects.create(recipe=recipe, position=2, name="Palier 2", temperature_c=68, duration_min=30)

        detail_response = self.client.get(f"/recettes/{recipe.pk}/")
        self.assertContains(detail_response, "déplacez le début d’un palier")
        self.assertContains(detail_response, "const point = { x: elapsed, y: step.temperature")
        self.assertContains(detail_response, "steps[stepIndex - 1].duration = clampDuration")
        self.assertContains(detail_response, "endpoint: true")
        self.assertContains(detail_response, "step.duration = clampDuration(requestedElapsed - previousElapsed, timeMax - previousElapsed)")
        self.assertContains(detail_response, "if (draggedMashEndpoint)")
        self.assertContains(detail_response, "if (!draggedMashEndpoint && stepIndex > 0)")

        response = self.client.post(
            f"/recettes/{recipe.pk}/brassage/graphique/",
            {
                "step_id": [str(first.pk), "new-1"],
                "step_name": ["Palier modifié", "Palier ajouté"],
                "step_temperature": ["64", "72"],
                "step_duration": ["40", "20"],
            },
        )

        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        first.refresh_from_db()
        self.assertEqual(first.name, "Palier modifié")
        self.assertEqual(first.temperature_c, 64)
        self.assertEqual(first.duration_min, 40)
        self.assertFalse(MashStep.objects.filter(pk=second.pk).exists())
        self.assertEqual(MashStep.objects.filter(recipe=recipe).count(), 2)
        self.assertEqual(
            list(MashStep.objects.filter(recipe=recipe).order_by("position").values_list("name", flat=True)),
            ["Palier modifié", "Palier ajouté"],
        )

    def test_mash_graph_settings_can_be_updated(self):
        recipe = Recipe.objects.create(name="Réglages du profil")

        response = self.client.post(
            f"/recettes/{recipe.pk}/brassage/graphique-parametres/",
            {
                "mash_time_min": "0",
                "mash_time_max": "240",
                "mash_temperature_min": "50",
                "mash_temperature_max": "75",
                "mash_time_grid": "10",
                "mash_temperature_grid": "2",
            },
        )

        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        self.assertEqual(recipe.mash_time_max, 240)
        self.assertEqual(recipe.mash_temperature_min, 50)
        self.assertEqual(recipe.mash_time_grid, 10)

    def test_mash_zone_selection_is_persisted(self):
        recipe = Recipe.objects.create(name="Zones persistantes")

        response = self.client.post(
            f"/recettes/{recipe.pk}/brassage/zones/",
            {"zones": ["protease", "mashout"]},
        )

        self.assertRedirects(response, f"/recettes/{recipe.pk}/")
        recipe.refresh_from_db()
        self.assertEqual(recipe.mash_zones, ["protease", "mashout"])

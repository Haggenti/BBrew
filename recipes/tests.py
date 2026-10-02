from django.test import TestCase

from .calculations import abv_from_gravity, gravity_points
from .models import Recipe


class CalculationTests(TestCase):
    def test_abv_from_gravity(self):
        self.assertEqual(abv_from_gravity(1.050, 1.010), 5.25)

    def test_gravity_points_are_positive(self):
        self.assertGreater(gravity_points(5, 37, 20, 75), 0)


class RecipeWorkflowTests(TestCase):
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

"""Import et export BeerXML sans dépendance à Django."""

from xml.etree import ElementTree


def _value(node, name, default=""):
    child = node.find(name)
    return child.text.strip() if child is not None and child.text else default


def export_recipe(recipe) -> bytes:
    root = ElementTree.Element("RECIPES")
    recipe_node = ElementTree.SubElement(root, "RECIPE")
    values = {
        "NAME": recipe.name,
        "BATCH_SIZE": recipe.batch_size_l,
        "EFFICIENCY": recipe.efficiency,
        "OG": recipe.target_og,
        "IBU": recipe.target_ibu,
        "BOIL_TIME": recipe.boil_time_min,
    }
    for name, value in values.items():
        ElementTree.SubElement(recipe_node, name).text = str(value)

    sections = {
        "FERMENTABLES": recipe.ingredients.filter(kind="malt"),
        "HOPS": recipe.ingredients.filter(kind="hop"),
        "YEASTS": recipe.ingredients.filter(kind="yeast"),
    }
    for section_name, ingredients in sections.items():
        section = ElementTree.SubElement(recipe_node, section_name)
        item_name = section_name[:-1]
        for ingredient in ingredients:
            item = ElementTree.SubElement(section, item_name)
            ElementTree.SubElement(item, "NAME").text = ingredient.name
            ElementTree.SubElement(item, "AMOUNT").text = str(float(ingredient.amount_g) / 1000)
            if item_name == "FERMENTABLE":
                ElementTree.SubElement(item, "COLOR").text = str(ingredient.color_ebc)
                ElementTree.SubElement(item, "YIELD").text = str(ingredient.potential_yield)
            elif item_name == "HOP":
                ElementTree.SubElement(item, "ALPHA").text = str(ingredient.alpha_acid)
                ElementTree.SubElement(item, "TIME").text = str(ingredient.boil_minutes)
                ElementTree.SubElement(item, "FORM").text = ingredient.form
            else:
                ElementTree.SubElement(item, "ATTENUATION").text = str(ingredient.attenuation)

    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def import_recipe(payload: bytes) -> dict:
    root = ElementTree.fromstring(payload)
    recipe_node = root.find(".//RECIPE")
    if recipe_node is None:
        raise ValueError("Le fichier BeerXML ne contient aucune recette.")

    recipe = {
        "name": _value(recipe_node, "NAME", "Recette importée"),
        "batch_size_l": float(_value(recipe_node, "BATCH_SIZE", "20")),
        "efficiency": float(_value(recipe_node, "EFFICIENCY", "75")),
        "target_og": float(_value(recipe_node, "OG", "1.050")),
        "target_ibu": float(_value(recipe_node, "IBU", "25")),
        "boil_time_min": int(float(_value(recipe_node, "BOIL_TIME", "60"))),
        "ingredients": [],
    }
    for node in recipe_node.findall("./FERMENTABLES/FERMENTABLE"):
        recipe["ingredients"].append(
            {
                "kind": "malt",
                "name": _value(node, "NAME", "Malt importé"),
                "amount_g": float(_value(node, "AMOUNT", "0")) * 1000,
                "color_ebc": float(_value(node, "COLOR", "0")),
                "potential_yield": float(_value(node, "YIELD", "80")),
            }
        )
    for node in recipe_node.findall("./HOPS/HOP"):
        recipe["ingredients"].append(
            {
                "kind": "hop",
                "name": _value(node, "NAME", "Houblon importé"),
                "amount_g": float(_value(node, "AMOUNT", "0")) * 1000,
                "alpha_acid": float(_value(node, "ALPHA", "5")),
                "boil_minutes": int(float(_value(node, "TIME", "60"))),
                "form": _value(node, "FORM", ""),
            }
        )
    for node in recipe_node.findall("./YEASTS/YEAST"):
        recipe["ingredients"].append(
            {
                "kind": "yeast",
                "name": _value(node, "NAME", "Levure importée"),
                "amount_g": float(_value(node, "AMOUNT", "0")) * 1000,
                "attenuation": float(_value(node, "ATTENUATION", "78")),
            }
        )
    return recipe

"""Import et export BeerXML sans dépendance à Django."""

from xml.etree import ElementTree


def _value(node, name, default=""):
    child = node.find(name)
    return child.text.strip() if child is not None and child.text else default


def _first_value(node, names, default=""):
    for name in names:
        value = _value(node, name, "")
        if value != "":
            return value
    return default


def _yeast_form(value):
    normalized = value.strip().lower()
    return {
        "dry": "Sèche",
        "sèche": "Sèche",
        "liquid": "Liquide",
        "liquide": "Liquide",
        "paste": "Pâte",
        "pâte": "Pâte",
    }.get(normalized, value)


def _malt_form(value):
    normalized = value.strip().lower()
    return {
        "grain": "Grains",
        "grains": "Grains",
        "flaked": "Flocons",
        "flakes": "Flocons",
        "flour": "Farine",
        "dry extract": "Extrait sec",
        "dry": "Extrait sec",
        "liquid extract": "Extrait liquide",
        "extract": "Extrait liquide",
        "sugar": "Sucre solide",
        "syrup": "Sirop",
    }.get(normalized, value)


def _hop_form(value):
    normalized = value.strip().lower()
    return {
        "pellet": "Pellets",
        "pellets": "Pellets",
        "cone": "Cônes",
        "cones": "Cônes",
        "cône": "Cônes",
        "cônes": "Cônes",
        "flower": "Fleurs",
        "flowers": "Fleurs",
        "fleur": "Fleurs",
        "fleurs": "Fleurs",
        "cryo": "Cryo",
    }.get(normalized, value)


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
        "MISCS": recipe.ingredients.filter(kind="other"),
    }
    for section_name, ingredients in sections.items():
        section = ElementTree.SubElement(recipe_node, section_name)
        item_name = section_name[:-1]
        for ingredient in ingredients:
            item = ElementTree.SubElement(section, item_name)
            ElementTree.SubElement(item, "NAME").text = ingredient.name
            ElementTree.SubElement(item, "AMOUNT").text = str(float(ingredient.amount_g) / 1000)
            if item_name == "FERMENTABLE":
                ElementTree.SubElement(item, "FORM").text = ingredient.form
                ElementTree.SubElement(item, "COLOR").text = str(ingredient.color_ebc)
                ElementTree.SubElement(item, "YIELD").text = str(ingredient.potential_yield)
            elif item_name == "HOP":
                ElementTree.SubElement(item, "ALPHA").text = str(ingredient.alpha_acid)
                ElementTree.SubElement(item, "TIME").text = str(ingredient.boil_minutes)
                ElementTree.SubElement(item, "FORM").text = ingredient.form
                if ingredient.addition_temperature_c is not None:
                    ElementTree.SubElement(item, "USE_TEMP").text = str(ingredient.addition_temperature_c)
            elif item_name == "YEAST":
                ElementTree.SubElement(item, "FORM").text = ingredient.form
                ElementTree.SubElement(item, "PRODUCT_ID").text = ingredient.product_id
                ElementTree.SubElement(item, "LABORATORY").text = ingredient.manufacturer
                ElementTree.SubElement(item, "ATTENUATION").text = str(ingredient.attenuation)
                ElementTree.SubElement(item, "ADD_TO_BOTTLE").text = "TRUE" if ingredient.for_bottling else "FALSE"
            elif item_name == "MISC":
                ElementTree.SubElement(item, "USE").text = ingredient.addition
                ElementTree.SubElement(item, "TYPE").text = ingredient.form
                ElementTree.SubElement(item, "NOTES").text = ingredient.notes

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
        "mash_steps": [],
        "fermentation_steps": [],
    }
    style_node = recipe_node.find("./STYLE")
    if style_node is not None:
        recipe["category_code"] = _value(style_node, "CATEGORY_NUMBER", "")
        recipe["category_name"] = _value(style_node, "NAME", "")
    for node in recipe_node.findall("./FERMENTABLES/FERMENTABLE"):
        recipe["ingredients"].append(
            {
                "kind": "malt",
                "name": _value(node, "NAME", "Malt importé"),
                "amount_g": float(_value(node, "AMOUNT", "0")) * 1000,
                "form": _malt_form(_first_value(node, ("FORM", "TYPE"), "")),
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
                "form": _hop_form(_value(node, "FORM", "")),
                "addition_temperature_c": (
                    float(_value(node, "USE_TEMP", "0"))
                    if _value(node, "USE_TEMP", "") else None
                ),
            }
        )
    for node in recipe_node.findall("./YEASTS/YEAST"):
        yeast_name = _value(node, "NAME", "Levure importée")
        product_id = _value(node, "PRODUCT_ID", "")
        if product_id.strip() in {"-", "—"}:
            product_id = ""
        recipe["ingredients"].append(
            {
                "kind": "yeast",
                "name": f"{yeast_name} ({product_id})" if product_id else yeast_name,
                "amount_g": float(_value(node, "AMOUNT", "0")) * 1000,
                "form": _yeast_form(_value(node, "FORM", "")),
                "product_id": product_id,
                "manufacturer": _first_value(node, ("LABORATORY", "MANUFACTURER"), ""),
                "attenuation": float(_value(node, "ATTENUATION", "78")),
                "for_bottling": _value(node, "ADD_TO_BOTTLE", "FALSE").upper() in ("TRUE", "YES", "1"),
            }
        )
    for node in recipe_node.findall("./MISCS/MISC"):
        recipe["ingredients"].append(
            {
                "kind": "other",
                "name": _value(node, "NAME", "Ingrédient divers importé"),
                "amount_g": float(_value(node, "AMOUNT", "0")) * 1000,
                "form": _value(node, "TYPE", ""),
                "addition": _value(node, "USE", ""),
                "notes": _value(node, "NOTES", ""),
            }
        )
    for position, node in enumerate(recipe_node.findall("./MASH/MASH_STEPS/MASH_STEP"), start=1):
        recipe["mash_steps"].append(
            {
                "position": position,
                "name": _first_value(node, ("NAME", "TYPE"), f"Palier {position}"),
                "temperature_c": float(_first_value(node, ("STEP_TEMP", "TEMPERATURE"), "65")),
                "duration_min": int(float(_first_value(node, ("STEP_TIME", "DURATION"), "60"))),
            }
        )

    standard_fermentation_steps = recipe_node.findall(
        "./FERMENTATION_STEPS/FERMENTATION_STEP"
    )
    for position, node in enumerate(standard_fermentation_steps, start=1):
        raw_phase = _first_value(node, ("NAME", "TYPE"), "Autre")
        phase = {
            "primary": "Fermentation primaire",
            "secondary": "Fermentation secondaire",
            "tertiary": "Autre",
            "cold crash": "Cold crash",
            "conditioning": "Conditionnement",
        }.get(raw_phase.strip().lower(), "Autre")
        recipe["fermentation_steps"].append(
            {
                "position": position,
                "phase": phase,
                "temperature_c": float(_first_value(node, ("STEP_TEMP", "TEMPERATURE"), "20")),
                "duration_days": int(float(_first_value(node, ("STEP_TIME", "DURATION"), "0"))),
                "action": _value(node, "NOTES", ""),
            }
        )

    if not standard_fermentation_steps:
        legacy_fermentation = (
            ("PRIMARY", "Fermentation primaire"),
            ("SECONDARY", "Fermentation secondaire"),
            ("TERTIARY", "Autre"),
        )
        for prefix, phase in legacy_fermentation:
            temperature = _value(recipe_node, f"{prefix}_TEMP", "")
            duration = _value(recipe_node, f"{prefix}_AGE", "")
            if temperature != "" or duration != "":
                recipe["fermentation_steps"].append(
                    {
                        "position": len(recipe["fermentation_steps"]) + 1,
                        "phase": phase,
                        "temperature_c": float(temperature or 20),
                        "duration_days": int(float(duration or 0)),
                        "action": "",
                    }
                )
    return recipe

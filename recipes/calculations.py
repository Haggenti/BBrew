"""Calculs brassicoles purs, indépendants de Django."""

import math


def abv_from_gravity(original_gravity: float, final_gravity: float) -> float:
    """Estime l'alcool en volume à partir des densités initiale et finale."""
    return round((original_gravity - final_gravity) * 131.25, 2)


def gravity_points(mass_kg: float, potential_yield: float, volume_l: float, efficiency: float) -> float:
    """Calcule les points de densité apportés par un malt."""
    pounds = mass_kg * 2.20462
    gallons = volume_l * 0.264172
    ppg = (potential_yield / 100) * 46.214
    return pounds * ppg * (efficiency / 100) / gallons


def estimated_og(malts, volume_l: float, efficiency: float) -> float:
    points = sum(
        gravity_points(float(malt.amount_g) / 1000, float(malt.potential_yield), volume_l, efficiency)
        for malt in malts
    )
    return round(1 + points / 1000, 3)


def tinseth_ibu(
    hops,
    volume_l: float,
    original_gravity: float,
    preboil_volume_l: float | None = None,
) -> float:
    """Estime l'amertume Tinseth des ajouts bouillis.

    ``original_gravity`` représente la DI après ébullition. Quand le volume
    pré-ébullition est fourni, la densité pendant l'ébullition est recalculée
    par conservation des points de densité. Les pellets bénéficient d'un
    facteur d'efficacité de 1,09 par rapport aux cônes.
    """
    if volume_l <= 0:
        return 0
    total = 0.0
    boil_gravity = float(original_gravity)
    if preboil_volume_l and preboil_volume_l > volume_l:
        boil_gravity = 1 + (
            (float(original_gravity) - 1) * float(volume_l) / float(preboil_volume_l)
        )
    density_factor = max(1.0, 1 + (boil_gravity - 1.050) / 0.2)
    for hop in hops:
        addition = str(getattr(hop, "addition", "") or "").casefold()
        if addition in {"dry hop", "fermentation primaire", "garde", "conditionnement"}:
            continue
        utilization = 1.65 * (0.000125 ** (boil_gravity - 1))
        utilization /= density_factor
        utilization *= (1 - math.exp(-0.04 * float(hop.boil_minutes))) / 4.15
        hop_form = str(getattr(hop, "form", "") or "").strip().casefold()
        pellet_factor = 1.09 if hop_form in {"pellet", "pellets"} else 1.0
        total += (
            utilization
            * (float(hop.alpha_acid) / 100)
            * (float(hop.amount_g) * 1000 / volume_l)
            * pellet_factor
        )
    return round(total, 1)


def estimated_color_ebc(malts, volume_l: float) -> float:
    """Estime la couleur avec la formule de Morey, convertie en EBC."""
    volume_l = float(volume_l)
    if volume_l <= 0:
        return 0
    mcu_total = sum(
        4.23 * float(malt.color_ebc) * (float(malt.amount_g) / 1000) / volume_l
        for malt in malts
    )
    return round(2.9396 * (mcu_total**0.6859), 1) if mcu_total > 0 else 0


def ebc_color_rgb(ebc: float) -> str:
    """Retourne une approximation visuelle continue de la couleur EBC."""
    palette = (
        (0, (252, 235, 182)),
        (4, (248, 225, 122)),
        (8, (245, 200, 76)),
        (12, (233, 165, 46)),
        (18, (200, 107, 36)),
        (25, (168, 58, 36)),
        (30, (178, 53, 36)),
        (35, (127, 36, 28)),
        (40, (94, 30, 22)),
        (50, (58, 18, 11)),
        (60, (37, 12, 7)),
        (80, (22, 10, 3)),
    )
    value = float(ebc)
    if value <= palette[0][0]:
        color = palette[0][1]
    elif value >= palette[-1][0]:
        color = palette[-1][1]
    else:
        for (lower_limit, lower_color), (upper_limit, upper_color) in zip(palette, palette[1:]):
            if value <= upper_limit:
                ratio = (value - lower_limit) / (upper_limit - lower_limit)
                color = tuple(
                    round(lower + ratio * (upper - lower))
                    for lower, upper in zip(lower_color, upper_color)
                )
                break
    return f"rgb({color[0]}, {color[1]}, {color[2]})"


DEFAULT_MASH_TEMPERATURE_C = 65.0
MASH_FERMENTABILITY_LIMITS = (
    (60.0, 82.0),
    (63.0, 85.0),
    (66.0, 86.0),
    (69.0, 80.0),
    (72.0, 72.0),
)


def average_mash_temperature(mash_steps) -> float:
    """Calcule la température moyenne d'empâtage, pondérée par la durée."""
    steps = list(mash_steps or [])
    if not steps:
        return DEFAULT_MASH_TEMPERATURE_C
    total_minutes = sum(float(step.duration_min) for step in steps)
    if total_minutes <= 0:
        return DEFAULT_MASH_TEMPERATURE_C
    return sum(
        float(step.temperature_c) * float(step.duration_min)
        for step in steps
    ) / total_minutes


def mash_fermentability_limit(temperature_c: float) -> float:
    """Interpole la limite d'atténuation empirique selon la température."""
    temperature_c = float(temperature_c)
    if temperature_c <= MASH_FERMENTABILITY_LIMITS[0][0]:
        return MASH_FERMENTABILITY_LIMITS[0][1]
    if temperature_c >= MASH_FERMENTABILITY_LIMITS[-1][0]:
        return MASH_FERMENTABILITY_LIMITS[-1][1]
    for (lower_temperature, lower_limit), (upper_temperature, upper_limit) in zip(
        MASH_FERMENTABILITY_LIMITS,
        MASH_FERMENTABILITY_LIMITS[1:],
    ):
        if lower_temperature <= temperature_c <= upper_temperature:
            progress = (temperature_c - lower_temperature) / (upper_temperature - lower_temperature)
            return lower_limit + (upper_limit - lower_limit) * progress
    return MASH_FERMENTABILITY_LIMITS[-1][1]


def estimated_attenuation(yeasts, mash_steps=None) -> float | None:
    """Estime l'atténuation avec la fermentescibilité empirique du moût."""
    yeasts = [yeast for yeast in yeasts if not getattr(yeast, "for_bottling", False)]
    if not yeasts:
        return None
    total_amount = sum(float(yeast.amount_g) for yeast in yeasts)
    if total_amount <= 0:
        return None
    yeast_attenuation = max(float(yeast.attenuation) for yeast in yeasts)
    mash_limit = mash_fermentability_limit(average_mash_temperature(mash_steps))
    peak_limit = max(limit for _, limit in MASH_FERMENTABILITY_LIMITS)
    return round(max(0, min(100, yeast_attenuation * mash_limit / peak_limit)), 2)


def estimated_final_gravity(original_gravity: float, yeasts, mash_steps=None) -> float | None:
    """Estime la densité finale avec l'atténuation et l'empâtage."""
    attenuation = estimated_attenuation(yeasts, mash_steps)
    if attenuation is None:
        return None
    return round(1 + (original_gravity - 1) * (1 - attenuation / 100), 3)


def estimated_abv(original_gravity: float, yeasts, mash_steps=None) -> float | None:
    """Estime l'ABV à partir de l'OG et de la densité finale estimée."""
    final_gravity = estimated_final_gravity(original_gravity, yeasts, mash_steps)
    if final_gravity is None:
        return None
    return round((original_gravity - final_gravity) * 131.25, 2)


def estimate_snapshot(snapshot: dict) -> dict:
    """Calcule les valeurs prévues à partir d'un snapshot de recette."""
    from types import SimpleNamespace

    recipe = snapshot["recipe"]
    malts = [SimpleNamespace(**item) for item in snapshot.get("ingredients", []) if item["kind"] == "malt"]
    yeasts = [SimpleNamespace(**item) for item in snapshot.get("ingredients", []) if item["kind"] == "yeast"]
    mash_steps = [SimpleNamespace(**item) for item in snapshot.get("mash_steps", [])]
    volume = float(recipe["batch_size_l"])
    efficiency = float(recipe["efficiency"])
    og = estimated_og(malts, volume, efficiency) if malts else None
    reference_og = og or float(recipe["target_og"])
    return {
        "volume_l": volume,
        "efficiency": efficiency,
        "og": og,
        "fg": estimated_final_gravity(reference_og, yeasts, mash_steps),
        "abv": estimated_abv(reference_og, yeasts, mash_steps),
    }


def estimated_efficiency(malts, original_gravity: float, volume_l: float) -> float | None:
    """Estime le rendement réel à partir d'une DI mesurée."""
    original_gravity = float(original_gravity)
    volume_l = float(volume_l)
    potential_points = sum(
        gravity_points(float(malt.amount_g) / 1000, float(malt.potential_yield), volume_l, 100)
        for malt in malts
    )
    if potential_points <= 0:
        return None
    return round(((float(original_gravity) - 1) * 1000) / potential_points * 100, 1)


def ibu_final_gravity_ratio(ibu: float | None, final_gravity: float | None) -> float | None:
    """Calcule le rapport entre l'amertume IBU et la densité finale."""
    if ibu is None or final_gravity is None or final_gravity <= 0:
        return None
    return round(float(ibu) / float(final_gravity), 2)


IBU_FINAL_GRAVITY_DESCRIPTIONS = (
    (20, "très douce"),
    (35, "douce"),
    (50, "équilibrée"),
    (65, "amère"),
    (float("inf"), "très amère"),
)


def ibu_final_gravity_comment(ratio: float | None, final_gravity: float | None) -> str | None:
    """Retourne une description française du profil amertume/sucrosité."""
    if ratio is None or final_gravity is None:
        return None
    bitterness = next(
        description
        for limit, description in IBU_FINAL_GRAVITY_DESCRIPTIONS
        if ratio < limit
    )
    if final_gravity >= 1.020:
        sweetness = "liquoreuse"
    elif final_gravity >= 1.014:
        sweetness = "douce"
    else:
        sweetness = "sèche"
    return f"{bitterness}, finale {sweetness}"


def bu_gu_ratio(ibu: float | None, original_gravity: float | None) -> float | None:
    """Calcule le ratio BU:GU à partir de l'IBU et de la DI."""
    if ibu is None or original_gravity is None:
        return None
    gravity_units = (float(original_gravity) - 1) * 1000
    if gravity_units <= 0:
        return None
    return round(float(ibu) / gravity_units, 2)


def bu_gu_comment(ratio: float | None) -> str | None:
    """Interprète le ratio BU:GU selon l'équilibre amertume/densité."""
    if ratio is None:
        return None
    if ratio < 0.5:
        return "douce"
    if ratio <= 0.8:
        return "équilibrée"
    return "amère"


def plato_from_gravity(gravity: float) -> float:
    """Convertit une densité spécifique en degrés Plato."""
    plato = (
        -616.868
        + 1111.14 * gravity
        - 630.272 * gravity**2
        + 135.997 * gravity**3
    )
    return round(plato, 1)

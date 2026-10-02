"""Calculs brassicoles purs, indépendants de Django."""


def abv_from_gravity(original_gravity: float, final_gravity: float) -> float:
    """Estime l'alcool en volume à partir des densités initiale et finale."""
    return round((original_gravity - final_gravity) * 131.25, 2)


def gravity_points(mass_kg: float, ppg: float, volume_l: float, efficiency: float) -> float:
    """Calcule les points de densité apportés par un malt."""
    pounds = mass_kg * 2.20462
    gallons = volume_l * 0.264172
    return pounds * ppg * (efficiency / 100) / gallons


def estimated_og(malts, volume_l: float, efficiency: float) -> float:
    points = sum(
        gravity_points(float(malt.amount_g) / 1000, float(malt.ppg), volume_l, efficiency)
        for malt in malts
    )
    return round(1 + points / 1000, 3)


def tinseth_ibu(hops, volume_l: float, original_gravity: float) -> float:
    """Estimation Tinseth simplifiée pour les ajouts d'ébullition."""
    total = 0.0
    for hop in hops:
        utilization = 1.65 * (0.000125 ** (original_gravity - 1))
        utilization *= (1 - 2.71828 ** (-0.04 * float(hop.boil_minutes))) / 4.15
        total += (
            utilization
            * (float(hop.alpha_acid) / 100)
            * (float(hop.amount_g) * 1000 / volume_l)
        )
    return round(total, 1)

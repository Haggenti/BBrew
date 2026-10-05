from decimal import Decimal, InvalidOperation

from django import template
from django.utils.formats import number_format


register = template.Library()


@register.filter
def compact_number(value, max_decimal_places=3):
    try:
        decimal_value = Decimal(str(value))
        decimal_places = int(max_decimal_places)
        rounded_value = decimal_value.quantize(Decimal(1).scaleb(-decimal_places))
    except (InvalidOperation, TypeError, ValueError):
        return value

    normalized = rounded_value.normalize()
    displayed_places = max(0, -normalized.as_tuple().exponent)
    return number_format(rounded_value, decimal_pos=displayed_places, use_l10n=True)

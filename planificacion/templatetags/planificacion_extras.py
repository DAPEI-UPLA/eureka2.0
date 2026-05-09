from django import template
from ..helpers import color_avance, hex_color_avance

register = template.Library()


@register.filter
def color_for(avance):
    return color_avance(avance)


@register.filter
def hex_color_for(avance):
    return hex_color_avance(avance)


@register.filter
def avance_clamp(v):
    """Recorta a 0..100 para anchos de barra."""
    if v is None:
        return 0
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0
    return max(0, min(int(v), 100))


@register.filter
def format_unidad(value, unidad_medida):
    """
    Formatea un valor según la unidad de medida del indicador.
        UNI -> número (entero o hasta 2 decimales, sin ceros sobrantes)
        POR -> número + '%'
        CAR -> valor tal cual (texto)
    Devuelve '—' si el valor es None o vacío.
    """
    if value is None or value == "":
        return "—"

    if unidad_medida == "CAR":
        return str(value)

    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)

    if v == int(v):
        formatted = str(int(v))
    else:
        formatted = f"{v:.2f}".rstrip("0").rstrip(".")

    if unidad_medida == "POR":
        return f"{formatted}%"
    return formatted

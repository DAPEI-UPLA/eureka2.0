"""Formato de montos para las cajas de edición.

Django trae `intcomma`, pero con `LANGUAGE_CODE = 'es-cl'` el módulo de formato
del locale manda sobre `settings.THOUSAND_SEPARATOR` y agrupa los miles con un
**espacio duro** (U+00A0): $25 000 000. El `THOUSAND_SEPARATOR = '.'` que hay en
settings queda ignorado.

Para leer un presupuesto de nueve cifras el punto es mucho más claro que un
espacio, y es lo que se usa en Chile. Este filtro lo impone sin depender del
locale, con la misma forma que `numeros.pesos()` usa en los mensajes de error,
para que la pantalla y los avisos digan el número igual.

Lo que se escribe vuelve al servidor por `numeros.limpiar_monto`, que ya
descarta puntos, espacios duros y símbolos: da lo mismo en qué formato viaje.
"""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def miles(valor):
    """25000000 -> «25.000.000». Vacío o no numérico -> «0»."""
    if valor is None or valor == "":
        return "0"
    if isinstance(valor, str):
        # Puede venir ya formateado desde un intento anterior del usuario.
        limpio = valor.replace(".", "").replace("\xa0", "").replace(" ", "")
        try:
            valor = Decimal(limpio or "0")
        except InvalidOperation:
            return valor
    try:
        return f"{valor:,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(valor)

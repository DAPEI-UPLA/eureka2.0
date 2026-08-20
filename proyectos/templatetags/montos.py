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


@register.filter
def miles_abs(valor):
    """Como `miles`, pero sin el signo.

    Las desviaciones se guardan con signo (un VAC negativo es plata que falta),
    y en la pantalla el signo ya lo pone la frase: «faltarían $25.000.000» con
    un menos delante se leería como si sobraran.
    """
    try:
        return miles(abs(Decimal(valor)))
    except (TypeError, ValueError, InvalidOperation):
        return miles(valor)


@register.filter
def escala_indice(indice):
    """Un índice de valor ganado (0..∞) como porcentaje de una barra 0..100.

    La marca del 1,00 —la meta— va al 60% del ancho, no al 100%: un índice
    puede pasar de 1 y con la meta en el extremo derecho no habría dónde
    dibujar el excedente, así que todo lo bueno se vería idéntico. Por encima
    de 1,67 la barra se llena y deja de crecer; a esa altura el número exacto
    ya no cambia ninguna decisión.
    """
    try:
        valor = Decimal(indice)
    except (TypeError, ValueError, InvalidOperation):
        return "0"
    if valor < 0:
        valor = Decimal("0")
    porcentaje = valor * Decimal("60")
    if porcentaje > 100:
        porcentaje = Decimal("100")
    return f"{porcentaje:.1f}"

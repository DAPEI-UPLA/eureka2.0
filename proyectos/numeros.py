"""Lectura de montos escritos por personas.

Un mismo monto llega de formas distintas según de dónde venga: tecleado a mano
("1500000", "1.500.000", "$1.500.000"), o de vuelta desde un input que el
template ya formateó. Este último caso es el traicionero: con
``USE_THOUSAND_SEPARATOR = True`` y ``LANGUAGE_CODE = 'es-cl'``, Django agrupa
los miles con un **espacio duro** (U+00A0), no con punto. Así, un objetivo con
$50.000.000 vuelve al servidor como ``"50\xa0000\xa0000"``; si solo se limpian
puntos y comas, el espacio duro sobrevive y `Decimal` revienta.

Por eso la limpieza descarta todo lo que no aporte valor numérico —símbolos,
espacios en cualquiera de sus variantes Unicode, separadores de miles— y deja
únicamente el signo, los dígitos y el separador decimal.
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

# Variantes de espacio que los formateadores de Django y los pegados desde
# Excel usan como separador de miles.
_ESPACIOS = "\xa0   \t\n\r "

_BASURA = _ESPACIOS + "$"


def limpiar_monto(valor):
    """Normaliza un monto a texto apto para `Decimal`, o `None` si viene vacío.

    Regla para el separador decimal: manda la coma (convención chilena). Si no
    hay coma, los puntos se tratan como separador de miles, salvo que el punto
    sea claramente decimal —un solo punto seguido de una o dos cifras, como
    "1234.50"—, forma en que suelen llegar los valores calculados en JavaScript.
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float, Decimal)):
        return str(valor)

    texto = str(valor)
    for caracter in _BASURA:
        texto = texto.replace(caracter, "")
    if not texto:
        return None

    if "," in texto:
        # "1.234.567,89" -> los puntos son miles y la coma es el decimal.
        texto = texto.replace(".", "").replace(",", ".")
    elif texto.count(".") == 1:
        entero, _, decimales = texto.partition(".")
        if len(decimales) > 2:
            # "1.234" son mil doscientos treinta y cuatro, no 1,234.
            texto = entero + decimales
    else:
        # Cero o varios puntos: todos son separadores de miles.
        texto = texto.replace(".", "")

    return texto or None


def pesos(monto):
    """Formatea un monto para leerlo dentro de un mensaje: $15.300.000.

    Los mensajes de validación son texto plano, así que no pasan por los filtros
    de la plantilla; sin esto salían con coma inglesa ("$15,300,000").
    """
    return f"${monto or 0:,.0f}".replace(",", ".")


def a_decimal(valor, default=Decimal("0")):
    """Convierte un monto escrito por una persona en `Decimal`.

    Devuelve `default` si no hay nada que convertir y levanta `ValidationError`
    con un mensaje que muestra lo recibido, para que el usuario pueda corregirlo.
    """
    if isinstance(valor, Decimal):
        return valor

    texto = limpiar_monto(valor)
    if texto is None:
        return default
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        raise ValidationError(f"«{valor}» no es un monto válido.")

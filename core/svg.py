"""Primitivas para dibujar gráficos como SVG desde el servidor.

**Por qué el servidor y no Chart.js.** Los informes existen para imprimirse. Un
``<canvas>`` depende de que el JS haya corrido y de que el CDN haya respondido;
si algo de eso falla —o si el navegador manda a imprimir antes de que el
gráfico termine de animarse— en el papel queda un rectángulo en blanco, y nadie
se entera hasta que el informe ya está entregado. Un ``<svg>`` inline se
imprime siempre, sale nítido a cualquier resolución, no agrega dependencias y
funciona igual en el servidor interno sin salida a internet.

**Por qué las coordenadas salen como texto.** Con ``LANGUAGE_CODE='es-cl'`` y
``USE_THOUSAND_SEPARATOR``, Django dibujaría un ``150.25`` como ``150,25`` y un
``1200`` como ``1 200``: cualquiera de las dos cosas rompe el atributo del SVG y
el gráfico desaparece **sin ningún aviso**. Formateando acá el problema no puede
aparecer, y no hay que acordarse de poner ``|unlocalize`` en veinte atributos.

Acá viven solo las piezas que comparten todos los informes; la geometría de
cada gráfico se arma en el módulo de su app, porque depende de qué se compara.
"""

import math
from decimal import Decimal


def numero(valor):
    """Decimal/None/int -> float, para poder hacer cuentas sin sobresaltos."""
    if isinstance(valor, Decimal):
        return float(valor)
    return float(valor or 0)


def coordenada(valor):
    """Coordenada lista para el atributo del SVG, como texto. Ver el docstring."""
    return f"{float(valor):.2f}".rstrip("0").rstrip(".") or "0"


def escala_agradable(tope, divisiones=4):
    """Sube el techo del eje hasta un número redondo.

    Con el máximo crudo, las líneas de referencia quedaban en $603M, $453M,
    $302M… que no se leen. Buscando un paso de 1, 2, 2,5 o 5 por potencia de
    diez, quedan en $200M, $400M, $600M, $800M.
    """
    if tope <= 0:
        return 1.0
    crudo = tope / divisiones
    exponente = 10 ** math.floor(math.log10(crudo))
    for multiplo in (1, 2, 2.5, 5, 10):
        if crudo <= multiplo * exponente:
            return multiplo * exponente * divisiones
    return tope


def etiqueta_monto(monto):
    """Etiqueta corta para ejes y barras: 603.377.451 -> «$603M».

    El monto exacto siempre está en la tabla de al lado; acá lo que importa es
    que el rótulo entre en el ancho que tiene.
    """
    monto = numero(monto)
    if not monto:
        return "$0"
    signo = "-" if monto < 0 else ""
    monto = abs(monto)
    if monto >= 1_000_000:
        return f"{signo}${monto / 1_000_000:,.0f}M".replace(",", ".")
    if monto >= 1000:
        return f"{signo}${monto / 1000:,.0f}k".replace(",", ".")
    return f"{signo}${monto:,.0f}".replace(",", ".")


def recortar(texto, largo):
    """Rótulo que entra en la columna, con puntos suspensivos si sobra."""
    texto = str(texto or "")
    return texto if len(texto) <= largo else texto[: largo - 1].rstrip() + "…"

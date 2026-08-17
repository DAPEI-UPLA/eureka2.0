"""Gráficos del informe OCT, dibujados como SVG en el servidor.

**Por qué no Chart.js acá.** El informe existe para imprimirse. Un ``<canvas>``
depende de que el JS haya corrido y de que el CDN haya respondido; si algo de
eso falla —o si el navegador manda a imprimir antes de que el gráfico termine
de animarse— en el papel queda un rectángulo en blanco, y nadie se entera hasta
que el informe ya está entregado. Un ``<svg>`` inline se imprime siempre, sale
nítido a cualquier resolución, no agrega dependencias y funciona igual en el
servidor interno sin salida a internet.

Acá se calcula solo la **geometría**: cada función devuelve las coordenadas ya
resueltas y la plantilla las recorre. Así el SVG del template queda legible y
las cuentas quedan donde se pueden probar.

**Todas las coordenadas se devuelven como texto**, nunca como número: con
``LANGUAGE_CODE='es-cl'`` un ``150.25`` se dibujaría ``150,25`` y el SVG
desaparece sin aviso. De eso se encarga ``core.svg``, que es donde viven las
primitivas compartidas con los demás informes.

Los colores son los mismos de ``oct/tablero.py``: un acento azul, un naranja
para contrastar dos series y neutros para el resto. Nunca se codifica
información **solo** en el color — toda barra lleva su número al lado.
"""

from core.svg import coordenada as _c
from core.svg import escala_agradable as _escala_agradable
from core.svg import etiqueta_monto as _millones
from core.svg import numero as _num

from .tablero import COLOR_APAGADO, COLOR_SERIE, COLOR_SERIE_2

# Lienzo de los gráficos de barras horizontales (los de media página).
ANCHO_BARRAS = 320
COL_ETIQUETA = 104          # ancho reservado a los rótulos de la izquierda
COL_VALOR = 66              # ancho reservado al número de la derecha
ALTO_FILA = 26
ALTO_BARRA = 11

# Lienzo del gráfico mensual (el de la página apaisada).
ANCHO_MESES = 900
ALTO_MESES = 240
MARGEN_MESES = {"izq": 74, "der": 10, "arriba": 12, "abajo": 32}


def barras_de_avance(filas):
    """Gestiones realizadas contra la meta, un ámbito por fila.

    Cada fila es una barra azul con lo hecho y, a continuación, en gris, lo que
    falta para la meta: juntas miden la meta y la comparación se lee sin
    leyenda. La escala es común a todas las filas —si no, una meta de 8 y otra
    de 20 se verían del mismo largo—, así que las barras completas tienen
    distinto ancho y eso también es información.

    **Cuando se supera la meta** la barra azul se pasa de largo (que es la
    verdad) y se marca con una línea dónde estaba la meta; si en cambio se
    recortara al riel, el informe diría que se cumplió justo.
    """
    if not filas:
        return None

    escala_max = max(
        [_num(f["meta"]) for f in filas] + [_num(f["gestiones"]) for f in filas] + [1]
    )
    util = ANCHO_BARRAS - COL_ETIQUETA - COL_VALOR
    escala = util / escala_max

    dibujadas = []
    for i, f in enumerate(filas):
        meta = _num(f["meta"])
        hechas = _num(f["gestiones"])
        y = i * ALTO_FILA + 6
        ancho_hecho = hechas * escala
        pendiente = max(meta - hechas, 0) * escala

        dibujadas.append({
            "etiqueta": f["etiqueta"],
            "y": _c(y),
            "y_texto": _c(y + ALTO_BARRA - 1.5),
            "x": _c(COL_ETIQUETA),
            "x_valor": _c(COL_ETIQUETA + util + 6),
            "alto": _c(ALTO_BARRA),
            # Una hebra mínima para que un cero no desaparezca del todo.
            "ancho_hecho": _c(ancho_hecho if hechas else 0.8),
            "x_pendiente": _c(COL_ETIQUETA + ancho_hecho),
            "ancho_pendiente": _c(pendiente),
            "supera": hechas > meta,
            "x_meta": _c(COL_ETIQUETA + meta * escala),
            "y_meta_fin": _c(y + ALTO_BARRA),
            "texto": f"{hechas:.0f} de {meta:.0f}",
            "porcentaje": f'{_num(f["avance_pct"]):.0f}%',
        })

    return {
        "ancho": _c(ANCHO_BARRAS),
        "alto": _c(len(filas) * ALTO_FILA + 8),
        "filas": dibujadas,
        "color": COLOR_SERIE,
        "color_pista": COLOR_APAGADO,
    }


def barras_por_estado(conteos):
    """Cuántas iniciativas hay en cada estado. Una sola serie, un solo color.

    ``conteos`` es una lista de ``(etiqueta, cantidad)`` ya ordenada; se omiten
    los estados vacíos para no llenar el informe de ceros.
    """
    visibles = [(etiqueta, n) for etiqueta, n in conteos if n]
    if not visibles:
        return None

    escala_max = max(n for _, n in visibles)
    util = ANCHO_BARRAS - COL_ETIQUETA - 30

    filas = []
    for i, (etiqueta, n) in enumerate(visibles):
        y = i * ALTO_FILA + 6
        ancho = max(util * n / escala_max, 1)
        filas.append({
            "etiqueta": etiqueta,
            "y": _c(y),
            "y_texto": _c(y + ALTO_BARRA - 1.5),
            "x": _c(COL_ETIQUETA),
            "x_valor": _c(COL_ETIQUETA + ancho + 5),
            "alto": _c(ALTO_BARRA),
            "ancho": _c(ancho),
            "texto": str(n),
        })

    return {
        "ancho": _c(ANCHO_BARRAS),
        "alto": _c(len(visibles) * ALTO_FILA + 8),
        "filas": filas,
        "color": COLOR_SERIE,
    }


def columnas_mensuales(meses, proyectado, efectivo):
    """Ingreso proyectado y efectivo, mes a mes, en columnas apareadas.

    Devuelve también las líneas de referencia con su rótulo, para que el
    gráfico se pueda leer sin volver a la tabla.
    """
    valores = [_num(v) for v in proyectado] + [_num(v) for v in efectivo]
    tope = _escala_agradable(max(valores + [0]))

    izq = MARGEN_MESES["izq"]
    arriba = MARGEN_MESES["arriba"]
    alto_util = ALTO_MESES - arriba - MARGEN_MESES["abajo"]
    ancho_util = ANCHO_MESES - izq - MARGEN_MESES["der"]
    base = arriba + alto_util

    paso = ancho_util / len(meses)
    ancho_barra = min(paso / 2 - 3, 22)

    grupos = []
    for i, (_, nombre) in enumerate(meses):
        centro = izq + paso * (i + 0.5)
        alto_p = alto_util * _num(proyectado[i]) / tope
        alto_e = alto_util * _num(efectivo[i]) / tope
        grupos.append({
            "nombre": nombre,
            "centro": _c(centro),
            "x_proyectado": _c(centro - ancho_barra - 1),
            "y_proyectado": _c(base - alto_p),
            "alto_proyectado": _c(alto_p),
            "x_efectivo": _c(centro + 1),
            "y_efectivo": _c(base - alto_e),
            "alto_efectivo": _c(alto_e),
        })

    referencias = [
        {"y": _c(base - alto_util * i / 4), "etiqueta": _millones(tope * i / 4)}
        for i in range(5)
    ]

    return {
        "ancho": _c(ANCHO_MESES),
        "alto": _c(ALTO_MESES),
        "x_eje": _c(izq),
        "x_fin": _c(izq + ancho_util),
        "base": _c(base),
        "y_meses": _c(base + 14),
        "ancho_barra": _c(ancho_barra),
        "grupos": grupos,
        "referencias": referencias,
        "color_proyectado": COLOR_APAGADO,
        "color_efectivo": COLOR_SERIE_2,
        # Con todo el efectivo en cero, la serie naranja no se ve: conviene
        # decirlo con palabras en vez de dejar el gráfico mudo.
        "hay_efectivo": any(_num(v) for v in efectivo),
    }

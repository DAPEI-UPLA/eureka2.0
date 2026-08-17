"""Geometría de los gráficos del informe imprimible de un proyecto.

Son SVG dibujados en el servidor (el porqué está en ``core.svg``): el informe
se manda a imprimir, y un gráfico que depende de JavaScript sale en blanco en
el papel sin que nadie lo note. No se toca ``views/graficos.py``, que sigue
alimentando Chart.js en la pantalla: ahí un gráfico que no carga se ve al
instante y basta recargar.

Cada función devuelve las coordenadas ya resueltas —como texto— y la plantilla
solo las recorre. Así el SVG del template queda legible y las cuentas quedan
donde se pueden probar.

Ninguna información se codifica **solo** en el color: toda barra lleva su
número al lado. Los colores son los mismos que usa la pantalla de gráficos
(``views/graficos.py``), para que el informe no contradiga lo que se vio antes.
"""

from decimal import Decimal

from core.svg import coordenada as _c
from core.svg import escala_agradable, etiqueta_monto, numero, recortar

# Paleta: la misma de las pantallas de proyectos.
COLOR_PAGADO = "#198754"
COLOR_COMPROMETIDO = "#f59e0b"
COLOR_DISPONIBLE = "#e2e8f0"
COLOR_CORRIENTE = "#1d4ed8"
COLOR_CAPITAL = "#7c3aed"
COLOR_APAGADO = "#cbd5e1"
COLOR_FISICO = "#2563eb"
COLOR_FINANCIERO = "#f59e0b"
COLOR_LIMITE = "#0f172a"

# Lienzo de los gráficos de ancho completo.
ANCHO_TOTAL = 620
# Lienzo de los que van de a dos por fila.
ANCHO_MEDIO = 320

ALTO_FILA = 26
ALTO_BARRA = 11


def barra_de_ejecucion(pagado, comprometido, presupuesto):
    """Una sola barra apilada: pagado + comprometido + lo que queda.

    Es el titular del informe, así que ocupa el ancho de la hoja.

    **Si el gasto se pasó del presupuesto** la barra se pasa de largo y una
    línea marca dónde estaba el presupuesto. Recortarla al presupuesto sería
    dibujar una barra llena, que es exactamente lo que se ve cuando se gastó
    justo: el informe estaría tapando el sobregiro.
    """
    pagado = max(numero(pagado), 0)
    comprometido = max(numero(comprometido), 0)
    presupuesto = numero(presupuesto)
    gastado = pagado + comprometido
    disponible = max(presupuesto - gastado, 0)

    tope = max(presupuesto, gastado, 1)
    escala = ANCHO_TOTAL / tope

    alto_barra = 26
    y = 16
    x = 0.0
    segmentos = []
    for etiqueta, monto, color, texto_claro in (
        ("Pagado", pagado, COLOR_PAGADO, True),
        ("Comprometido", comprometido, COLOR_COMPROMETIDO, True),
        ("Disponible", disponible, COLOR_DISPONIBLE, False),
    ):
        ancho = monto * escala
        porcentaje = (monto / presupuesto * 100) if presupuesto else 0
        segmentos.append({
            "etiqueta": etiqueta,
            # El monto va en la leyenda: un segmento de 1% no tiene dónde
            # escribirlo adentro, y sin número la barra no dice nada.
            "monto": monto,
            "x": _c(x),
            "ancho": _c(ancho),
            "color": color,
            "texto": f"{porcentaje:.0f}%",
            "x_texto": _c(x + ancho / 2),
            "claro": texto_claro,
            # Un «12%» necesita unos 26 px para no salirse de su segmento; si
            # no caben, el número igual está en la leyenda y en el KPI.
            "cabe": ancho >= 30,
        })
        x += ancho

    return {
        "ancho": _c(ANCHO_TOTAL),
        "alto": _c(y + alto_barra + 6),
        "y": _c(y),
        "alto_barra": _c(alto_barra),
        "segmentos": segmentos,
        "supera": gastado > presupuesto > 0,
        "x_limite": _c(presupuesto * escala),
        "y_limite": _c(y - 5),
        "y_limite_fin": _c(y + alto_barra + 5),
        "x_rotulo_limite": _c(min(max(presupuesto * escala, 44), ANCHO_TOTAL - 44)),
        "y_rotulo_limite": _c(y - 8),
        "color_limite": COLOR_LIMITE,
        "etiqueta_limite": f"Presupuesto {etiqueta_monto(presupuesto)}",
    }


def barras_de_bolsas(bolsas):
    """Gastado contra presupuesto, una fila por bolsa (corriente y capital).

    ``bolsas`` es una lista de ``(etiqueta, gastado, presupuesto, color)``.
    Cada fila es lo gastado y, a continuación en gris, lo que queda: juntos
    miden el presupuesto de esa bolsa. La escala es común a las dos filas —si
    no, una bolsa de $10M y otra de $90M se verían del mismo largo— y por eso
    las barras completas tienen distinto ancho, que también es información.

    Como en la barra de ejecución, pasarse del presupuesto se dibuja pasándose.
    """
    bolsas = [b for b in bolsas if numero(b[2]) or numero(b[1])]
    if not bolsas:
        return None

    col_etiqueta = 74
    col_valor = 96
    util = ANCHO_MEDIO - col_etiqueta - col_valor
    tope = max([numero(p) for _, _, p, _ in bolsas] + [numero(g) for _, g, _, _ in bolsas] + [1])
    escala = util / tope

    filas = []
    for i, (etiqueta, gastado, presupuesto, color) in enumerate(bolsas):
        gastado = max(numero(gastado), 0)
        presupuesto = numero(presupuesto)
        y = i * ALTO_FILA + 6
        ancho_gastado = gastado * escala
        pendiente = max(presupuesto - gastado, 0) * escala
        filas.append({
            "etiqueta": etiqueta,
            "color": color,
            "y": _c(y),
            "y_texto": _c(y + ALTO_BARRA - 1.5),
            "x": _c(col_etiqueta),
            "x_valor": _c(col_etiqueta + util + 6),
            "alto": _c(ALTO_BARRA),
            # Una hebra mínima para que un cero no desaparezca del todo.
            "ancho_gastado": _c(ancho_gastado if gastado else 0.8),
            "x_pendiente": _c(col_etiqueta + ancho_gastado),
            "ancho_pendiente": _c(pendiente),
            "supera": gastado > presupuesto,
            "x_limite": _c(col_etiqueta + presupuesto * escala),
            "y_limite_fin": _c(y + ALTO_BARRA),
            "texto": f"{etiqueta_monto(gastado)} de {etiqueta_monto(presupuesto)}",
        })

    return {
        "ancho": _c(ANCHO_MEDIO),
        "alto": _c(len(filas) * ALTO_FILA + 8),
        "filas": filas,
        "color_pendiente": COLOR_APAGADO,
        "color_limite": COLOR_LIMITE,
    }


def barras_de_montos(items, ancho=ANCHO_MEDIO, col_etiqueta=112, largo_rotulo=20):
    """Una serie de montos, de mayor a menor. Sirve para transferencias.

    ``items`` es una lista de ``(etiqueta, monto)``; se omiten los ceros para
    no llenar el informe de barras invisibles.
    """
    visibles = [(e, numero(m)) for e, m in items if numero(m) > 0]
    if not visibles:
        return None
    visibles.sort(key=lambda par: -par[1])

    col_valor = 58
    util = ancho - col_etiqueta - col_valor
    tope = max(m for _, m in visibles)

    filas = []
    for i, (etiqueta, monto) in enumerate(visibles):
        y = i * ALTO_FILA + 6
        largo = max(util * monto / tope, 1)
        filas.append({
            "etiqueta": recortar(etiqueta, largo_rotulo),
            "titulo": str(etiqueta),
            "y": _c(y),
            "y_texto": _c(y + ALTO_BARRA - 1.5),
            "x": _c(col_etiqueta),
            "x_valor": _c(col_etiqueta + largo + 5),
            "alto": _c(ALTO_BARRA),
            "ancho": _c(largo),
            "texto": etiqueta_monto(monto),
        })

    return {
        "ancho": _c(ancho),
        "alto": _c(len(filas) * ALTO_FILA + 8),
        "filas": filas,
        "color": COLOR_FISICO,
    }


def barras_de_objetivos(objetivos):
    """Avance físico contra avance financiero, un par de barras por objetivo.

    Es la comparación que el informe no podía mostrar con una tabla: un
    objetivo con 20% de cumplimiento y 80% de presupuesto gastado se ve de
    inmediato, y ese desajuste es justamente lo que hay que mirar.

    Las dos series son porcentajes, así que comparten escala y llevan una línea
    en el 100%. Si algo se pasa del 100 la escala se estira hasta un número
    redondo, para que la línea del 100% siga significando lo mismo.
    """
    if not objetivos:
        return None

    col_etiqueta = 152
    col_valor = 52
    util = ANCHO_TOTAL - col_etiqueta - col_valor
    tope = max(
        [numero(o["fisico"]) for o in objetivos] + [numero(o["financiero"]) for o in objetivos] + [100]
    )
    tope = escala_agradable(tope) if tope > 100 else 100.0
    escala = util / tope

    alto_par = 9
    alto_fila = 30
    filas = []
    for i, objetivo in enumerate(objetivos):
        y = i * alto_fila + 4
        fisico = max(numero(objetivo["fisico"]), 0)
        financiero = max(numero(objetivo["financiero"]), 0)
        filas.append({
            "etiqueta": objetivo["etiqueta"],
            "titulo": objetivo.get("titulo", ""),
            "x": _c(col_etiqueta),
            "y_rotulo": _c(y + alto_par + 2),
            "alto": _c(alto_par),
            "y_fisico": _c(y),
            "ancho_fisico": _c(max(fisico * escala, 0.8)),
            "x_valor_fisico": _c(col_etiqueta + fisico * escala + 5),
            "y_texto_fisico": _c(y + alto_par - 1),
            "texto_fisico": f"{fisico:.0f}%",
            "y_financiero": _c(y + alto_par + 3),
            "ancho_financiero": _c(max(financiero * escala, 0.8)),
            "x_valor_financiero": _c(col_etiqueta + financiero * escala + 5),
            "y_texto_financiero": _c(y + alto_par * 2 + 2),
            "texto_financiero": f"{financiero:.0f}%",
        })

    return {
        "ancho": _c(ANCHO_TOTAL),
        "alto": _c(len(filas) * alto_fila + 6),
        "filas": filas,
        "x_cien": _c(col_etiqueta + 100 * escala),
        "y_cien_fin": _c(len(filas) * alto_fila),
        "color_fisico": COLOR_FISICO,
        "color_financiero": COLOR_FINANCIERO,
        "color_limite": COLOR_LIMITE,
    }


def porcentaje(parte, total):
    """Porcentaje que no explota con el total en cero (que es lo normal acá:
    un objetivo recién creado todavía no tiene presupuesto asignado)."""
    total = numero(total)
    if not total:
        return Decimal("0")
    return Decimal(str(numero(parte) / total * 100))

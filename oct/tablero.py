"""Los cálculos del Tablero Maestro de Resultados OCT.

En la planilla, las hojas «Avance mensual» y «Tablero de control» son
**puras fórmulas** sobre «Registro iniciativas»: COUNTIFS y SUMIFS por mes y
por estado. Acá se recalculan a partir de los registros guardados, con las
mismas reglas, para que no existan dos versiones del mismo número.

Las reglas, tal como están en el archivo:

* **gestionadas** — se cuentan por el **mes de ingreso**. Una fila sin fecha de
  ingreso no cae en ningún mes y por lo tanto no suma en el total. (Por eso la
  fila de ejemplo de donaciones aparece en el registro pero el tablero muestra
  0 gestiones: no es un error, es la planilla.)
* **presentadas** — mismas de arriba, pero solo las que ya salieron de la casa.
* **exitosas** — se cuentan por el **mes de resultado** y con el estado de
  éxito que corresponde al ámbito: adjudicada, suscrita o recibida.
* **montos** — el postulado sigue al mes de ingreso; el adjudicado, al mes de
  resultado.

Un detalle heredado que conviene tener presente: la «tasa de adjudicación»
mensual se calcula sobre las **presentadas**, mientras que la «tasa de éxito»
del tablero de control se calcula sobre las **gestionadas**. Son dos preguntas
distintas y el Excel las hace distinto; se respeta.
"""

from decimal import Decimal

from django.db.models import Sum

from .models import (
    ESTADO_EXITOSO,
    Ambito,
    Gestion,
    MetaAmbito,
    ProyeccionMensual,
)

MESES = [
    (1, "ene"), (2, "feb"), (3, "mar"), (4, "abr"), (5, "may"), (6, "jun"),
    (7, "jul"), (8, "ago"), (9, "sept"), (10, "oct"), (11, "nov"), (12, "dic"),
]

CERO = Decimal("0")

# Cómo se llama cada indicador en cada ámbito. El Excel les cambia el nombre
# —un convenio no se "adjudica", se suscribe— aunque el cálculo sea el mismo.
ROTULOS = {
    Ambito.PROYECTOS: [
        "Iniciativas gestionadas", "Postulaciones presentadas", "Adjudicaciones",
        "Tasa de adjudicación", "Monto postulado", "Monto adjudicado",
    ],
    Ambito.LICITACIONES: [
        "Iniciativas gestionadas", "Ofertas presentadas", "Licitaciones adjudicadas",
        "Tasa de adjudicación", "Monto ofertado", "Monto adjudicado",
    ],
    Ambito.CONVENIOS: [
        "Convenios gestionados", "Propuestas formalizadas", "Convenios suscritos",
        "Tasa de formalización", "Monto gestionado", "Monto comprometido",
    ],
    Ambito.DONACIONES: [
        "Donaciones gestionadas", "Solicitudes/contactos formalizados",
        "Donaciones recibidas", "Tasa de conversión",
        "Monto solicitado/gestionado", "Monto recibido",
    ],
}

# Las claves de cada fila, en el mismo orden que los rótulos.
FILAS = [
    "gestionadas", "presentadas", "exitosas", "tasa", "monto_postulado",
    "monto_adjudicado",
]

# Filas que son porcentajes y no cantidades ni pesos.
FILAS_TASA = {"tasa"}
FILAS_MONTO = {"monto_postulado", "monto_adjudicado"}


def _division(numerador, denominador):
    """El IFERROR(a/b, 0) de la planilla."""
    if not denominador:
        return CERO
    return Decimal(numerador) / Decimal(denominador)


def porcentaje(proporcion):
    """0.283 -> 28.3. Las plantillas de Django no multiplican, así que el
    número llega listo para mostrar."""
    return (proporcion or CERO) * 100


def _vacio():
    return {mes: CERO for mes, _ in MESES}


def avance_mensual(anio, gestiones=None):
    """Reproduce la hoja «Avance mensual»: un bloque por ámbito.

    Devuelve una lista de bloques ``{ambito, etiqueta, filas}``, donde cada
    fila trae ``meses`` (los doce valores, en orden) y ``total``.
    """
    if gestiones is None:
        gestiones = Gestion.objects.filter(anio=anio)

    # Un solo recorrido: son pocas filas y así el cálculo queda en un lugar.
    datos = {
        ambito: {clave: _vacio() for clave in FILAS}
        for ambito in Ambito.values
    }

    for g in gestiones:
        bloque = datos.get(g.ambito)
        if bloque is None:
            continue

        if g.mes_ingreso:
            bloque["gestionadas"][g.mes_ingreso] += 1
            bloque["monto_postulado"][g.mes_ingreso] += g.monto_postulado or CERO
            if g.fue_presentada:
                bloque["presentadas"][g.mes_ingreso] += 1

        if g.mes_resultado:
            bloque["monto_adjudicado"][g.mes_resultado] += g.monto_adjudicado or CERO
            if g.estado == ESTADO_EXITOSO.get(g.ambito):
                bloque["exitosas"][g.mes_resultado] += 1

    bloques = []
    for ambito in Ambito.values:
        crudo = datos[ambito]
        for mes, _ in MESES:
            crudo["tasa"][mes] = _division(
                crudo["exitosas"][mes], crudo["presentadas"][mes])

        filas = []
        for clave, rotulo in zip(FILAS, ROTULOS[ambito]):
            valores = [crudo[clave][mes] for mes, _ in MESES]
            if clave in FILAS_TASA:
                total = _division(
                    sum(crudo["exitosas"].values()),
                    sum(crudo["presentadas"].values()),
                )
            else:
                total = sum(valores, CERO)
            filas.append({
                "clave": clave,
                "rotulo": rotulo,
                "meses": valores,
                "meses_pct": [porcentaje(v) for v in valores],
                "total": total,
                "total_pct": porcentaje(total),
                "es_tasa": clave in FILAS_TASA,
                "es_monto": clave in FILAS_MONTO,
            })

        bloques.append({
            "ambito": ambito,
            "etiqueta": Ambito(ambito).label,
            "filas": filas,
        })

    return bloques


def _totales_proyectados(anio):
    filas = (
        ProyeccionMensual.objects
        .filter(anio=anio)
        .values("ambito")
        .annotate(total=Sum("monto"))
    )
    return {f["ambito"]: f["total"] or CERO for f in filas}


def _metas(anio):
    return {
        m.ambito: m.meta_gestiones
        for m in MetaAmbito.objects.filter(anio=anio)
    }


def semaforo(proporcion):
    """Verde ≥ 90%; amarillo 70%–89%; rojo < 70%.

    Es el criterio que la propia planilla deja escrito al pie del tablero.
    """
    if proporcion is None:
        return "gris"
    if proporcion >= Decimal("0.9"):
        return "verde"
    if proporcion >= Decimal("0.7"):
        return "amarillo"
    return "rojo"


def tablero_control(anio, gestiones=None):
    """Reproduce la hoja «Tablero de control»: una fila por ámbito y el total.

    Devuelve ``(filas, total)``.
    """
    bloques = {b["ambito"]: b for b in avance_mensual(anio, gestiones)}
    proyectado = _totales_proyectados(anio)
    metas = _metas(anio)

    filas = []
    for ambito in Ambito.values:
        indicadores = {f["clave"]: f["total"] for f in bloques[ambito]["filas"]}

        meta = metas.get(ambito, 0)
        gestionadas = indicadores["gestionadas"]
        exitosas = indicadores["exitosas"]
        esperado = proyectado.get(ambito, CERO)
        efectivo = indicadores["monto_adjudicado"]

        avance = _division(gestionadas, meta)
        # Ojo: sobre gestionadas, no sobre presentadas. Ver el docstring.
        tasa_exito = _division(exitosas, gestionadas)
        cumplimiento = _division(efectivo, esperado)

        filas.append({
            "ambito": ambito,
            "etiqueta": Ambito(ambito).label,
            "meta": meta,
            "gestiones": gestionadas,
            "avance": avance,
            "exitosos": exitosas,
            "tasa_exito": tasa_exito,
            "proyectado": esperado,
            "efectivo": efectivo,
            "cumplimiento": cumplimiento,
            "avance_pct": porcentaje(avance),
            "tasa_exito_pct": porcentaje(tasa_exito),
            "cumplimiento_pct": porcentaje(cumplimiento),
            "semaforo_avance": semaforo(avance),
            "semaforo_cumplimiento": semaforo(cumplimiento),
        })

    suma = lambda campo: sum((f[campo] for f in filas), CERO)  # noqa: E731
    meta_total = sum(f["meta"] for f in filas)
    gestiones_total = suma("gestiones")
    exitosos_total = suma("exitosos")
    proyectado_total = suma("proyectado")
    efectivo_total = suma("efectivo")

    avance_total = _division(gestiones_total, meta_total)
    cumplimiento_total = _division(efectivo_total, proyectado_total)

    total = {
        "etiqueta": "TOTAL",
        "meta": meta_total,
        "gestiones": gestiones_total,
        "avance": avance_total,
        "exitosos": exitosos_total,
        "tasa_exito": _division(exitosos_total, gestiones_total),
        "proyectado": proyectado_total,
        "efectivo": efectivo_total,
        "cumplimiento": cumplimiento_total,
        "avance_pct": porcentaje(avance_total),
        "tasa_exito_pct": porcentaje(_division(exitosos_total, gestiones_total)),
        "cumplimiento_pct": porcentaje(cumplimiento_total),
        "semaforo_avance": semaforo(avance_total),
        "semaforo_cumplimiento": semaforo(cumplimiento_total),
    }
    return filas, total


def proyeccion_por_mes(anio):
    """Reproduce la hoja «Proyección financiera»: ámbitos en filas, meses en
    columnas, con el total anual de cada uno y la fila de totales."""
    guardado = {
        (p.ambito, p.mes): p.monto
        for p in ProyeccionMensual.objects.filter(anio=anio)
    }

    filas = []
    for ambito in Ambito.values:
        montos = [guardado.get((ambito, mes), CERO) for mes, _ in MESES]
        filas.append({
            "ambito": ambito,
            "etiqueta": Ambito(ambito).label,
            "meses": montos,
            "total": sum(montos, CERO),
        })

    columnas = [
        sum((f["meses"][i] for f in filas), CERO) for i in range(len(MESES))
    ]
    total = {
        "etiqueta": "TOTAL INGRESOS PROYECTADOS",
        "meses": columnas,
        "total": sum(columnas, CERO),
    }
    return filas, total


def resumen(anio, gestiones=None):
    """Los cuatro números de cabecera del tablero."""
    filas, total = tablero_control(anio, gestiones)
    return {
        "filas": filas,
        "total": total,
        "gestiones": total["gestiones"],
        "meta": total["meta"],
        "avance": total["avance"],
        "exitosos": total["exitosos"],
        "proyectado": total["proyectado"],
        "efectivo": total["efectivo"],
        "cumplimiento": total["cumplimiento"],
    }


# Colores de los gráficos. Son los slots 1 y 2 de la paleta categórica ya
# validada que usa OTEC (``otec/graficos.py``): separación bajo daltonismo y
# contraste suficiente sobre la tarjeta blanca. El azul UPLA #009fe3 se queda
# como acento de interfaz —mide 2.97:1 contra blanco—, no como marca de datos.
COLOR_SERIE = "#2a78d6"
COLOR_SERIE_2 = "#eb6834"
COLOR_APAGADO = "#cbd5e1"

# Estados: reservados, siempre acompañados de rótulo, nunca solo color.
COLOR_ESTADO = {
    "verde": "#0ca30c",
    "amarillo": "#fab219",
    "rojo": "#d03b3b",
    "gris": "#94a3b8",
}


def anios_disponibles():
    """Años con datos, para el selector. Siempre incluye el año del archivo
    base para que el tablero no aparezca vacío antes de la primera carga."""
    vistos = set(Gestion.objects.values_list("anio", flat=True))
    vistos |= set(ProyeccionMensual.objects.values_list("anio", flat=True))
    vistos |= set(MetaAmbito.objects.values_list("anio", flat=True))
    vistos.add(2026)
    return sorted(vistos, reverse=True)

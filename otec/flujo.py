"""Cálculo del flujo de caja de OTEC.

Todo lo que en la planilla era fórmula se calcula acá: el resultado por línea,
la distribución UPLA/OTEC, el flujo mensual y el saldo de caja encadenado. Las
reglas se derivaron de las 35 filas del archivo, no se supusieron:

* ``resultado = ingreso − costos directos``
* ``UPLA = OTEC = ingreso × 15%``, o **× 50% si el curso es de autoaprendizaje**
  (lo dice el encabezado de la planilla y lo confirman todas las filas)
* ``saldo para la Universidad = max(0, resultado − UPLA − OTEC)`` — el piso en
  cero es lo que hace la planilla cuando los costos se comen el resultado
* ``total a la Universidad = saldo + UPLA``

Un desacuerdo interno del archivo, resuelto a favor de la regla documentada: la
hoja mensual reparte un 15% plano a todo, ignorando el 50% del autoaprendizaje
que sí aplica la hoja por actividad. Recalcular corrige esa diferencia.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from .models import CostoTransversal, LineaFinanciera, SupuestosFinancieros

CERO = Decimal("0")

MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre",
    12: "Diciembre",
}

# Ingreso "asegurado" = lo cobrado más lo contratado en firme.
CERTEZAS_ASEGURADAS = (
    LineaFinanciera.Certeza.EFECTIVO,
    LineaFinanciera.Certeza.CONFIRMADO,
)


def supuestos_de(anio):
    """Supuestos del año, o unos por defecto si nadie los ha cargado."""
    existentes = SupuestosFinancieros.objects.filter(anio=anio).first()
    return existentes or SupuestosFinancieros(anio=anio)


def resultado_linea(linea, supuestos):
    """Resultado y reparto de una línea. Devuelve un dict con todo desglosado."""
    ingreso = linea.ingreso_considerado or CERO
    costos = linea.costo.total if hasattr(linea, "costo") else CERO
    resultado = ingreso - costos

    pct = (
        supuestos.pct_autoaprendizaje if linea.autoaprendizaje
        else supuestos.pct_upla
    )
    pct_otec = (
        supuestos.pct_autoaprendizaje if linea.autoaprendizaje
        else supuestos.pct_otec
    )

    upla = ingreso * pct
    otec = ingreso * pct_otec
    saldo = max(CERO, resultado - upla - otec)

    return {
        "linea": linea,
        "ingreso": ingreso,
        "costos": costos,
        "resultado": resultado,
        "pct": pct,
        "upla": upla,
        "otec": otec,
        "saldo_universidad": saldo,
        "total_universidad": saldo + upla,
        "margen": (resultado / ingreso) if ingreso else None,
    }


def resultados(anio, supuestos=None):
    supuestos = supuestos or supuestos_de(anio)
    lineas = (
        LineaFinanciera.objects
        .select_related("costo", "institucion", "actividad")
        .order_by("codigo")
    )
    return [resultado_linea(l, supuestos) for l in lineas]


def _mes(fecha):
    return (fecha.year, fecha.month) if fecha else None


def flujo_mensual(anio, supuestos=None):
    """Flujo mes a mes con el saldo de caja encadenado.

    Los ingresos caen en su fecha de pago (la efectiva manda sobre la
    estimada); los costos directos en la suya; los transversales en su fecha de
    pago. El saldo solo se proyecta desde el mes de corte: antes de esa fecha
    los meses se muestran, pero arrastrar un saldo hacia atrás no significaría
    nada.
    """
    supuestos = supuestos or supuestos_de(anio)

    ingresos = defaultdict(lambda: defaultdict(lambda: CERO))
    upla_mes = defaultdict(lambda: CERO)
    otec_mes = defaultdict(lambda: CERO)

    for r in resultados(anio, supuestos):
        clave = _mes(r["linea"].fecha_ingreso)
        if not clave or clave[0] != anio:
            continue
        ingresos[clave][r["linea"].certeza] += r["ingreso"]
        upla_mes[clave] += r["upla"]
        otec_mes[clave] += r["otec"]

    directos = defaultdict(lambda: CERO)
    for linea in LineaFinanciera.objects.select_related("costo"):
        costo = getattr(linea, "costo", None)
        if not costo:
            continue
        clave = _mes(costo.fecha_egreso)
        if clave and clave[0] == anio:
            directos[clave] += costo.total

    transversales = defaultdict(lambda: CERO)
    for c in CostoTransversal.objects.filter(incluir_en_flujo=True):
        clave = _mes(c.fecha_pago)
        if clave and clave[0] == anio:
            transversales[clave] += c.monto

    mes_corte = supuestos.fecha_corte.month if supuestos.fecha_corte else 1
    saldo = supuestos.saldo_inicial or CERO

    filas = []
    for mes in range(1, 13):
        clave = (anio, mes)
        por_certeza = {
            c.value: ingresos[clave].get(c.value, CERO)
            for c in LineaFinanciera.Certeza
        }
        total_ingresos = sum(por_certeza.values())
        cd, ct = directos[clave], transversales[clave]
        operacionales = cd + ct
        resultado_op = total_ingresos - operacionales
        upla, otec = upla_mes[clave], otec_mes[clave]
        saldo_universidad = resultado_op - upla - otec

        # La transferencia a UPLA se hace al recibir los pagos, así que solo
        # sale de caja desde el mes de corte en adelante.
        transferencia = upla if mes >= mes_corte else CERO
        egresos = operacionales + transferencia
        neto = total_ingresos - egresos

        proyectado = mes >= mes_corte
        inicial = saldo if proyectado else None
        if proyectado:
            saldo = saldo + neto

        filas.append({
            "mes": mes,
            "nombre": MESES[mes],
            "ingresos": por_certeza,
            "total_ingresos": total_ingresos,
            "costos_directos": cd,
            "costos_transversales": ct,
            "costos_operacionales": operacionales,
            "resultado_operacional": resultado_op,
            "upla": upla,
            "otec": otec,
            "saldo_universidad": saldo_universidad,
            "transferencia_upla": transferencia,
            "egresos": egresos,
            "neto": neto,
            "saldo_inicial": inicial,
            "saldo_final": saldo if proyectado else None,
            "proyectado": proyectado,
            "bajo_minimo": proyectado and saldo < (supuestos.saldo_minimo or CERO),
        })

    return filas


def resumen(anio, supuestos=None):
    """Los indicadores del resumen ejecutivo, recalculados."""
    supuestos = supuestos or supuestos_de(anio)
    filas = flujo_mensual(anio, supuestos)
    rs = resultados(anio, supuestos)

    por_certeza = {c.value: CERO for c in LineaFinanciera.Certeza}
    for fila in filas:
        for clave, valor in fila["ingresos"].items():
            por_certeza[clave] += valor

    total = sum(por_certeza.values())
    asegurados = sum(por_certeza[c] for c in CERTEZAS_ASEGURADAS)
    proyectados = filas[-1]["saldo_final"] if filas else None
    # El último mes con saldo proyectado, que puede no ser diciembre.
    for fila in reversed(filas):
        if fila["saldo_final"] is not None:
            proyectados = fila["saldo_final"]
            break

    return {
        "anio": anio,
        "supuestos": supuestos,
        "por_certeza": por_certeza,
        "total_ingresos": total,
        "asegurados": asegurados,
        "pct_asegurados": (asegurados / total * 100) if total else None,
        "costos_operacionales": sum(f["costos_operacionales"] for f in filas),
        "costos_directos": sum(f["costos_directos"] for f in filas),
        "costos_transversales": sum(f["costos_transversales"] for f in filas),
        "upla": sum(r["upla"] for r in rs),
        "otec": sum(r["otec"] for r in rs),
        "saldo_universidad": sum(r["saldo_universidad"] for r in rs),
        "total_universidad": sum(r["total_universidad"] for r in rs),
        "saldo_final": proyectados,
        "meses_bajo_minimo": [f for f in filas if f["bajo_minimo"]],
        "filas": filas,
        "resultados": rs,
    }

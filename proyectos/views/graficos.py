"""Vistas de gráficos para seguimiento de proyectos.

Dos niveles:
  - graficos_proyectos: panel de cartera (todos los proyectos visibles).
  - graficos_proyecto: parcial HTMX con gráficos de un proyecto concreto.

Se calca el patrón de `analisis.views.graficos_informes`: los datos se arman
en Python y se entregan al template para pintarlos con Chart.js vía json_script.
No requiere modelos ni migraciones nuevas.
"""

from collections import defaultdict
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from ..models import Egreso, Proyecto
from .permisos import es_jefe
from .utils import anio_seleccionado

# Paleta institucional (coincide con core/base.html)
ESTADOS_ORDEN = ['PLANIFICADO', 'EN_EJECUCION', 'FINALIZADO', 'SUSPENDIDO']
ESTADOS_COLORES = {
    'PLANIFICADO': '#6c757d',
    'EN_EJECUCION': '#009fe3',
    'FINALIZADO': '#198754',
    'SUSPENDIDO': '#dc3545',
}
ESTADOS_LABEL = dict(Proyecto.ESTADOS)


def _f(valor):
    """Decimal/None -> float para serializar a JSON."""
    if valor is None:
        return 0.0
    if isinstance(valor, Decimal):
        return float(valor)
    return float(valor)


def _cumplimiento_objetivo(objetivo):
    """Cumplimiento de un objetivo: promedio de sus resultados ponderado por
    presupuesto (mismo criterio que Proyecto.cumplimiento y Resultado.cumplimiento)."""
    resultados = list(objetivo.resultados.filter(eliminado=False))
    if not resultados:
        return Decimal('0')
    pesos = sum((r.presupuesto_asignado for r in resultados), Decimal('0'))
    if pesos == 0:
        return (
            sum((r.cumplimiento for r in resultados), Decimal('0')) / len(resultados)
        ).quantize(Decimal('0.01'))
    ponderado = sum(
        (r.cumplimiento * r.presupuesto_asignado for r in resultados),
        Decimal('0'),
    )
    return (ponderado / pesos).quantize(Decimal('0.01'))


# =========================
# NIVEL 1 — PANEL DE CARTERA
# =========================

@login_required
def graficos_proyectos(request):
    user = request.user
    jefe = es_jefe(user)

    qs = Proyecto.objects.with_resumen().prefetch_related(
        'objetivos__resultados__actividades'
    ).order_by('-fecha_creacion')
    if not jefe:
        qs = qs.filter(responsable=user)

    proyectos = list(qs)

    # ===== Donut: proyectos por estado =====
    conteo_estado = {e: 0 for e in ESTADOS_ORDEN}
    for p in proyectos:
        if p.estado in conteo_estado:
            conteo_estado[p.estado] += 1

    datos_estado = {
        'labels': [ESTADOS_LABEL.get(e, e) for e in ESTADOS_ORDEN],
        'data': [conteo_estado[e] for e in ESTADOS_ORDEN],
        'colors': [ESTADOS_COLORES[e] for e in ESTADOS_ORDEN],
    }

    # ===== Barras: presupuesto vs gastado por tipo =====
    tipo_pres = defaultdict(Decimal)
    tipo_gasto = defaultdict(Decimal)
    for p in proyectos:
        etq = p.get_tipo_display()
        tipo_pres[etq] += p.presupuesto_total or Decimal('0')
        tipo_gasto[etq] += p.gastos_total or Decimal('0')

    tipos = sorted(tipo_pres.keys(), key=lambda t: -tipo_pres[t])
    datos_tipo = {
        'labels': tipos,
        'datasets': [
            {
                'label': 'Presupuesto',
                'data': [_f(tipo_pres[t]) for t in tipos],
                'backgroundColor': '#009fe3',
                'borderRadius': 6,
                'maxBarThickness': 40,
            },
            {
                'label': 'Gastado',
                'data': [_f(tipo_gasto[t]) for t in tipos],
                'backgroundColor': '#f59e0b',
                'borderRadius': 6,
                'maxBarThickness': 40,
            },
        ],
    }

    # ===== Barra apilada: ejecución por proyecto (top 12 por presupuesto) =====
    top = sorted(proyectos, key=lambda p: -(p.presupuesto_total or Decimal('0')))[:12]
    ejec_labels = [p.nombre[:28] + ('…' if len(p.nombre) > 28 else '') for p in top]
    datos_ejecucion = {
        'labels': ejec_labels,
        'datasets': [
            {
                'label': 'Pagado',
                'data': [_f(p.gastos_pagados) for p in top],
                'backgroundColor': '#198754',
                'borderRadius': 4,
                'maxBarThickness': 30,
            },
            {
                'label': 'Comprometido',
                'data': [_f(p.gastos_comprometidos) for p in top],
                'backgroundColor': '#f59e0b',
                'borderRadius': 4,
                'maxBarThickness': 30,
            },
            {
                'label': 'Disponible',
                'data': [_f(max(p.disponible_para_gastar, Decimal('0'))) for p in top],
                'backgroundColor': '#e2e8f0',
                'borderRadius': 4,
                'maxBarThickness': 30,
            },
        ],
    }

    # ===== Scatter: avance (cumplimiento) vs % gastado =====
    puntos = []
    for p in proyectos:
        puntos.append({
            'x': round(_f(p.cumplimiento), 1),
            'y': round(_f(p.porcentaje_gastado), 1),
            'nombre': p.nombre,
            'estado': p.estado,
        })
    datos_avance_gasto = {
        'datasets': [{
            'label': 'Proyectos',
            'data': puntos,
            'backgroundColor': [ESTADOS_COLORES.get(pt['estado'], '#94a3b8') for pt in puntos],
            'pointRadius': 7,
            'pointHoverRadius': 9,
        }],
    }

    # ===== Stats de cabecera =====
    stats = {
        'total': len(proyectos),
        'en_ejecucion': conteo_estado['EN_EJECUCION'],
        'finalizados': conteo_estado['FINALIZADO'],
        'atrasados': sum(1 for p in proyectos if p.atrasado),
        'presupuesto_total': _f(sum((p.presupuesto_total or Decimal('0')) for p in proyectos)),
        'ejecutado_total': _f(sum((p.gastos_total or Decimal('0')) for p in proyectos)),
    }

    # ===== Tabla resumen =====
    resumen = [{
        'nombre': p.nombre,
        'estado': p.estado,
        'estado_label': p.get_estado_display(),
        'presupuesto': _f(p.presupuesto_total),
        'ejecutado': _f(p.gastos_total),
        'pct_gastado': round(_f(p.porcentaje_gastado), 1),
        'cumplimiento': round(_f(p.cumplimiento), 1),
        'atrasado': p.atrasado,
    } for p in proyectos]

    return render(request, 'proyectos/graficos_proyectos.html', {
        'stats': stats,
        'datos_estado': datos_estado,
        'datos_tipo': datos_tipo,
        'datos_ejecucion': datos_ejecucion,
        'datos_avance_gasto': datos_avance_gasto,
        'resumen': resumen,
        'hay_datos': bool(proyectos),
        'es_jefe': jefe,
    })


# =========================
# NIVEL 2 — GRÁFICOS POR PROYECTO (parcial HTMX)
# =========================

@login_required
def graficos_proyecto(request, pk):
    """Gráficos de un proyecto, completos o acotados a un año.

    Con un año elegido, todo lo que sea dinero pasa a ser el de ese año. El
    avance físico no: `Actividad.cumplimiento` es una sola cifra para toda la
    vida del proyecto, así que se sigue mostrando el global y el subtítulo lo
    dice, en vez de fingir un avance anual que no existe en los datos.
    """
    proyecto = get_object_or_404(
        Proyecto.objects.prefetch_related('objetivos__resultados__actividades'),
        pk=pk,
    )
    anio = anio_seleccionado(request, proyecto)

    if anio:
        presupuesto = anio.presupuesto_total
        corriente_total, capital_total = anio.presupuesto_corriente, anio.presupuesto_capital
        asignado = anio.asignado_a_objetivos
        corriente_asignado, capital_asignado = anio.asignado_corriente, anio.asignado_capital
        corriente_libre, capital_libre = anio.sin_asignar_corriente, anio.sin_asignar_capital
        comprometido, pagado = anio.comprometido, anio.pagado
        disponible = presupuesto - anio.gastos_total
        egresos = proyecto.egresos.filter(
            eliminado=False, plan_de_gasto__anio=anio.anio_calendario
        )
    else:
        presupuesto = proyecto.presupuesto_total
        corriente_total, capital_total = (proyecto.presupuesto_corriente,
                                          proyecto.presupuesto_capital)
        asignado = proyecto.presupuesto_asignado
        corriente_asignado, capital_asignado = (proyecto.corriente_asignado,
                                                proyecto.capital_asignado)
        corriente_libre, capital_libre = (proyecto.corriente_disponible,
                                          proyecto.capital_disponible)
        comprometido, pagado = proyecto.gastos_comprometidos, proyecto.gastos_pagados
        disponible = proyecto.disponible_para_gastar
        egresos = proyecto.egresos.filter(eliminado=False)

    # ===== Cascada de presupuesto (barras horizontales) =====
    cascada = {
        'labels': ['Total', 'Asignado', 'Comprometido', 'Ejecutado', 'Disponible'],
        'data': [
            _f(presupuesto), _f(asignado), _f(comprometido), _f(pagado),
            _f(max(disponible, Decimal('0'))),
        ],
        'colors': ['#0f172a', '#1d4ed8', '#f59e0b', '#198754', '#94a3b8'],
    }

    # ===== Corriente vs Capital (uso: asignado vs disponible) =====
    corriente_capital = {
        'corriente': {
            'labels': ['Asignado', 'Disponible'],
            'data': [_f(corriente_asignado), _f(max(corriente_libre, Decimal('0')))],
            'colors': ['#1d4ed8', '#dbeafe'],
        },
        'capital': {
            'labels': ['Asignado', 'Disponible'],
            'data': [_f(capital_asignado), _f(max(capital_libre, Decimal('0')))],
            'colors': ['#7c3aed', '#ede9fe'],
        },
    }

    # ===== Avance por objetivo =====
    # El avance es del proyecto entero (no hay cumplimiento por año); lo que sí
    # cambia con el año es el presupuesto de cada objetivo.
    obj_labels, obj_avance, obj_pres = [], [], []
    for i, objetivo in enumerate(proyecto.objetivos.all(), start=1):
        etq = objetivo.descripcion or f'Objetivo {i}'
        obj_labels.append(f'OE{i}: ' + (etq[:34] + ('…' if len(etq) > 34 else '')))
        obj_avance.append(round(_f(_cumplimiento_objetivo(objetivo)), 1))
        if anio:
            fila = objetivo.presupuesto_del_anio(anio)
            obj_pres.append(_f(fila.presupuesto_total if fila else Decimal('0')))
        else:
            obj_pres.append(_f(objetivo.presupuesto_asignado))
    avance_objetivos = {
        'labels': obj_labels,
        'avance': obj_avance,
        'presupuesto': obj_pres,
    }

    # ===== Gastos por transferencia =====
    trans_totales = defaultdict(Decimal)
    for egreso in egresos:
        if egreso.plan_de_gasto_id:
            nombre = str(egreso.plan_de_gasto.transferencia)
        else:
            nombre = egreso.get_tipo_display()
        if egreso.tipo == Egreso.TIPO_HONORARIO:
            monto = egreso.monto_total
        else:
            monto = egreso.total_con_iva
        trans_totales[nombre] += monto or Decimal('0')

    trans_orden = sorted(trans_totales.keys(), key=lambda t: -trans_totales[t])
    gastos_transferencia = {
        'labels': trans_orden,
        'data': [_f(trans_totales[t]) for t in trans_orden],
    }

    # ===== Comprometido vs Pagado (donut) =====
    comprometido_pagado = {
        'labels': ['Pagado', 'Comprometido'],
        'data': [_f(pagado), _f(comprometido)],
        'colors': ['#198754', '#f59e0b'],
    }

    return render(request, 'proyectos/partials/graficos_proyecto.html', {
        'proyecto': proyecto,
        'anio_sel': anio,
        'cascada': cascada,
        'corriente_capital': corriente_capital,
        'avance_objetivos': avance_objetivos,
        'gastos_transferencia': gastos_transferencia,
        'comprometido_pagado': comprometido_pagado,
        'hay_gastos': bool(trans_totales),
    })

"""Reparto del presupuesto de un resultado por año.

El último escalón del reparto anual. Debajo están las actividades, que no se
reparten por año: pueden cambiar mientras el resultado se cumpla, así que lo que
se compromete anualmente es el resultado.

El techo de cada fila no es el año del proyecto sino lo que ese año le dio a su
objetivo, que es de donde cuelga el resultado.
"""

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from ..models import CAPITAL, CORRIENTE, PresupuestoResultadoAnual, Resultado
from ..numeros import pesos
from .permisos import usuario_es_responsable
from .utils import _to_decimal, detalle_resultado, disparar


def _filas(resultado, propuestas=None):
    """Una fila por año en que **su objetivo** tenga presupuesto.

    Se recorren los años del objetivo y no los del proyecto: un resultado no
    puede recibir plata en un año en que su objetivo no tiene nada, así que
    ofrecer esa fila sólo llevaría a un error al guardar.
    """
    asignadas = {a.anio_id: a for a in resultado.presupuestos_anuales.all()}
    escritos = {a.pk: m for a, m in (propuestas or {}).items()}
    filas = []
    for del_objetivo in resultado.objetivo.presupuestos_anuales.select_related("anio"):
        anio = del_objetivo.anio
        asignacion = asignadas.get(anio.pk)
        if anio.pk in escritos:
            corriente, capital = escritos[anio.pk]
        elif asignacion:
            corriente, capital = (asignacion.presupuesto_corriente,
                                  asignacion.presupuesto_capital)
        else:
            corriente = capital = Decimal("0")
        filas.append({
            "anio": anio,
            "del_objetivo": del_objetivo,
            "asignacion": asignacion,
            "corriente": corriente,
            "capital": capital,
        })
    return filas


def _responder(request, resultado, propuestas=None, **extra):
    contexto = {
        "resultado": resultado,
        "filas": _filas(resultado, propuestas),
    }
    contexto.update(extra)
    return render(
        request,
        "proyectos/partials/resultado_presupuesto_anual.html",
        contexto,
    )


@login_required
def presupuesto_resultado_anual(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")
    return _responder(request, resultado)


def _validar(resultado, propuestas):
    """Revisa el reparto completo del resultado. `propuestas` es {anio: (c, k)}."""
    objetivo = resultado.objetivo
    errores = []
    for anio, montos in propuestas.items():
        del_objetivo = objetivo.presupuesto_del_anio(anio)
        for etiqueta, campo, naturaleza, propuesto in (
            ("corriente", "presupuesto_corriente", CORRIENTE, montos[0]),
            ("capital", "presupuesto_capital", CAPITAL, montos[1]),
        ):
            if propuesto < 0:
                errores.append(
                    f"{anio.etiqueta}: el presupuesto {etiqueta} no puede ser negativo."
                )
                continue

            tope_objetivo = (getattr(del_objetivo, campo) or Decimal("0")
                             if del_objetivo else Decimal("0"))
            if propuesto and not tope_objetivo:
                errores.append(
                    f"{anio.etiqueta} ({anio.anio_calendario}): el objetivo no tiene "
                    f"presupuesto {etiqueta} ese año. Repártelo primero en el objetivo."
                )
                continue

            usado_por_otros = PresupuestoResultadoAnual.objects.filter(
                anio=anio, resultado__objetivo=objetivo, resultado__eliminado=False,
            ).exclude(resultado=resultado).aggregate(
                total=Sum(campo)
            )["total"] or Decimal("0")

            if usado_por_otros + propuesto > tope_objetivo:
                errores.append(
                    f"{anio.etiqueta}: el objetivo tiene {pesos(tope_objetivo)} "
                    f"{etiqueta} ese año y los demás resultados ya usan "
                    f"{pesos(usado_por_otros)}, así que éste puede llegar hasta "
                    f"{pesos(tope_objetivo - usado_por_otros)}."
                )

            planificado = resultado.planificado_en(anio.anio_calendario, naturaleza)
            if propuesto < planificado:
                errores.append(
                    f"{anio.etiqueta}: sus planes de gasto {etiqueta} ya suman "
                    f"{pesos(planificado)}, así que no puede quedar en {pesos(propuesto)}."
                )
    return errores


@login_required
@require_POST
def guardar_presupuesto_resultado_anual(request, pk):
    """Guarda el reparto del resultado en todos sus años de una vez."""
    resultado = get_object_or_404(Resultado, pk=pk)
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    propuestas = {}
    for del_objetivo in resultado.objetivo.presupuestos_anuales.select_related("anio"):
        anio = del_objetivo.anio
        # Sólo los años que vinieron en el envío: uno ausente no puede
        # interpretarse como "déjalo en cero" y borrar su asignación.
        if f"corriente_{anio.pk}" not in request.POST:
            continue
        propuestas[anio] = (
            _to_decimal(request.POST[f"corriente_{anio.pk}"]),
            _to_decimal(request.POST.get(f"capital_{anio.pk}") or 0),
        )

    errores = _validar(resultado, propuestas)
    if errores:
        return _responder(request, resultado, error=" ".join(errores),
                          propuestas=propuestas)

    with transaction.atomic():
        for anio, (corriente, capital) in propuestas.items():
            fila = resultado.presupuesto_del_anio(anio)
            if fila is None:
                if not corriente and not capital:
                    continue
                fila = PresupuestoResultadoAnual(
                    resultado=resultado, anio=anio, creado_por=request.user,
                )
            fila.presupuesto_corriente = corriente
            fila.presupuesto_capital = capital
            fila.actualizado_por = request.user
            fila.save()

    response = _responder(request, resultado)
    return disparar(
        response,
        estructuraActualizada=True,
        resultadoActualizado=detalle_resultado(resultado),
        objetivoActualizado={"objetivo_id": resultado.objetivo_id},
        guardado="Reparto del resultado guardado.",
    )

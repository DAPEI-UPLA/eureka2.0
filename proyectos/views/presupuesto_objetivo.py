"""Reparto del presupuesto de un objetivo por año.

Un escalón bajo `presupuesto_anual`: el proyecto reparte su plata por año, y
dentro de cada año se reparte entre los objetivos. Cuando el proyecto tiene
años, el total del objetivo deja de editarse y pasa a ser sólo lectura — es la
suma de lo repartido, no una cifra que se decida por su cuenta.
"""

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from ..models import (
    CAPITAL,
    CORRIENTE,
    ObjetivoEspecifico,
    PresupuestoObjetivoAnual,
)
from ..numeros import pesos
from .permisos import usuario_es_responsable
from .utils import _to_decimal, disparar


def _filas(objetivo, propuestas=None):
    """Una fila por año del proyecto, tenga o no asignación todavía.

    Se arma sobre los años del proyecto y no sobre las asignaciones existentes
    porque la pantalla tiene que mostrar también los años en blanco: son
    justamente los que falta repartir.

    Tras un error se repintan los montos escritos (`propuestas`) y no los
    guardados: ver el error junto a las cifras viejas hace pensar que habla de
    otra cosa.
    """
    asignadas = {a.anio_id: a for a in objetivo.presupuestos_anuales.all()}
    escritos = {a.pk: m for a, m in (propuestas or {}).items()}
    filas = []
    for anio in objetivo.proyecto.presupuestos_anuales.all():
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
            "asignacion": asignacion,
            "corriente": corriente,
            "capital": capital,
        })
    return filas


def _contexto(objetivo, propuestas=None, **extra):
    contexto = {
        "objetivo": objetivo,
        "filas": _filas(objetivo, propuestas),
        "puede_editar": True,
    }
    contexto.update(extra)
    return contexto


def _responder(request, objetivo, propuestas=None, **extra):
    return render(
        request,
        "proyectos/partials/objetivo_presupuesto_anual.html",
        _contexto(objetivo, propuestas, **extra),
    )


@login_required
def presupuesto_objetivo_anual(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")
    return _responder(request, objetivo)


def _validar(objetivo, propuestas):
    """Revisa el reparto completo del objetivo. `propuestas` es {anio: (c, k)}."""
    errores = []
    for anio, montos in propuestas.items():
        for etiqueta, campo, naturaleza, propuesto in (
            ("corriente", "presupuesto_corriente", CORRIENTE, montos[0]),
            ("capital", "presupuesto_capital", CAPITAL, montos[1]),
        ):
            if propuesto < 0:
                errores.append(
                    f"{anio.etiqueta}: el presupuesto {etiqueta} no puede ser negativo."
                )
                continue

            del_anio = getattr(anio, campo) or Decimal("0")
            if propuesto and not del_anio:
                # El caso que más confunde: el año existe pero está en cero
                # porque el proyecto no repartió nada ahí todavía. Sin decirlo,
                # el mensaje de tope habla de un $0 que parece un error del
                # sistema y no una tarea pendiente.
                errores.append(
                    f"{anio.etiqueta} ({anio.anio_calendario}) no tiene presupuesto "
                    f"{etiqueta} en el proyecto. Reparte primero el presupuesto del "
                    f"proyecto en «Presupuesto por año»."
                )
                continue

            usado_por_otros = PresupuestoObjetivoAnual.objects.filter(
                anio=anio, objetivo__eliminado=False,
            ).exclude(objetivo=objetivo).aggregate(
                total=Sum(campo)
            )["total"] or Decimal("0")

            if usado_por_otros + propuesto > del_anio:
                errores.append(
                    f"{anio.etiqueta}: el año tiene {pesos(del_anio)} {etiqueta} y los "
                    f"demás objetivos ya usan {pesos(usado_por_otros)}, así que este "
                    f"objetivo puede llegar hasta {pesos(del_anio - usado_por_otros)}."
                )

            planificado = objetivo.planificado_en(anio.anio_calendario, naturaleza)
            if propuesto < planificado:
                errores.append(
                    f"{anio.etiqueta}: sus planes de gasto {etiqueta} ya suman "
                    f"{pesos(planificado)}, así que no puede quedar en {pesos(propuesto)}."
                )
    return errores


@login_required
@require_POST
def guardar_presupuesto_objetivo_anual(request, pk):
    """Guarda el reparto del objetivo en todos los años de una vez.

    Se guardan juntos por la misma razón que en el proyecto: mover plata de un
    año a otro son dos cambios que sólo son válidos si viajan en el mismo
    movimiento.
    """
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    propuestas = {}
    for anio in objetivo.proyecto.presupuestos_anuales.all():
        # Sólo los años que vinieron en el envío: uno ausente no puede
        # interpretarse como "déjalo en cero" y borrar su asignación.
        if f"corriente_{anio.pk}" not in request.POST:
            continue
        propuestas[anio] = (
            _to_decimal(request.POST[f"corriente_{anio.pk}"]),
            _to_decimal(request.POST.get(f"capital_{anio.pk}") or 0),
        )

    errores = _validar(objetivo, propuestas)
    if errores:
        return _responder(request, objetivo, error=" ".join(errores),
                          propuestas=propuestas)

    with transaction.atomic():
        for anio, (corriente, capital) in propuestas.items():
            fila = objetivo.presupuesto_del_anio(anio)
            if fila is None:
                # Un año en cero que nunca se tocó no deja fila: no hay nada que
                # repartir y sólo ensuciaría la pantalla.
                if not corriente and not capital:
                    continue
                fila = PresupuestoObjetivoAnual(
                    objetivo=objetivo, anio=anio, creado_por=request.user,
                )
            fila.presupuesto_corriente = corriente
            fila.presupuesto_capital = capital
            fila.actualizado_por = request.user
            fila.save()

    response = _responder(request, objetivo)
    return disparar(
        response,
        estructuraActualizada=True,
        objetivoActualizado={"objetivo_id": objetivo.pk},
        guardado="Reparto del objetivo guardado.",
    )

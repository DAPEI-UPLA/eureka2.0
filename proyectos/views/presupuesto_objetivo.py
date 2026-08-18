"""Reparto del presupuesto de un objetivo por año.

Un escalón bajo `presupuesto_anual`: el proyecto reparte su plata por año, y
dentro de cada año se reparte entre los objetivos. Cuando el proyecto tiene
años, el total del objetivo deja de editarse y pasa a ser sólo lectura — es la
suma de lo repartido, no una cifra que se decida por su cuenta.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from ..models import ObjetivoEspecifico, PresupuestoObjetivoAnual
from .permisos import usuario_es_responsable
from .utils import _to_decimal, disparar


def _filas(objetivo):
    """Una fila por año del proyecto, tenga o no asignación todavía.

    Se arma sobre los años del proyecto y no sobre las asignaciones existentes
    porque la pantalla tiene que mostrar también los años en blanco: son
    justamente los que falta repartir.
    """
    asignadas = {a.anio_id: a for a in objetivo.presupuestos_anuales.all()}
    return [
        {"anio": anio, "asignacion": asignadas.get(anio.pk)}
        for anio in objetivo.proyecto.presupuestos_anuales.all()
    ]


def _contexto(objetivo, **extra):
    contexto = {
        "objetivo": objetivo,
        "filas": _filas(objetivo),
        "puede_editar": True,
    }
    contexto.update(extra)
    return contexto


def _responder(request, objetivo, **extra):
    return render(
        request,
        "proyectos/partials/objetivo_presupuesto_anual.html",
        _contexto(objetivo, **extra),
    )


@login_required
def presupuesto_objetivo_anual(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")
    return _responder(request, objetivo)


@login_required
@require_POST
def guardar_presupuesto_objetivo_anual(request, pk):
    """Guarda la asignación de un objetivo para un año.

    La fila se crea al guardarla por primera vez, no al abrir la pantalla: un
    objetivo que no participa de un año no tiene por qué dejar una asignación
    en cero dando vueltas.
    """
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    anio = objetivo.proyecto.presupuestos_anuales.filter(
        pk=request.POST.get("anio")
    ).first()
    if anio is None:
        return _responder(request, objetivo, error="Ese año no es del proyecto.")

    asignacion = objetivo.presupuesto_del_anio(anio) or PresupuestoObjetivoAnual(
        objetivo=objetivo, anio=anio, creado_por=request.user,
    )
    asignacion.presupuesto_corriente = _to_decimal(
        request.POST.get("presupuesto_corriente")
    )
    asignacion.presupuesto_capital = _to_decimal(
        request.POST.get("presupuesto_capital")
    )
    asignacion.actualizado_por = request.user

    try:
        asignacion.full_clean()
        asignacion.save()
    except ValidationError as error:
        mensajes = [m for msgs in error.message_dict.values() for m in msgs]
        return _responder(
            request, objetivo,
            error=" ".join(mensajes),
            anio_con_error=anio.pk,
        )

    response = _responder(request, objetivo)
    return disparar(
        response,
        estructuraActualizada=True,
        objetivoActualizado={"objetivo_id": objetivo.pk},
        guardado=f"Presupuesto de {anio.etiqueta} guardado.",
    )

"""Reparto del presupuesto de un resultado por año.

El último escalón del reparto anual. Debajo están las actividades, que no se
reparten por año: pueden cambiar mientras el resultado se cumpla, así que lo que
se compromete anualmente es el resultado.

El techo de cada fila no es el año del proyecto sino lo que ese año le dio a su
objetivo, que es de donde cuelga el resultado.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from ..models import PresupuestoResultadoAnual, Resultado
from .permisos import usuario_es_responsable
from .utils import _to_decimal, detalle_resultado, disparar


def _filas(resultado):
    """Una fila por año en que **su objetivo** tenga presupuesto.

    Se recorren los años del objetivo y no los del proyecto: un resultado no
    puede recibir plata en un año en que su objetivo no tiene nada, así que
    ofrecer esa fila sólo llevaría a un error al guardar.
    """
    asignadas = {a.anio_id: a for a in resultado.presupuestos_anuales.all()}
    return [
        {
            "anio": del_objetivo.anio,
            "del_objetivo": del_objetivo,
            "asignacion": asignadas.get(del_objetivo.anio_id),
        }
        for del_objetivo in resultado.objetivo.presupuestos_anuales.select_related("anio")
    ]


def _responder(request, resultado, **extra):
    contexto = {
        "resultado": resultado,
        "filas": _filas(resultado),
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


@login_required
@require_POST
def guardar_presupuesto_resultado_anual(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)
    proyecto = resultado.objetivo.proyecto
    if not usuario_es_responsable(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    anio = proyecto.presupuestos_anuales.filter(pk=request.POST.get("anio")).first()
    if anio is None:
        return _responder(request, resultado, error="Ese año no es del proyecto.")

    asignacion = resultado.presupuesto_del_anio(anio) or PresupuestoResultadoAnual(
        resultado=resultado, anio=anio, creado_por=request.user,
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
            request, resultado,
            error=" ".join(mensajes),
            anio_con_error=anio.pk,
        )

    response = _responder(request, resultado)
    return disparar(
        response,
        estructuraActualizada=True,
        resultadoActualizado=detalle_resultado(resultado),
        objetivoActualizado={"objetivo_id": resultado.objetivo_id},
        guardado=f"Presupuesto de {anio.etiqueta} guardado.",
    )

"""
Reordenamiento de objetivos, resultados y actividades.

Antes, si algo se cargaba en el orden equivocado había que borrarlo y volver a
escribirlo. Aquí cada elemento puede subir o bajar una posición dentro de su
padre; el campo `orden` se renumera de forma correlativa en cada movimiento,
así que se autocorrige aunque venga con valores repetidos o en cero.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from ..models import Actividad, ObjetivoEspecifico, Resultado
from .permisos import usuario_es_responsable
from .utils import disparar

DIRECCIONES = {"subir": -1, "bajar": 1}


def _mover(modelo, objeto, hermanos, direccion):
    """Intercambia la posición de `objeto` con su vecino. Devuelve True si se movió."""
    paso = DIRECCIONES[direccion]
    ids = list(hermanos.values_list("pk", flat=True))
    if objeto.pk not in ids:
        return False

    actual = ids.index(objeto.pk)
    destino = actual + paso
    if destino < 0 or destino >= len(ids):
        return False

    ids[actual], ids[destino] = ids[destino], ids[actual]
    for posicion, pk in enumerate(ids, start=1):
        modelo.objects.filter(pk=pk).update(orden=posicion)
    return True


@login_required
@require_POST
def mover_objetivo(request, pk, direccion):
    if direccion not in DIRECCIONES:
        return HttpResponseBadRequest("Dirección inválida")

    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    proyecto = objetivo.proyecto
    if not usuario_es_responsable(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    movido = _mover(ObjetivoEspecifico, objetivo, proyecto.objetivos.all(), direccion)

    response = render(request, "proyectos/partials/objetivos_lista.html", {
        "proyecto": proyecto,
        "es_encargado": True,
    })
    if movido:
        disparar(response, guardado="Orden actualizado")
    return response


@login_required
@require_POST
def mover_resultado(request, pk, direccion):
    if direccion not in DIRECCIONES:
        return HttpResponseBadRequest("Dirección inválida")

    resultado = get_object_or_404(Resultado, pk=pk)
    objetivo = resultado.objetivo
    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    movido = _mover(Resultado, resultado, objetivo.resultados.all(), direccion)

    response = render(request, "proyectos/partials/resultados_lista.html", {
        "objetivo": objetivo,
        "es_encargado": True,
    })
    if movido:
        disparar(response, guardado="Orden actualizado")
    return response


@login_required
@require_POST
def mover_actividad(request, pk, direccion):
    if direccion not in DIRECCIONES:
        return HttpResponseBadRequest("Dirección inválida")

    actividad = get_object_or_404(Actividad, pk=pk)
    resultado = actividad.resultado
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    movido = _mover(Actividad, actividad, resultado.actividades.all(), direccion)

    response = render(request, "proyectos/partials/actividades_lista.html", {
        "actividades": resultado.actividades.all(),
    })
    if movido:
        disparar(response, guardado="Orden actualizado")
    return response

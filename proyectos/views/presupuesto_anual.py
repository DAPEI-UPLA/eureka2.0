"""Reparto del presupuesto del proyecto por año calendario.

Un proyecto de 36 meses no tiene un presupuesto, tiene tres: uno por año, que
es como se transfiere y como se rinde. Estas vistas son el CRUD de ese reparto
y el selector que filtra el detalle del proyecto por año.

Sigue el patrón HTMX del resto del módulo: cada mutación devuelve la lista
completa ya repintada y publica `estructuraActualizada` para que el dashboard y
los gráficos se enteren.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Max
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from ..models import PresupuestoAnual, Proyecto
from .permisos import es_jefe, usuario_es_responsable
from .utils import _to_decimal, disparar


def _puede_editar(user, proyecto):
    """El reparto anual lo carga el equipo del proyecto; la jefatura también.

    Es plata del proyecto, no de un objetivo, así que no basta con ser
    responsable de una parte: o llevas el proyecto o llevas la cartera.
    """
    return usuario_es_responsable(user, proyecto) or es_jefe(user)


def _contexto(proyecto, user, **extra):
    contexto = {
        "proyecto": proyecto,
        "anios": proyecto.presupuestos_anuales.all(),
        "puede_editar": _puede_editar(user, proyecto),
    }
    contexto.update(extra)
    return contexto


def _responder(request, proyecto, **extra):
    return render(
        request,
        "proyectos/partials/presupuesto_anual.html",
        _contexto(proyecto, request.user, **extra),
    )


@login_required
def listar_presupuesto_anual(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    return _responder(request, proyecto)


@login_required
@require_POST
def crear_anio(request, pk):
    """Agrega el año siguiente al último cargado, en cero.

    Se crea vacío a propósito: el monto lo sabe el equipo del proyecto y
    proponerle una cifra repartida en partes iguales sólo lograría que la
    aceptara sin mirarla.
    """
    proyecto = get_object_or_404(Proyecto, pk=pk)
    if not _puede_editar(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    agregados = proyecto.presupuestos_anuales.aggregate(
        n=Max("numero_anio"), c=Max("anio_calendario")
    )
    siguiente = (agregados["n"] or 0) + 1
    calendario = (
        agregados["c"] + 1 if agregados["c"] else proyecto.anio_calendario_inicial
    )

    anio = PresupuestoAnual(
        proyecto=proyecto,
        numero_anio=siguiente,
        anio_calendario=calendario,
        creado_por=request.user,
    )
    try:
        anio.full_clean()
        anio.save()
    except ValidationError as error:
        return _responder(request, proyecto, error=" ".join(
            m for msgs in error.message_dict.values() for m in msgs
        ))

    response = _responder(request, proyecto, nuevo_anio_id=anio.pk)
    return disparar(response, estructuraActualizada=True,
                    guardado=f"Año {siguiente} agregado ({calendario}).")


@login_required
@require_POST
def guardar_anio(request, pk):
    anio = get_object_or_404(PresupuestoAnual, pk=pk)
    proyecto = anio.proyecto
    if not _puede_editar(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    anio.presupuesto_corriente = _to_decimal(request.POST.get("presupuesto_corriente"))
    anio.presupuesto_capital = _to_decimal(request.POST.get("presupuesto_capital"))
    if request.POST.get("anio_calendario"):
        anio.anio_calendario = int(_to_decimal(request.POST["anio_calendario"]))
    anio.actualizado_por = request.user

    try:
        anio.full_clean()
        anio.save()
    except ValidationError as error:
        # Se recarga desde la base para que la pantalla vuelva a mostrar lo que
        # está guardado y no el monto rechazado, que induce a creer que quedó.
        anio.refresh_from_db()
        return _responder(request, proyecto, error=" ".join(
            m for msgs in error.message_dict.values() for m in msgs
        ), anio_con_error=anio.pk)

    response = _responder(request, proyecto)
    return disparar(response, estructuraActualizada=True,
                    guardado=f"Presupuesto de {anio.anio_calendario} guardado.")


@login_required
@require_POST
def eliminar_anio(request, pk):
    """Borra un año y renumera los que quedan.

    Sin renumerar, borrar el Año 2 de tres deja «Año 1, Año 3» y el selector
    miente sobre cuántos años tiene el proyecto. El año calendario no se toca:
    ése es un dato, no una posición.
    """
    anio = get_object_or_404(PresupuestoAnual, pk=pk)
    proyecto = anio.proyecto
    if not _puede_editar(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    if anio.planificado:
        return _responder(request, proyecto, error=(
            f"No se puede borrar {anio.anio_calendario}: tiene planes de gasto "
            f"cargados por {anio.planificado:,.0f}. Bórralos o muévelos primero."
        ))

    calendario = anio.anio_calendario
    anio.delete()

    for posicion, restante in enumerate(
        proyecto.presupuestos_anuales.order_by("numero_anio"), start=1
    ):
        if restante.numero_anio != posicion:
            restante.numero_anio = posicion
            restante.save(update_fields=["numero_anio"])

    response = _responder(request, proyecto)
    return disparar(response, estructuraActualizada=True,
                    guardado=f"Año {calendario} eliminado.")

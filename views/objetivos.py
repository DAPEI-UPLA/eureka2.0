from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Max
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from ..models import ObjetivoEspecifico, Proyecto
from .permisos import usuario_es_responsable
from .utils import _to_decimal, disparar


@login_required
def listar_objetivos(request, pk):
    """Lista completa de objetivos; la usa el refresco automático en vivo."""
    proyecto = get_object_or_404(Proyecto, pk=pk)
    return render(request, "proyectos/partials/objetivos_lista.html", {
        "proyecto": proyecto,
        "es_encargado": usuario_es_responsable(request.user, proyecto),
    })


@login_required
@require_POST
def crear_objetivo(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    if not usuario_es_responsable(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    siguiente = (proyecto.objetivos.aggregate(m=Max("orden"))["m"] or 0) + 1
    # Se crea sin descripción: la caja de edición aparece vacía y con
    # placeholder, para no arrastrar un texto de relleno que haya que borrar.
    objetivo = ObjetivoEspecifico.objects.create(
        proyecto=proyecto,
        descripcion="",
        orden=siguiente,
        creado_por=request.user,
    )

    response = render(request, "proyectos/partials/objetivos_lista.html", {
        "proyecto": proyecto,
        "es_encargado": True,
        "nuevo_objetivo_id": objetivo.pk,
    })
    return disparar(response, estructuraActualizada=True)


@login_required
def editar_objetivo_form(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")
    return render(request, "proyectos/partials/objetivo_input.html", {"objetivo": objetivo})


@login_required
@require_POST
def guardar_objetivo(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    objetivo.descripcion = request.POST.get("descripcion", "").strip()
    objetivo.actualizado_por = request.user
    objetivo.save(update_fields=["descripcion", "actualizado_por", "actualizado_en"])

    response = render(request, "proyectos/partials/objetivo_texto.html", {"objetivo": objetivo})
    return disparar(response, guardado="Objetivo guardado")


@login_required
def meta_objetivo(request, pk):
    """Contadores + presupuesto de la cabecera del objetivo."""
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    return render(request, "proyectos/partials/objetivo_meta.html", {"objetivo": objetivo})


@login_required
def editar_presupuesto_objetivo(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    if request.method == "POST":
        try:
            objetivo.presupuesto_corriente = _to_decimal(request.POST.get("presupuesto_corriente"))
            objetivo.presupuesto_capital = _to_decimal(request.POST.get("presupuesto_capital"))
            objetivo.actualizado_por = request.user
            objetivo.full_clean()
            objetivo.save()
        except ValidationError as e:
            return HttpResponseBadRequest("; ".join(e.messages))

        response = render(request, "proyectos/partials/objetivo_presupuesto.html", {
            "objetivo": objetivo,
        })
        return disparar(
            response,
            estructuraActualizada=True,
            guardado="Presupuesto del objetivo actualizado",
        )

    return render(request, "proyectos/partials/objetivo_presupuesto_form.html", {
        "objetivo": objetivo,
    })


@login_required
@require_POST
def eliminar_objetivo(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")
    objetivo.soft_delete()
    return disparar(
        HttpResponse(""),
        objetivosActualizados=True,
        estructuraActualizada=True,
        guardado="Objetivo eliminado",
    )

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST, require_http_methods

from ..models import ObjetivoEspecifico, Resultado
from .permisos import usuario_es_responsable
from .utils import _to_decimal, detalle_resultado, disparar


@login_required
def listar_resultados(request, pk):
    """Cuerpo de la tabla de resultados de un objetivo (refresco en vivo)."""
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    return render(request, "proyectos/partials/resultados_lista.html", {
        "objetivo": objetivo,
        "es_encargado": usuario_es_responsable(request.user, objetivo.proyecto),
    })


@login_required
@require_POST
def crear_resultado(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    siguiente = (objetivo.resultados.aggregate(m=Max("orden"))["m"] or 0) + 1
    resultado = Resultado.objects.create(
        objetivo=objetivo,
        descripcion="",
        orden=siguiente,
        creado_por=request.user,
    )

    # Se devuelve la tabla completa (no un append) para que desaparezca el
    # estado vacío y el nuevo resultado quede listo para escribir.
    response = render(request, "proyectos/partials/resultados_lista.html", {
        "objetivo": objetivo,
        "es_encargado": True,
        "nuevo_resultado_id": resultado.pk,
    })
    return disparar(
        response,
        objetivoActualizado={"objetivo_id": objetivo.pk},
        estructuraActualizada=True,
    )


@login_required
def editar_resultado_form(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")
    return render(request, "proyectos/partials/resultado_input.html", {"resultado": resultado})


@login_required
def fila_resultado(request, pk):
    """Sólo la fila del resultado, con sus totales recalculados."""
    resultado = get_object_or_404(Resultado, pk=pk)
    return render(request, "proyectos/partials/resultado_fila.html", {
        "resultado": resultado,
        "es_encargado": usuario_es_responsable(request.user, resultado.objetivo.proyecto),
    })


@login_required
@require_POST
def guardar_resultado(request, pk):
    """
    Guarda solo descripción. El cumplimiento y estado son derivados de las
    actividades — ya no se editan a mano.
    """
    resultado = get_object_or_404(Resultado, pk=pk)
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    descripcion = request.POST.get("descripcion")
    if descripcion is not None:
        resultado.descripcion = descripcion.strip()

    resultado.actualizado_por = request.user
    resultado.save(update_fields=["descripcion", "actualizado_por", "actualizado_en"])

    response = render(request, "proyectos/partials/resultado_fila.html", {"resultado": resultado})
    return disparar(response, guardado="Resultado guardado")


@login_required
@require_http_methods(["POST", "DELETE"])
def eliminar_resultado(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")
    objetivo_id = resultado.objetivo_id
    resultado.soft_delete()
    return disparar(
        HttpResponse(""),
        resultadosActualizados={"objetivo_id": objetivo_id},
        objetivoActualizado={"objetivo_id": objetivo_id},
        estructuraActualizada=True,
        guardado="Resultado eliminado",
    )


@login_required
def form_asignar_presupuesto(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)
    return render(request, "proyectos/partials/form_asignar_presupuesto.html", {
        "resultado": resultado,
    })


@login_required
@require_POST
def guardar_presupuesto(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)
    proyecto = resultado.objetivo.proyecto
    if not usuario_es_responsable(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    try:
        with transaction.atomic():
            # El presupuesto baja por la cadena proyecto → objetivo → resultado →
            # actividad: cada nivel reparte lo que recibió del de arriba. El tope
            # de un resultado es lo que le queda a **su objetivo**, no lo que le
            # queda al proyecto; `Resultado.clean()` ya aplica esa regla y es la
            # única fuente de verdad.
            #
            # Los dos montos se editan directamente en vez de sumarse: antes solo
            # se podía agregar, así que un monto puesto de más no había cómo
            # bajarlo salvo por el admin.
            corriente = _to_decimal(request.POST.get("presupuesto_corriente"))
            capital = _to_decimal(request.POST.get("presupuesto_capital"))

            resultado.presupuesto_corriente = corriente
            resultado.presupuesto_capital = capital
            resultado.actualizado_por = request.user
            resultado.full_clean()
            resultado.save()

    except ValidationError as e:
        return HttpResponse("; ".join(e.messages), status=400)

    response = render(request, "proyectos/partials/presupuesto_detalle.html", {"resultado": resultado})
    return disparar(
        response,
        resultadoActualizado=detalle_resultado(resultado),
        objetivoActualizado={"objetivo_id": resultado.objetivo_id},
        estructuraActualizada=True,
        guardado="Presupuesto asignado",
    )


@login_required
def detalle_presupuesto_resultado(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")
    return render(request, "proyectos/partials/presupuesto_detalle.html", {"resultado": resultado})

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Max
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from ..models import ObjetivoEspecifico, Proyecto, montos_en_el_anio
from .permisos import usuario_es_responsable
from .utils import _to_decimal, anio_seleccionado, disparar


def objetivos_con_montos(proyecto, anio_sel):
    """Los objetivos con el monto que corresponde mostrar.

    Con un año elegido son los de ese año, no los de toda la vida del proyecto:
    mostrar el total bajo un encabezado que dice «Viendo Año 2» es enseñar una
    cifra que no es la que se está mirando.
    """
    objetivos = list(proyecto.objetivos.all())
    for objetivo in objetivos:
        objetivo.montos = montos_en_el_anio(objetivo, anio_sel)
    return objetivos


@login_required
def listar_objetivos(request, pk):
    """Lista completa de objetivos; la usa el refresco automático en vivo."""
    proyecto = get_object_or_404(Proyecto, pk=pk)
    anio_sel = anio_seleccionado(request, proyecto)
    return render(request, "proyectos/partials/objetivos_lista.html", {
        "proyecto": proyecto,
        "objetivos": objetivos_con_montos(proyecto, anio_sel),
        "anio_sel": anio_sel,
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
    anio_sel = anio_seleccionado(request, objetivo.proyecto)
    objetivo.montos = montos_en_el_anio(objetivo, anio_sel)
    return render(request, "proyectos/partials/objetivo_meta.html", {
        "objetivo": objetivo,
        "anio_sel": anio_sel,
    })


@login_required
def editar_presupuesto_objetivo(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    # Con reparto anual, el total del objetivo es la suma de sus años y no se
    # edita a mano: dejarlo editable permitiría dejarlo diciendo algo distinto
    # de lo repartido, y a partir de ahí ninguna de las dos cifras sería
    # confiable. Se manda al editor por año, que es donde se decide.
    if objetivo.proyecto and objetivo.proyecto.presupuestos_anuales.exists():
        from .presupuesto_objetivo import presupuesto_objetivo_anual
        return presupuesto_objetivo_anual(request, pk)

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

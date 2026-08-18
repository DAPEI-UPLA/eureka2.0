import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..forms import ProyectoForm
from ..models import Proyecto
from .permisos import es_jefe, usuario_es_responsable
from .objetivos import objetivos_con_montos
from .utils import anio_seleccionado

logger = logging.getLogger(__name__)


def _detalle_errores(form):
    """Arma un resumen legible de los errores para mostrarlo en un `message`.

    El modal de edición vive en la lista y el POST termina en un redirect, así
    que el formulario con sus errores se pierde: sin esto el usuario solo veía
    «Errores al actualizar el proyecto» y el motivo quedaba enterrado en el log
    del servidor.
    """
    partes = []
    for campo, errores in form.errors.items():
        texto = " ".join(errores)
        if campo == '__all__':
            partes.append(texto)
        else:
            etiqueta = form.fields[campo].label or campo.replace('_', ' ').capitalize()
            partes.append(f"{etiqueta}: {texto}")
    return " ".join(partes) or "revisa los datos ingresados."


@login_required
def mis_proyectos(request):
    proyectos = Proyecto.objects.filter(responsable=request.user)
    return render(request, 'proyectos/mis_proyectos.html', {'proyectos': proyectos})


@login_required
def proyectos_por_tipo(request, tipo):
    proyectos = Proyecto.objects.filter(tipo=tipo)
    return render(request, 'proyectos/proyectos_por_tipo.html', {'proyectos': proyectos})


@login_required
def lista_proyectos(request):
    user = request.user
    jefe = es_jefe(user)

    qs = Proyecto.objects.with_resumen().prefetch_related(
        'objetivos__resultados__actividades'
    ).order_by('-fecha_creacion')
    if not jefe:
        qs = qs.filter(responsable=user)

    abrir_crear = False
    if request.method == 'POST' and jefe:
        form = ProyectoForm(request.POST)
        if form.is_valid():
            proyecto = form.save(commit=False)
            proyecto.creado_por = request.user
            proyecto.save()
            messages.success(request, "Proyecto creado.")
            return redirect('proyectos:lista_proyectos')
        # Form inválido: reabrimos el modal mostrando los errores en vez de
        # recargar en silencio (lo que parecía "el sistema no responde").
        abrir_crear = True
        messages.error(request, "Revisa los datos del proyecto: hay campos por corregir.")
    else:
        form = ProyectoForm()

    vista = request.GET.get('vista', 'tarjetas')
    page_obj = Paginator(qs, 12).get_page(request.GET.get('page'))

    return render(request, 'proyectos/lista_proyectos.html', {
        'proyectos': page_obj.object_list,
        'page_obj': page_obj,
        'es_jefe': jefe,
        'form': form,
        'edit_form': ProyectoForm(auto_id='edit_id_%s'),
        'abrir_crear': abrir_crear,
        'vista': vista,
    })


@login_required
def detalle_proyecto(request, pk):
    proyecto = get_object_or_404(
        Proyecto.objects.prefetch_related('objetivos__resultados__actividades'),
        pk=pk,
    )
    anio_sel = anio_seleccionado(request, proyecto)
    return render(request, "proyectos/detalle_proyecto.html", {
        "proyecto": proyecto,
        "es_encargado": usuario_es_responsable(request.user, proyecto),
        "es_jefe": es_jefe(request.user),
        "anio_sel": anio_sel,
        "anios": proyecto.presupuestos_anuales.all(),
        "objetivos": objetivos_con_montos(proyecto, anio_sel),
    })


@login_required
def dashboard_proyecto(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    anio_sel = anio_seleccionado(request, proyecto)

    # El arrastre sólo tiene sentido mirando un año concreto: en la vista del
    # proyecto completo todas las actividades están, se hayan corrido o no.
    arrastre = None
    if anio_sel:
        arrastre = {
            "propias": anio_sel.actividades_propias().count(),
            "arrastradas": list(anio_sel.actividades_arrastradas()),
            "perdidas": list(anio_sel.actividades_perdidas()),
        }

    return render(request, "proyectos/partials/detalle_dashboard.html", {
        "proyecto": proyecto,
        "anio_sel": anio_sel,
        "arrastre": arrastre,
    })


@login_required
def tablero_proyecto(request, pk):
    proyecto = get_object_or_404(
        Proyecto.objects.prefetch_related('objetivos__resultados'),
        pk=pk,
    )
    return render(request, "proyectos/tablero.html", {"proyecto": proyecto})


@login_required
@require_POST
def editar_proyecto(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    if not es_jefe(request.user):
        return HttpResponseForbidden("No autorizado")

    form = ProyectoForm(request.POST, instance=proyecto)
    if form.is_valid():
        proyecto = form.save(commit=False)
        proyecto.actualizado_por = request.user
        proyecto.save()
        messages.success(request, "Proyecto actualizado.")
    else:
        logger.warning("Errores al editar proyecto %s: %s", pk, form.errors)
        messages.error(
            request,
            "No se pudo actualizar el proyecto: " + _detalle_errores(form),
        )
    return redirect('proyectos:lista_proyectos')


@login_required
@require_POST
def eliminar_proyecto(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    if not es_jefe(request.user):
        return HttpResponseForbidden("No autorizado")
    proyecto.soft_delete()
    messages.success(request, "Proyecto eliminado.")
    return redirect('proyectos:lista_proyectos')

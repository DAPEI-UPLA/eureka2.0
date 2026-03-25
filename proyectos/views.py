from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string
from django.http import HttpResponse, HttpResponseForbidden
from django.core.exceptions import ValidationError

from .models import Proyecto, ObjetivoEspecifico, Resultado
from .forms import ProyectoForm


# =========================
# HELPERS / PERMISOS
# =========================

def es_jefe(user):
    return user.groups.filter(name='JefeProyectos').exists()


def es_encargada(user):
    return user.groups.filter(name='EncargadaProyectos').exists()


def usuario_es_responsable(user, proyecto):
    return user == proyecto.responsable


# =========================
# PROYECTOS
# =========================

@login_required
def mis_proyectos(request):
    proyectos = Proyecto.objects.filter(responsable=request.user)
    return render(request, 'proyectos/mis_proyectos.html', {
        'proyectos': proyectos
    })


@login_required
def proyectos_por_tipo(request, tipo):
    proyectos = Proyecto.objects.filter(tipo=tipo)
    return render(request, 'proyectos/proyectos_por_tipo.html', {
        'proyectos': proyectos
    })


@login_required
def lista_proyectos(request):
    user = request.user
    jefe = es_jefe(user)

    if jefe:
        proyectos = Proyecto.objects.prefetch_related(
            'objetivos__resultados'
        ).all()
    else:
        proyectos = Proyecto.objects.prefetch_related(
            'objetivos__resultados'
        ).filter(responsable=user)

    if request.method == 'POST' and jefe:
        form = ProyectoForm(request.POST)
        if form.is_valid():
            proyecto = form.save(commit=False)
            proyecto.creado_por = request.user
            proyecto.save()
            return redirect('proyectos:lista_proyectos')
    else:
        form = ProyectoForm()

    return render(request, 'proyectos/lista_proyectos.html', {
        'proyectos': proyectos,
        'es_jefe': jefe,
        'form': form
    })


@login_required
def detalle_proyecto(request, pk):
    proyecto = get_object_or_404(
        Proyecto.objects.prefetch_related('objetivos__resultados'),
        pk=pk
    )

    contexto = {
        "proyecto": proyecto,
        "es_encargado": usuario_es_responsable(request.user, proyecto),
        "es_jefe": es_jefe(request.user),
    }

    return render(request, "proyectos/detalle_proyecto.html", contexto)


# =========================
# OBJETIVOS (INLINE / HTMX)
# =========================

@login_required
def crear_objetivo(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)

    if not usuario_es_responsable(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    objetivo = ObjetivoEspecifico.objects.create(
        proyecto=proyecto,
        descripcion="Nuevo objetivo (editar)"
    )

    html = render_to_string(
        "proyectos/partials/objetivo_row.html",
        {"objetivo": objetivo},
        request=request
    )

    return HttpResponse(html, status=201)


@login_required
def editar_objetivo_form(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)

    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    return render(
        request,
        "proyectos/partials/objetivo_input.html",
        {"objetivo": objetivo}
    )


@login_required
def guardar_objetivo(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)

    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    nueva_descripcion = request.POST.get("descripcion", "").strip()

    if not nueva_descripcion:
        return HttpResponse("La descripción no puede estar vacía", status=400)

    objetivo.descripcion = nueva_descripcion
    objetivo.save()

    return render(
        request,
        "proyectos/partials/objetivo_texto.html",
        {"objetivo": objetivo}
    )


# =========================
# RESULTADOS (INLINE / HTMX)
# =========================

@login_required
def crear_resultado(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)

    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    try:
        resultado = Resultado.objects.create(
            objetivo=objetivo,
            descripcion="",  # 👈 vacío para edición inmediata
            cumplimiento=0,
            presupuesto_asignado=0
        )
    except ValidationError as e:
        return HttpResponse(str(e), status=400)

    # 👇 Retorna directamente el input editable
    return render(
        request,
        "proyectos/partials/resultado_input.html",
        {"resultado": resultado}
    )

@login_required
def editar_resultado_form(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)

    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    return render(
        request,
        "proyectos/partials/resultado_input.html",
        {"resultado": resultado}
    )


@login_required
def guardar_resultado(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)

    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    # DATOS

    descripcion = request.POST.get("descripcion")
    estado = request.POST.get("estado")
    cumplimiento = request.POST.get("cumplimiento")

    # DESCRIPCIÓN

    if descripcion is not None:
        descripcion = descripcion.strip()
        if descripcion:
            resultado.descripcion = descripcion
        else:
            return HttpResponse("La descripción no puede estar vacía", status=400)

    # CUMPLIMIENTO

    if cumplimiento is not None:
        try:
            valor = float(cumplimiento)
            if 0 <= valor <= 100:
                resultado.cumplimiento = valor
            else:
                return HttpResponse("El cumplimiento debe estar entre 0 y 100", status=400)
        except ValueError:
            return HttpResponse("Valor de cumplimiento inválido", status=400)


    # ESTADO

    if estado:
        resultado.estado = estado

    if resultado.cumplimiento == 100:
        resultado.estado = "COMPLETADO"
    elif resultado.cumplimiento > 0:
        resultado.estado = "EN_PROCESO"
    elif resultado.cumplimiento == 0:
        resultado.estado = "PENDIENTE"

    # GUARDAR

    try:
        resultado.save()
    except ValidationError as e:
        return HttpResponse(str(e), status=400)

    # RESPUESTA

    return render(
        request,
        "proyectos/partials/resultado_row.html",  
        {"resultado": resultado}
    )


@login_required
def eliminar_resultado(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)

    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    resultado.delete()

    return HttpResponse(status=204)





# =========================
# TABLERO (BASE TIPO MONDAY)
# =========================

@login_required
def tablero_proyecto(request, pk):
    proyecto = get_object_or_404(
        Proyecto.objects.prefetch_related('objetivos__resultados'),
        pk=pk
    )

    return render(request, "proyectos/tablero.html", {
        "proyecto": proyecto
    })


@login_required
def detalle_presupuesto_resultado(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)

    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    return render(request, "proyectos/partials/presupuesto_detalle.html", {
        "resultado": resultado
    })
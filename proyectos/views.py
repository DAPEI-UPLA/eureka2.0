from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string
from django.http import HttpResponse, HttpResponseForbidden
from django.core.exceptions import ValidationError
from django.db import transaction
from decimal import Decimal

from .models import Proyecto, ObjetivoEspecifico, Resultado, Gasto, PlanDeGasto, Actividad
from .forms import ProyectoForm



# HELPERS / PERMISOS


def es_jefe(user):
    return user.groups.filter(name='JefeProyectos').exists()


def es_encargada(user):
    return user.groups.filter(name='EncargadaProyectos').exists()


def usuario_es_responsable(user, proyecto):
    return user == proyecto.responsable


# PROYECTOS


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



# OBJETIVOS (INLINE / HTMX)


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



# RESULTADOS (INLINE / HTMX)


@login_required
def crear_resultado(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)

    if not usuario_es_responsable(request.user, objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    try:
        resultado = Resultado.objects.create(
            objetivo=objetivo,
            descripcion="",   # 👈 vacío para editar inmediatamente
            cumplimiento=0
        )
    except ValidationError as e:
        return HttpResponse(str(e), status=400)

    # Renderizamos el input directamente (modo edición)
    html = render_to_string(
        "proyectos/partials/resultado_input.html",
        {"resultado": resultado},
        request=request
    )

    return HttpResponse(html)

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

# Asignación de presupuesto

@login_required
def form_asignar_presupuesto(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)

    return render(request, "proyectos/partials/form_asignar_presupuesto.html", {
        "resultado": resultado
    })


@login_required
def guardar_presupuesto(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)
    proyecto = resultado.objetivo.proyecto

    try:
        monto = Decimal(request.POST.get("monto", "0"))
        tipo_gasto = request.POST.get("tipo_gasto")

        if monto <= 0:
            return HttpResponse("Monto inválido", status=400)

        if tipo_gasto not in ["COR", "CAP"]:
            return HttpResponse("Tipo de gasto inválido", status=400)

        with transaction.atomic():

            # 🔒 VALIDACIÓN GLOBAL
            if monto > proyecto.presupuesto_disponible:
                return HttpResponse(
                    f"No hay presupuesto disponible. Disponible: ${proyecto.presupuesto_disponible:,.0f}",
                    status=400
                )

            # 🔥 SUMAR SEGÚN TIPO
            if tipo_gasto == "COR":
                resultado.presupuesto_corriente += monto

            elif tipo_gasto == "CAP":
                resultado.presupuesto_capital += monto

            # 👇 IMPORTANTE: el save maneja el descuento automático
            resultado.save()

    except Exception as e:
        return HttpResponse(str(e), status=400)

    return render(request, "proyectos/partials/presupuesto_detalle.html", {
        "resultado": resultado
    })


# TABLERO 


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


# Gastos

@login_required
def crear_gasto(request, resultado_id):
    resultado = get_object_or_404(Resultado, pk=resultado_id)

    return render(request, "proyectos/partials/form_gasto.html", {
        "resultado": resultado
    })

@login_required
def guardar_gasto(request, resultado_id):
    resultado = get_object_or_404(Resultado, pk=resultado_id)

    Gasto.objects.create(
        resultado=resultado,
        nombre=request.POST.get("nombre"),
        descripcion=request.POST.get("descripcion"),
        monto=request.POST.get("monto"),
        tipo_gasto=request.POST.get("tipo_gasto"),
        estado=request.POST.get("estado"),
    )

    return render(request, "proyectos/partials/gasto_ok.html", {
        "resultado": resultado
    })

def crear_plan_gasto_form(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, pk=proyecto_id)

    objetivos = proyecto.objetivos.all()

    return render(request, "proyectos/partials/plan_gasto_form.html", {
        "proyecto": proyecto,
        "objetivos": objetivos
    })



def crear_plan_gasto(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, pk=proyecto_id)

    try:
        plan = PlanDeGasto.objects.create(
            anio=request.POST.get("anio"),
            objetivo_id=request.POST.get("objetivo"),
            resultado_id=request.POST.get("resultado"),
            tipo_gasto_id=request.POST.get("tipo_gasto"),
            monto=request.POST.get("monto"),
            creado_por=request.user
        )

        return HttpResponse("""
            <div class="text-center py-4">
                <h5 class="text-success">✔ Línea creada</h5>
                <button class="btn btn-primary mt-2" data-bs-dismiss="modal">
                    Cerrar
                </button>
            </div>
        """)

    except Exception as e:
        return HttpResponse(f"<div class='text-danger'>Error: {str(e)}</div>")
    
def cargar_resultados(request):
    objetivo_id = request.GET.get("objetivo")

    resultados = Resultado.objects.filter(objetivo_id=objetivo_id)

    return render(request, "proyectos/partials/resultados_options.html", {
        "resultados": resultados
    })


def listar_actividades(request, resultado_id):
    resultado = get_object_or_404(Resultado, pk=resultado_id)

    return render(request, "proyectos/partials/actividades_lista.html", {
        "actividades": resultado.actividades.all()
    })

def crear_actividad_form(request, resultado_id):
    resultado = get_object_or_404(Resultado, pk=resultado_id)

    return render(request, "proyectos/partials/actividad_form.html", {
        "resultado": resultado
    })

def crear_actividad(request, resultado_id):
    resultado = get_object_or_404(Resultado, pk=resultado_id)

    try:
        actividad = Actividad(
            resultado=resultado,
            nombre=request.POST.get("nombre"),
            presupuesto=request.POST.get("presupuesto"),
            fecha_limite=request.POST.get("fecha_limite"),
            creado_por=request.user
        )

        actividad.full_clean()
        actividad.save()

        return render(request, "proyectos/partials/actividad_row.html", {
            "actividad": actividad
        })

    except Exception as e:
        return HttpResponse(f"<div class='text-danger'>{str(e)}</div>")
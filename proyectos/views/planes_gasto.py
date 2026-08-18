from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST, require_http_methods

from ..models import (
    Actividad, GastoElegible, PlanDeGasto, Proyecto, Resultado, Transferencia,
    Unidad,
)
from .permisos import usuario_es_responsable
from .utils import _to_decimal, anio_seleccionado


@login_required
def crear_plan_gasto_form(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, pk=proyecto_id)
    contexto = {
        "proyecto": proyecto,
        "objetivos": proyecto.objetivos.all(),
        "transferencias": Transferencia.objects.all(),
        "unidades": Unidad.objects.all(),
    }

    # Si el formulario se abre desde un resultado (o desde una actividad, que
    # lleva a su resultado), se llega con él elegido en vez de obligar a
    # recorrer de nuevo objetivo → resultado.
    resultado = None
    actividad_id = request.GET.get("actividad")
    resultado_id = request.GET.get("resultado")
    if actividad_id:
        actividad = get_object_or_404(
            Actividad.objects.select_related("resultado__objetivo"), pk=actividad_id
        )
        resultado = actividad.resultado
        contexto["actividad_sel"] = actividad
    elif resultado_id:
        resultado = get_object_or_404(
            Resultado.objects.select_related("objetivo"), pk=resultado_id
        )

    if resultado and resultado.objetivo.proyecto_id == proyecto.id:
        contexto.update({
            "resultado_sel": resultado,
            "resultados": resultado.objetivo.resultados.all(),
            "actividades": resultado.actividades.all(),
        })

    return render(request, "proyectos/partials/plan_gasto_form.html", contexto)


@login_required
@require_POST
def crear_plan_gasto(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, pk=proyecto_id)
    if not usuario_es_responsable(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    try:
        resultado_id = request.POST.get("resultado")
        # La actividad es opcional: sirve para decir para qué es el gasto, pero
        # el presupuesto lo controla el resultado.
        actividad_id = request.POST.get("actividad") or None
        gasto_elegible_id = request.POST.get("gasto_elegible")
        transferencia_id = request.POST.get("transferencia")
        unidad_id = request.POST.get("unidad_responsable") or None
        anio = int(request.POST.get("anio") or 0)
        monto = _to_decimal(request.POST.get("monto"))

        resultado = get_object_or_404(
            Resultado.objects.select_related("objetivo"), pk=resultado_id
        )
        if resultado.objetivo.proyecto_id != proyecto.id:
            return HttpResponseForbidden("Resultado fuera del proyecto")

        actividad = (get_object_or_404(Actividad, pk=actividad_id)
                     if actividad_id else None)

        gasto_elegible = get_object_or_404(
            GastoElegible.objects.select_related("gasto__tipo_gasto__transferencia"),
            pk=gasto_elegible_id,
        )

        if transferencia_id and str(gasto_elegible.gasto.tipo_gasto.transferencia_id) != str(transferencia_id):
            return HttpResponse(
                "<div class='text-danger'>El gasto elegible no pertenece a la transferencia seleccionada.</div>",
                status=400,
            )

        unidad = get_object_or_404(Unidad, pk=unidad_id) if unidad_id else None

        with transaction.atomic():
            plan = PlanDeGasto(
                resultado=resultado,
                actividad=actividad,
                gasto_elegible=gasto_elegible,
                unidad_responsable=unidad,
                anio=anio,
                monto=monto,
            )
            plan.full_clean()
            plan.save()

        response = HttpResponse(f"""
            <div class="text-center py-4">
                <h5 class="text-success">Plan creado</h5>
                <code class="d-block my-2">{plan.nombre_corto}</code>
                <button class="btn btn-primary mt-2" data-bs-dismiss="modal">Cerrar</button>
            </div>
        """)
        response["HX-Trigger"] = "planUpdated"
        return response

    except ValidationError as e:
        return HttpResponse(f"<div class='text-danger'>{'; '.join(e.messages)}</div>", status=400)
    except (ValueError, TypeError) as e:
        return HttpResponse(f"<div class='text-danger'>Datos inválidos: {e}</div>", status=400)


@login_required
def editar_plan_gasto_form(request, pk):
    plan = get_object_or_404(
        PlanDeGasto.objects.select_related(
            "resultado__objetivo__proyecto",
            "gasto_elegible__gasto__tipo_gasto__transferencia",
            "unidad_responsable",
        ),
        pk=pk,
    )
    proyecto = plan.resultado.objetivo.proyecto
    if not usuario_es_responsable(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")
    return render(request, "proyectos/partials/plan_gasto_form.html", {
        "proyecto": proyecto,
        "plan": plan,
        "resultado_sel": plan.resultado,
        "actividad_sel": plan.actividad,
        "objetivos": proyecto.objetivos.all(),
        "transferencias": Transferencia.objects.all(),
        "unidades": Unidad.objects.all(),
        "tipos_gasto": plan.gasto_elegible.gasto.tipo_gasto.transferencia.tipos_gasto.all(),
        "gastos": plan.gasto_elegible.gasto.tipo_gasto.gastos.all(),
        "gastos_elegibles": plan.gasto_elegible.gasto.elegibles.all(),
        "resultados": plan.resultado.objetivo.resultados.all(),
        "actividades": plan.resultado.actividades.all(),
    })


@login_required
@require_POST
def editar_plan_gasto(request, pk):
    plan = get_object_or_404(
        PlanDeGasto.objects.select_related(
            "resultado__objetivo__proyecto",
        ),
        pk=pk,
    )
    proyecto = plan.resultado.objetivo.proyecto
    if not usuario_es_responsable(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    try:
        resultado_id = request.POST.get("resultado")
        actividad_id = request.POST.get("actividad") or None
        gasto_elegible_id = request.POST.get("gasto_elegible")
        unidad_id = request.POST.get("unidad_responsable") or None
        anio = int(request.POST.get("anio") or 0)
        monto = _to_decimal(request.POST.get("monto"))

        resultado = get_object_or_404(
            Resultado.objects.select_related("objetivo"), pk=resultado_id
        )
        if resultado.objetivo.proyecto_id != proyecto.id:
            return HttpResponseForbidden("Resultado fuera del proyecto")

        actividad = (get_object_or_404(Actividad, pk=actividad_id)
                     if actividad_id else None)

        gasto_elegible = get_object_or_404(GastoElegible, pk=gasto_elegible_id)
        unidad = get_object_or_404(Unidad, pk=unidad_id) if unidad_id else None

        with transaction.atomic():
            plan.resultado = resultado
            plan.actividad = actividad
            plan.gasto_elegible = gasto_elegible
            plan.unidad_responsable = unidad
            plan.anio = anio
            plan.monto = monto
            plan.full_clean()
            plan.save()

        response = HttpResponse("""
            <div class="text-center py-4">
                <h5 class="text-success">Plan actualizado</h5>
                <button class="btn btn-primary mt-2" data-bs-dismiss="modal">Cerrar</button>
            </div>
        """)
        response["HX-Trigger"] = "planUpdated"
        return response

    except ValidationError as e:
        return HttpResponse(f"<div class='text-danger'>{'; '.join(e.messages)}</div>", status=400)
    except (ValueError, TypeError) as e:
        return HttpResponse(f"<div class='text-danger'>Datos inválidos: {e}</div>", status=400)


@login_required
def listar_planes_actividad(request, actividad_id):
    actividad = get_object_or_404(Actividad, pk=actividad_id)
    planes = (
        actividad.planes_gasto
        .select_related(
            "gasto_elegible__gasto__tipo_gasto__transferencia",
            "unidad_responsable",
        )
        .order_by("-anio")
    )
    return render(request, "proyectos/partials/planes_actividad.html", {
        "actividad": actividad,
        "planes": planes,
        "puede_editar": usuario_es_responsable(
            request.user, actividad.resultado.objetivo.proyecto
        ),
    })


@login_required
@require_http_methods(["POST", "DELETE"])
def eliminar_plan_gasto(request, pk):
    from ..models import Egreso

    plan = get_object_or_404(
        PlanDeGasto.objects.select_related(
            "resultado__objetivo__proyecto"
        ),
        pk=pk,
    )
    proyecto = plan.actividad.resultado.objetivo.proyecto
    if not usuario_es_responsable(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    # Egresos activos bloquean la eliminación (con mensaje claro)
    activos = Egreso.objects.filter(plan_de_gasto=plan, eliminado=False)
    if activos.exists():
        return HttpResponse(
            f"<div class='alert alert-danger small'>"
            f"No se puede eliminar: hay {activos.count()} gasto(s) activo(s) "
            f"cargados a este plan. Eliminá los gastos primero."
            f"</div>",
            status=400,
        )

    # Egresos ya soft-deleted: limpiamos definitivamente para liberar el FK
    Egreso.all_objects.filter(plan_de_gasto=plan, eliminado=True).delete()

    plan.delete()
    response = HttpResponse(status=200)
    response["HX-Trigger"] = "planUpdated"
    return response


@login_required
def listar_planes_gasto(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, pk=proyecto_id)
    planes = (
        PlanDeGasto.objects
        .filter(resultado__objetivo__proyecto=proyecto)
        .select_related(
            "resultado__objetivo",
            "gasto_elegible__gasto__tipo_gasto__transferencia",
            "unidad_responsable",
        )
        .order_by("-anio", "actividad__nombre")
    )

    # El POA de un año concreto cuando se está mirando ese año; si no, todos.
    anio_sel = anio_seleccionado(request, proyecto)
    if anio_sel:
        planes = planes.filter(anio=anio_sel.anio_calendario)

    return render(request, "proyectos/partials/planes_gasto_lista.html", {
        "proyecto": proyecto,
        "planes": planes,
        "puede_editar": usuario_es_responsable(request.user, proyecto),
        "anio_sel": anio_sel,
    })

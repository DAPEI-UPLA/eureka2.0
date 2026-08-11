from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST, require_http_methods

from ..models import (
    Egreso,
    Gasto,
    GastoElegible,
    PlanDeGasto,
    Proyecto,
)
from .permisos import usuario_es_responsable
from .utils import _to_decimal


def _parsear_egreso(request, proyecto):
    """Lee y valida el POST de un egreso. Devuelve dict listo para asignar.
    Lanza ValidationError si hay incoherencias semánticas."""
    tipo = request.POST.get("tipo") or Egreso.TIPO_COMPRA
    subtipo = request.POST.get("subtipo_compra") or ""
    estado = request.POST.get("estado") or Egreso.ESTADO_COMPROMETIDO
    cr = (request.POST.get("centro_responsabilidad") or "").strip()
    elegible_id = request.POST.get("gasto_elegible") or None
    plan_id = request.POST.get("plan_de_gasto") or None
    fecha = request.POST.get("fecha") or None
    observaciones = (request.POST.get("observaciones") or "").strip()

    # Folios del trámite. Opcionales y sueltos: llegan en momentos distintos.
    documentos = {
        campo: (request.POST.get(campo) or "").strip()[:50]
        for campo in ("solicitud_compra", "orden_compra", "factura")
    }

    plan = None
    gasto = None
    gasto_elegible = None

    if elegible_id:
        gasto_elegible = get_object_or_404(
            GastoElegible.objects.select_related("gasto"),
            pk=elegible_id,
        )
        gasto = gasto_elegible.gasto

    if plan_id:
        plan = get_object_or_404(
            PlanDeGasto.objects.select_related(
                "gasto_elegible__gasto",
                "actividad__resultado__objetivo__proyecto",
            ),
            pk=plan_id,
        )
        if plan.actividad.resultado.objetivo.proyecto_id != proyecto.id:
            raise ValidationError("El plan no pertenece a este proyecto.")
        # Si el elegible no coincide con el del plan no se rechaza nada: el
        # modelo los alinea tomando el del plan, que es el que manda.

    data = {
        "tipo": tipo,
        "subtipo_compra": subtipo if tipo == Egreso.TIPO_COMPRA else "",
        "estado": estado,
        "centro_responsabilidad": cr,
        "plan_de_gasto": plan,
        "gasto": gasto,
        "gasto_elegible": gasto_elegible,
        "observaciones": observaciones,
        **documentos,
    }
    if fecha:
        data["fecha"] = fecha

    if tipo == Egreso.TIPO_COMPRA:
        data["cantidad"] = int(request.POST.get("cantidad") or 0)
        data["valor_sin_iva"] = _to_decimal(request.POST.get("valor_sin_iva"))
        # limpiar campos de honorario para evitar valores residuales
        data["nombre_persona"] = ""
        data["apellido_persona"] = ""
        data["profesion"] = ""
        data["monto_total"] = Decimal("0")
        data["meses"] = 0
        data["cuota_mensual"] = Decimal("0")
        data["descripcion"] = ""
    elif tipo == Egreso.TIPO_HONORARIO:
        data["nombre_persona"] = (request.POST.get("nombre_persona") or "").strip()
        data["apellido_persona"] = (request.POST.get("apellido_persona") or "").strip()
        data["profesion"] = (request.POST.get("profesion") or "").strip()
        data["meses"] = int(request.POST.get("meses") or 0)
        data["cuota_mensual"] = _to_decimal(request.POST.get("cuota_mensual"))
        data["monto_total"] = _to_decimal(request.POST.get("monto_total"))
        data["descripcion"] = (request.POST.get("descripcion") or "").strip()[:500]
        # Una cuota por campo. `_cuadrar_las_cuotas` deriva de acá los meses y
        # el total, así que estas cifras son las que mandan.
        data["cuotas"] = [
            str(_to_decimal(monto))
            for monto in request.POST.getlist("cuota_monto")
        ]
        # compra fields a 0
        data["cantidad"] = 0
        data["valor_sin_iva"] = Decimal("0")

    return data


def _elegibles_por_subtipo(subtipo):
    filtro = Egreso.SUBTIPO_ELEGIBLE_FILTER.get(subtipo)
    if not filtro:
        return GastoElegible.objects.none()
    return GastoElegible.objects.filter(**filtro).select_related("gasto").order_by("nombre")


def _elegibles_por_tipo(tipo):
    filtro = Egreso.TIPO_ELEGIBLE_FILTER.get(tipo)
    if not filtro:
        return GastoElegible.objects.none()
    return GastoElegible.objects.filter(**filtro).select_related("gasto").order_by("nombre")


def _planes_por_elegible(proyecto, gasto_elegible_id):
    if not gasto_elegible_id:
        return PlanDeGasto.objects.none()
    return (
        PlanDeGasto.objects
        .filter(
            actividad__resultado__objetivo__proyecto=proyecto,
            gasto_elegible_id=gasto_elegible_id,
        )
        .select_related(
            "actividad__resultado__objetivo",
            "gasto_elegible__gasto__tipo_gasto__transferencia",
        )
        .order_by("-anio", "actividad__nombre")
    )


def _contexto_form(proyecto, egreso=None, edicion=False, error=None):
    """Contexto del formulario de gasto: vacío, en edición o de vuelta con error.

    `edicion` no se deduce de `egreso` porque cuando una validación falla se
    vuelve a dibujar el formulario con el gasto **sin guardar** que se acaba de
    escribir: hay instancia, pero sigue siendo un alta.
    """
    contexto = {
        "proyecto": proyecto,
        "egreso": egreso,
        "edicion": edicion,
        "error": error,
        "tipos": Egreso.TIPOS,
        "subtipos_compra": Egreso.SUBTIPOS_COMPRA,
        "estados": Egreso.ESTADOS,
        # Los campos de cuota los dibuja el JS; de acá salen sus valores. Un
        # honorario viejo no tiene la lista, pero `montos_de_cuotas` la arma
        # con la cuota pareja, así que llega detallado igual.
        "cuotas_iniciales": [
            f"{monto:.0f}" for monto in egreso.montos_de_cuotas
        ] if egreso is not None and egreso.tipo == Egreso.TIPO_HONORARIO else [],
    }
    if egreso is not None:
        if egreso.tipo == Egreso.TIPO_COMPRA:
            elegibles = list(_elegibles_por_subtipo(egreso.subtipo_compra))
        else:
            elegibles = list(_elegibles_por_tipo(egreso.tipo))

        # Un honorario puede estar guardado sin gasto elegible (el modelo sólo
        # le exige el plan). Sin elegible, el <select> de plan se dibuja
        # deshabilitado, así que el plan no viaja al guardar y el formulario
        # rechaza el gasto por no tener plan. El elegible del plan es el que
        # corresponde: `clean()` ya exige que sean el mismo.
        elegible_id = egreso.gasto_elegible_id
        if not elegible_id and egreso.plan_de_gasto_id:
            elegible_id = egreso.plan_de_gasto.gasto_elegible_id

        # Y el elegible que el gasto ya tiene va siempre en la lista, aunque el
        # filtro por subtipo no lo alcance: si no, el <select> vuelve sin nada
        # marcado, el navegador manda la opción vacía y el gasto se queda sin
        # elegible al guardar, sin que nadie haya tocado ese campo.
        if elegible_id and all(e.id != elegible_id for e in elegibles):
            elegibles.insert(0, GastoElegible.objects.get(pk=elegible_id))

        contexto["elegibles"] = elegibles
        contexto["elegible_id"] = elegible_id
        contexto["planes"] = _planes_por_elegible(proyecto, elegible_id)
    return contexto


def _form_con_error(request, proyecto, egreso, error, edicion):
    """Devuelve el formulario con el aviso arriba y lo escrito todavía puesto.

    Antes esto respondía sólo con el texto del error, que reemplazaba el modal
    entero: el aviso llegaba, pero a costa de borrar el formulario completo y
    obligar a escribirlo todo de nuevo.
    """
    mensajes = error.messages if isinstance(error, ValidationError) else [str(error)]
    contexto = _contexto_form(proyecto, egreso, edicion=edicion,
                              error="; ".join(mensajes))
    return render(request, "proyectos/partials/egreso_form.html",
                  contexto, status=400)


@login_required
def crear_egreso_form(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, pk=proyecto_id)
    return render(request, "proyectos/partials/egreso_form.html",
                  _contexto_form(proyecto))


@login_required
def editar_egreso_form(request, pk):
    egreso = get_object_or_404(
        Egreso.objects.select_related("proyecto", "plan_de_gasto", "gasto_elegible"),
        pk=pk,
    )
    if not usuario_es_responsable(request.user, egreso.proyecto):
        return HttpResponseForbidden("No autorizado")

    return render(request, "proyectos/partials/egreso_form.html",
                  _contexto_form(egreso.proyecto, egreso, edicion=True))


@login_required
@require_POST
def editar_egreso(request, pk):
    egreso = get_object_or_404(
        Egreso.objects.select_related("proyecto"),
        pk=pk,
    )
    proyecto = egreso.proyecto
    if not usuario_es_responsable(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    try:
        data = _parsear_egreso(request, proyecto)

        with transaction.atomic():
            for field, value in data.items():
                setattr(egreso, field, value)
            egreso.actualizado_por = request.user
            egreso.full_clean()
            egreso.save()

        response = HttpResponse("""
            <div class="text-center py-4">
                <h5 class="text-success">Gasto actualizado</h5>
                <button class="btn btn-primary mt-2" data-bs-dismiss="modal">Cerrar</button>
            </div>
        """)
        response["HX-Trigger"] = "egresoUpdated"
        return response

    except ValidationError as e:
        return _form_con_error(request, proyecto, egreso, e, edicion=True)
    except (ValueError, TypeError) as e:
        return _form_con_error(request, proyecto, egreso,
                               f"Datos inválidos: {e}", edicion=True)


@login_required
def elegibles_por_subtipo(request, proyecto_id):
    """Devuelve el bloque con el select de GastoElegible filtrado por subtipo
    (o por tipo si es Honorario/Viático), más planes pre-cargados si hay un
    solo elegible (auto-selección)."""
    proyecto = get_object_or_404(Proyecto, pk=proyecto_id)
    subtipo = request.GET.get("subtipo_compra") or ""
    tipo = request.GET.get("tipo") or Egreso.TIPO_COMPRA

    if tipo == Egreso.TIPO_COMPRA:
        elegibles = list(_elegibles_por_subtipo(subtipo))
    else:
        elegibles = list(_elegibles_por_tipo(tipo))

    selected_elegible_id = None
    planes = []
    if len(elegibles) == 1:
        selected_elegible_id = elegibles[0].id
        planes = list(_planes_por_elegible(proyecto, selected_elegible_id))

    return render(request, "proyectos/partials/egreso_elegibles_options.html", {
        "elegibles": elegibles,
        "planes": planes,
        "subtipo": subtipo,
        "tipo": tipo,
        "proyecto_id": proyecto_id,
        "selected_elegible_id": selected_elegible_id,
    })


@login_required
def planes_por_elegible(request, proyecto_id):
    """Devuelve el select de Plan de Gasto filtrado por el GastoElegible elegido."""
    proyecto = get_object_or_404(Proyecto, pk=proyecto_id)
    gasto_elegible_id = request.GET.get("gasto_elegible") or None
    planes = _planes_por_elegible(proyecto, gasto_elegible_id)
    return render(request, "proyectos/partials/egreso_planes_select.html", {
        "planes": planes,
        "gasto_elegible_id": gasto_elegible_id,
    })


@login_required
@require_POST
def crear_egreso(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, pk=proyecto_id)
    if not usuario_es_responsable(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    egreso = None
    try:
        data = _parsear_egreso(request, proyecto)
        egreso = Egreso(
            proyecto=proyecto,
            creado_por=request.user,
            actualizado_por=request.user,
            **data,
        )

        with transaction.atomic():
            egreso.full_clean()
            egreso.save()

        response = HttpResponse("""
            <div class="text-center py-4">
                <h5 class="text-success">Gasto registrado</h5>
                <button class="btn btn-primary mt-2" data-bs-dismiss="modal">Cerrar</button>
            </div>
        """)
        response["HX-Trigger"] = "egresoUpdated"
        return response

    except ValidationError as e:
        return _form_con_error(request, proyecto, egreso, e, edicion=False)
    except (ValueError, TypeError) as e:
        return _form_con_error(request, proyecto, egreso,
                               f"Datos inválidos: {e}", edicion=False)


@login_required
def listar_egresos(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, pk=proyecto_id)

    qs = (
        Egreso.objects
        .filter(proyecto=proyecto)
        .select_related(
            "plan_de_gasto__actividad__resultado__objetivo",
            "gasto__tipo_gasto__transferencia",
            "gasto_elegible",
        )
    )

    f_estado = request.GET.get("estado") or ""
    f_tipo = request.GET.get("tipo") or ""
    f_anio = request.GET.get("anio") or ""

    if f_estado:
        qs = qs.filter(estado=f_estado)
    if f_tipo:
        qs = qs.filter(tipo=f_tipo)
    if f_anio:
        try:
            qs = qs.filter(fecha__year=int(f_anio))
        except (TypeError, ValueError):
            pass

    # Resumen por tipo (sobre TODOS los egresos del proyecto, sin filtros UI).
    # Se suma con `Egreso.montos` y no con cantidad × valor: los honorarios no
    # usan esas dos columnas, así que salían siempre en $0 aunque el contrato
    # valiera millones.
    totales = {}
    for egreso in Egreso.objects.filter(proyecto=proyecto, eliminado=False):
        total, _pagado, _comprometido = egreso.montos
        totales[egreso.tipo] = totales.get(egreso.tipo, Decimal("0")) + total

    tipos_dict = dict(Egreso.TIPOS)
    resumen_por_tipo = [
        {"tipo": tipo, "label": tipos_dict.get(tipo, tipo), "total": total}
        for tipo, total in totales.items()
    ]

    anios = (
        Egreso.objects
        .filter(proyecto=proyecto, eliminado=False)
        .dates("fecha", "year", order="DESC")
    )

    return render(request, "proyectos/partials/egresos_lista.html", {
        "proyecto": proyecto,
        "egresos": qs,
        "puede_editar": usuario_es_responsable(request.user, proyecto),
        "filtro_estado": f_estado,
        "filtro_tipo": f_tipo,
        "filtro_anio": f_anio,
        "estados": Egreso.ESTADOS,
        "tipos": Egreso.TIPOS,
        "anios": [d.year for d in anios],
        "resumen_por_tipo": resumen_por_tipo,
    })


@login_required
@require_POST
def pagar_cuota(request, pk):
    egreso = get_object_or_404(
        Egreso.objects.select_related("proyecto"), pk=pk,
    )
    if not usuario_es_responsable(request.user, egreso.proyecto):
        return HttpResponseForbidden("No autorizado")
    if egreso.tipo != Egreso.TIPO_HONORARIO:
        return HttpResponse(
            "<div class='alert alert-danger small'>Solo aplica a honorarios.</div>",
            status=400,
        )
    if egreso.cuotas_pendientes <= 0:
        return HttpResponse(
            "<div class='alert alert-danger small'>No quedan cuotas por pagar.</div>",
            status=400,
        )

    egreso.cuotas_pagadas = (egreso.cuotas_pagadas or 0) + 1
    egreso.actualizado_por = request.user
    if egreso.cuotas_pagadas >= egreso.meses:
        egreso.estado = Egreso.ESTADO_PAGADO
    egreso.save()

    response = HttpResponse(status=204)
    response["HX-Trigger"] = "egresoUpdated"
    return response


@login_required
@require_POST
def pagar_impuesto(request, pk):
    egreso = get_object_or_404(
        Egreso.objects.select_related("proyecto"), pk=pk,
    )
    if not usuario_es_responsable(request.user, egreso.proyecto):
        return HttpResponseForbidden("No autorizado")
    if egreso.tipo != Egreso.TIPO_HONORARIO:
        return HttpResponse(
            "<div class='alert alert-danger small'>Solo aplica a honorarios.</div>",
            status=400,
        )
    if egreso.impuestos_pendientes <= 0:
        return HttpResponse(
            "<div class='alert alert-danger small'>No hay impuestos pendientes.</div>",
            status=400,
        )

    egreso.impuestos_pagados = (egreso.impuestos_pagados or 0) + 1
    egreso.actualizado_por = request.user
    egreso.save()

    response = HttpResponse(status=204)
    response["HX-Trigger"] = "egresoUpdated"
    return response


@login_required
@require_http_methods(["POST", "DELETE"])
def eliminar_egreso(request, pk):
    egreso = get_object_or_404(
        Egreso.objects.select_related("proyecto"),
        pk=pk,
    )
    if not usuario_es_responsable(request.user, egreso.proyecto):
        return HttpResponseForbidden("No autorizado")

    egreso.soft_delete()
    response = HttpResponse(status=200)
    response["HX-Trigger"] = "egresoUpdated"
    return response


@login_required
def plan_detalle(request):
    """Devuelve un fragmento con info del Plan seleccionado (Gasto + Gasto elegible)."""
    plan_id = request.GET.get("plan_de_gasto")
    if not plan_id:
        return HttpResponse("")
    plan = get_object_or_404(
        PlanDeGasto.objects.select_related(
            "gasto_elegible__gasto__tipo_gasto__transferencia",
            "actividad",
        ),
        pk=plan_id,
    )
    return render(request, "proyectos/partials/egreso_plan_detalle.html", {
        "plan": plan,
    })

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Max, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils.formats import number_format
from django.views.decorators.http import require_POST, require_http_methods

from ..models import Actividad, Resultado
from .permisos import usuario_es_responsable
from .utils import _to_decimal, detalle_resultado, disparar


def _contexto_form(resultado, excluir=None, **extra):
    """Datos comunes del formulario de actividad (crear y editar).

    `excluir` es la actividad que se está editando.

    Ya no calcula disponibles: la actividad no lleva presupuesto, así que no hay
    monto que topar contra el resultado. Lo que se planifica son los planes de
    gasto, que cuelgan del resultado.
    """
    contexto = {
        "resultado": resultado,
        "actividad": excluir,
    }
    contexto.update(extra)

    # El template lee siempre de `datos`, así no tiene que resolver campos sobre
    # una actividad que no existe al crear. Si el POST falló, `datos` ya viene
    # con lo que la persona escribió y se respeta.
    if "datos" not in contexto:
        contexto["datos"] = {
            "nombre": excluir.nombre if excluir else "",
            "fecha_limite": _iso(excluir.fecha_limite) if excluir else "",
            "fecha_efectiva": _iso(excluir.fecha_efectiva) if excluir else "",
        }
    return contexto


def _entero(valor):
    """Monto en texto agrupado ("3.000.000"), como se ve en el resto de la app.

    El campo es de texto y `a_decimal` sabe leer el separador de miles, así que
    la persona edita el número tal como lo lee, sin traducirlo mentalmente.
    """
    return number_format(int(valor or 0), force_grouping=True)


def _iso(fecha):
    return fecha.isoformat() if fecha else ""


def _datos_enviados(request):
    return {
        "nombre": request.POST.get("nombre", "").strip(),
        "fecha_limite": request.POST.get("fecha_limite") or "",
        "fecha_efectiva": request.POST.get("fecha_efectiva") or "",
        # Opcional: si viene, queda anotado en el historial de reprogramaciones.
        # No se exige, porque obligar a justificar cada corrida de fecha llevaría
        # a que la gente escriba «se atrasó» y el dato no sirva de nada.
        "motivo_reprogramacion": request.POST.get("motivo_reprogramacion", "").strip(),
    }


@login_required
def listar_actividades(request, resultado_id):
    resultado = get_object_or_404(Resultado, pk=resultado_id)
    return render(request, "proyectos/partials/actividades_lista.html", {
        "actividades": resultado.actividades.all(),
    })


@login_required
def crear_actividad_form(request, resultado_id):
    resultado = get_object_or_404(Resultado, pk=resultado_id)
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")
    return render(request, "proyectos/partials/actividad_form.html",
                  _contexto_form(resultado))


@login_required
def editar_actividad_form(request, actividad_id):
    actividad = get_object_or_404(Actividad, pk=actividad_id)
    resultado = actividad.resultado
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")
    return render(request, "proyectos/partials/actividad_form.html",
                  _contexto_form(resultado, excluir=actividad))


@login_required
@require_POST
def editar_actividad(request, actividad_id):
    actividad = get_object_or_404(Actividad, pk=actividad_id)
    resultado = actividad.resultado
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    datos = _datos_enviados(request)
    try:
        actividad.nombre = datos["nombre"]
        actividad.fecha_limite = datos["fecha_limite"] or None
        actividad.fecha_efectiva = datos["fecha_efectiva"] or None
        actividad.actualizado_por = request.user
        actividad._motivo_reprogramacion = datos["motivo_reprogramacion"]
        actividad.full_clean()
        actividad.save()
    except ValidationError as e:
        msgs = e.messages if hasattr(e, "messages") else [str(e)]
        return render(request, "proyectos/partials/actividad_form.html",
                      _contexto_form(resultado, excluir=actividad,
                                     error=" ".join(msgs), datos=datos),
                      status=400)

    response = render(request, "proyectos/partials/actividad_creada.html", {
        "actividad": actividad,
        "resultado": resultado,
        "editada": True,
    })
    return disparar(
        response,
        actividadActualizada=detalle_resultado(resultado),
        resultadoActualizado=detalle_resultado(resultado),
        objetivoActualizado={"objetivo_id": resultado.objetivo_id},
        estructuraActualizada=True,
        guardado="Actividad actualizada",
    )


@login_required
@require_POST
def crear_actividad(request, resultado_id):
    resultado = get_object_or_404(Resultado, pk=resultado_id)
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    datos = _datos_enviados(request)

    try:
        siguiente = (resultado.actividades.aggregate(m=Max("orden"))["m"] or 0) + 1
        actividad = Actividad(
            resultado=resultado,
            nombre=datos["nombre"],
            fecha_limite=datos["fecha_limite"] or None,
            fecha_efectiva=datos["fecha_efectiva"] or None,
            orden=siguiente,
            creado_por=request.user,
        )
        actividad.full_clean()
        actividad.save()
    except ValidationError as e:
        # El formulario se re-muestra con lo ya escrito y el motivo concreto,
        # en vez de dejar el campo bloqueado por un max/min imposible.
        msgs = e.messages if hasattr(e, "messages") else [str(e)]
        return render(request, "proyectos/partials/actividad_form.html",
                      _contexto_form(resultado, error=" ".join(msgs), datos=datos),
                      status=400)

    response = render(request, "proyectos/partials/actividad_creada.html", {
        "actividad": actividad,
        "resultado": resultado,
    })
    return disparar(
        response,
        actividadActualizada=detalle_resultado(resultado),
        resultadoActualizado=detalle_resultado(resultado),
        objetivoActualizado={"objetivo_id": resultado.objetivo_id},
        estructuraActualizada=True,
        guardado="Actividad creada",
    )


@login_required
@require_http_methods(["POST", "DELETE"])
def eliminar_actividad(request, actividad_id):
    actividad = get_object_or_404(Actividad, pk=actividad_id)
    resultado = actividad.resultado
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")
    actividad.delete()
    return disparar(
        HttpResponse(""),
        actividadActualizada=detalle_resultado(resultado),
        resultadoActualizado=detalle_resultado(resultado),
        objetivoActualizado={"objetivo_id": resultado.objetivo_id},
        estructuraActualizada=True,
        guardado="Actividad eliminada",
    )


@login_required
@require_POST
def guardar_actividad(request, actividad_id):
    actividad = get_object_or_404(Actividad, pk=actividad_id)
    resultado = actividad.resultado
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    try:
        valor = int(request.POST.get("cumplimiento", 0))
        actividad.cumplimiento = max(0, min(100, valor))
    except (ValueError, TypeError):
        actividad.cumplimiento = 0

    actividad.actualizado_por = request.user
    actividad.save(update_fields=["cumplimiento", "actualizado_por", "actualizado_en"])

    response = render(request, "proyectos/partials/actividad_fila.html", {"actividad": actividad})
    return disparar(
        response,
        resultadoActualizado=detalle_resultado(resultado),
        objetivoActualizado={"objetivo_id": resultado.objetivo_id},
        estructuraActualizada=True,
        guardado="Avance guardado",
    )

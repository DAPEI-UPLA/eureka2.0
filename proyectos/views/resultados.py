from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST, require_http_methods

from ..models import ObjetivoEspecifico, Resultado, montos_en_el_anio
from .permisos import usuario_es_responsable
from .utils import anio_seleccionado, _to_decimal, detalle_resultado, disparar


def resultados_con_montos(objetivo, anio_sel):
    """Los resultados con el monto que corresponde mostrar (ver objetivos)."""
    resultados = list(objetivo.resultados.all())
    for resultado in resultados:
        resultado.montos = montos_en_el_anio(resultado, anio_sel)
    return resultados


@login_required
def listar_resultados(request, pk):
    """Cuerpo de la tabla de resultados de un objetivo (refresco en vivo)."""
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)
    anio_sel = anio_seleccionado(request, objetivo.proyecto)
    return render(request, "proyectos/partials/resultados_lista.html", {
        "objetivo": objetivo,
        "resultados": resultados_con_montos(objetivo, anio_sel),
        "anio_sel": anio_sel,
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

    # Si su objetivo ya reparte por año, el total del resultado es la suma de
    # sus años y no se edita a mano: se manda al editor por año, que es donde
    # se decide. Dejar los dos caminos abiertos permitiría que el total dijera
    # algo distinto del reparto y ninguna cifra sería confiable.
    if resultado.objetivo.tiene_reparto_anual:
        from .presupuesto_resultado import presupuesto_resultado_anual
        return presupuesto_resultado_anual(request, pk)

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
    """El desglose del presupuesto de un resultado.

    Es una pantalla de lectura, así que la ve cualquiera: el equipo pidió poder
    mirar los proyectos de sus compañeros. Lo que no se puede es editar, y eso
    lo topan los endpoints de escritura, no éste.
    """
    resultado = get_object_or_404(Resultado, pk=pk)
    return render(request, "proyectos/partials/presupuesto_detalle.html", {
        "resultado": resultado,
        "puede_editar": usuario_es_responsable(
            request.user, resultado.objetivo.proyecto
        ),
    })


# =========================
# CÓMO SE MIDE EL AVANCE
# =========================
# Antes el avance salía siempre del promedio de las actividades, y un resultado
# sin actividades leía 0% para siempre. Ahora cada resultado declara con qué
# regla se mide, para que el número sea comparable entre equipos y verificable
# en una rendición.

@login_required
def avance_resultado_form(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")
    return render(request, "proyectos/partials/avance_resultado_form.html", {
        "resultado": resultado,
        "tramos": Resultado.TRAMOS,
    })


@login_required
@require_POST
def guardar_avance_resultado(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)
    if not usuario_es_responsable(request.user, resultado.objetivo.proyecto):
        return HttpResponseForbidden("No autorizado")

    metodo = request.POST.get("metodo_avance", "")
    validos = {clave for clave, _ in Resultado.METODOS_AVANCE}
    resultado.metodo_avance = metodo if metodo in validos else ""

    if resultado.metodo_avance == Resultado.METODO_META:
        resultado.unidad_meta = request.POST.get("unidad_meta", "").strip()
        resultado.meta = _entero(request.POST.get("meta")) or None
        resultado.alcanzado = _entero(request.POST.get("alcanzado")) or 0
    elif resultado.metodo_avance == Resultado.METODO_TRAMOS:
        permitidos = {valor for valor, _ in Resultado.TRAMOS}
        tramo = _entero(request.POST.get("tramo"))
        resultado.tramo = tramo if tramo in permitidos else 0

    error = _revisar_avance(resultado)
    if error:
        return render(request, "proyectos/partials/avance_resultado_form.html", {
            "resultado": resultado,
            "tramos": Resultado.TRAMOS,
            "error": error,
        }, status=400)

    resultado.actualizado_por = request.user
    resultado.save(update_fields=[
        "metodo_avance", "unidad_meta", "meta", "alcanzado", "tramo",
        "actualizado_por", "actualizado_en",
    ])

    response = render(request, "proyectos/partials/resultado_fila.html",
                      {"resultado": resultado})
    return disparar(
        response,
        resultadoActualizado=detalle_resultado(resultado),
        objetivoActualizado={"objetivo_id": resultado.objetivo_id},
        # El valor ganado del proyecto sale de estos números.
        estructuraActualizada=True,
        guardado="Avance del resultado guardado",
    )


def _entero(valor):
    try:
        return max(0, int(str(valor or "").strip() or 0))
    except (TypeError, ValueError):
        return 0


def _revisar_avance(resultado):
    """Lo que no se puede guardar, y por qué."""
    if resultado.metodo_avance != Resultado.METODO_META:
        return None
    if not resultado.unidad_meta:
        return "Di qué se cuenta: convenios, talleres, informes…"
    if not resultado.meta:
        return "La meta comprometida tiene que ser mayor que cero."
    if resultado.alcanzado > resultado.meta:
        # No se bloquea el sobrecumplimiento porque es real y hay que poder
        # registrarlo; sólo se avisa de que el avance se topa en 100%, para que
        # nadie espere ver un 125% en la fila.
        return None
    return None

from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.db.models import Count

from .forms import IniciativaForm, FormulacionForm
from .models import (
    Iniciativa,
    Formulacion,
    MovimientoIniciativa,
    DocumentoIniciativa,
    DocumentoFormulacion,
)


# =============================================================
# PERMISOS
# =============================================================

GRUPO_APROBADORES = "Aprobadores de Iniciativas"


def es_aprobador(user):
    """Único punto de verdad para saber si un usuario aprueba iniciativas."""
    return user.is_authenticated and user.groups.filter(name=GRUPO_APROBADORES).exists()


def aprobador_required(view):
    """Exige sesión iniciada y pertenencia al grupo de aprobadores.

    A diferencia de @user_passes_test, devuelve 403 a un usuario autenticado
    sin permiso (en vez de redirigirlo al login).
    """
    @wraps(view)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not es_aprobador(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return _wrapped


# =============================================================
# UTILIDADES — TRAZABILIDAD Y DOCUMENTOS
# =============================================================

def registrar_movimiento(iniciativa, usuario, tipo, detalle="",
                         estado_anterior="", estado_nuevo=""):
    """Registra un evento en la bitácora de la iniciativa."""
    MovimientoIniciativa.objects.create(
        iniciativa=iniciativa,
        usuario=usuario,
        tipo=tipo,
        detalle=detalle,
        estado_anterior=estado_anterior or "",
        estado_nuevo=estado_nuevo or "",
    )


# Validación de documentos adjuntos (bases, formularios, anexos).
EXTENSIONES_DOC_VALIDAS = (".pdf", ".doc", ".docx", ".xls", ".xlsx")
MAX_DOC_BYTES = 10 * 1024 * 1024  # 10 MB
FIRMAS_DOC = (
    b"%PDF",                               # PDF
    b"PK\x03\x04",                         # DOCX / XLSX (contenedor ZIP)
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",  # DOC / XLS antiguos (OLE2)
)


def validar_documento(archivo):
    """Valida un documento adjunto. Devuelve un mensaje de error o None si es OK."""
    if not archivo:
        return "Debes seleccionar un archivo."
    if not archivo.name.lower().endswith(EXTENSIONES_DOC_VALIDAS):
        return "Solo se aceptan archivos PDF, Word o Excel."
    if archivo.size > MAX_DOC_BYTES:
        return "El documento no puede superar los 10 MB."
    cabecera = archivo.read(8)
    archivo.seek(0)
    if not any(cabecera.startswith(firma) for firma in FIRMAS_DOC):
        return "El archivo no es un documento válido (contenido no reconocido)."
    return None


def puede_ver_iniciativa(user, iniciativa):
    return iniciativa.responsable_id == user.id or es_aprobador(user)


# =============================================================
# HOME
# =============================================================

@login_required
def oct_home(request):
    return render(request, 'oct/home.html')


@login_required
def iniciativas_home(request):
    aprobador = es_aprobador(request.user)
    contexto = {"es_aprobador": aprobador}

    if aprobador:
        contexto["pendientes_iniciativas"] = Iniciativa.objects.filter(
            estado=Iniciativa.Estado.ENVIADA
        ).count()
        contexto["pendientes_formulaciones"] = Formulacion.objects.filter(
            estado=Formulacion.Estado.ENVIADA
        ).count()

    return render(request, "oct/iniciativas_home.html", contexto)


# =============================================================
# INICIATIVAS — RESPONSABLE
# =============================================================

@login_required
def registrar_iniciativa(request):
    if request.method == "POST":
        form = IniciativaForm(request.POST)
        if form.is_valid():
            iniciativa = form.save(commit=False)
            iniciativa.responsable = request.user
            enviar = "enviar" in request.POST
            if enviar:
                iniciativa.estado = Iniciativa.Estado.ENVIADA
            iniciativa.save()

            registrar_movimiento(
                iniciativa, request.user, MovimientoIniciativa.Tipo.CREACION,
                detalle=f'Iniciativa creada: "{iniciativa.nombre}".',
                estado_nuevo=iniciativa.estado,
            )
            if enviar:
                registrar_movimiento(
                    iniciativa, request.user, MovimientoIniciativa.Tipo.ENVIO,
                    detalle="Enviada a revisión de la OCT.",
                    estado_nuevo=Iniciativa.Estado.ENVIADA,
                )
                messages.success(request, "Iniciativa enviada a revisión.")
            else:
                messages.success(request, "Iniciativa guardada como borrador.")
            return redirect("oct:mis_iniciativas")
    else:
        form = IniciativaForm()

    return render(request, "oct/registrar_iniciativa.html", {"form": form})


@login_required
def mis_iniciativas(request):
    iniciativas = Iniciativa.objects.filter(responsable=request.user)

    # Conteo por estado (sobre todas, sin filtro de UI) para los chips.
    conteo = {e.value: 0 for e in Iniciativa.Estado}
    for fila in iniciativas.values("estado").annotate(n=Count("id")):
        conteo[fila["estado"]] = fila["n"]

    # Solo mostramos chips de estados que tengan al menos una iniciativa.
    chips = [
        {"value": value, "label": label, "count": conteo[value]}
        for value, label in Iniciativa.Estado.choices
        if conteo[value]
    ]

    filtro = request.GET.get("estado") or ""
    if filtro:
        iniciativas = iniciativas.filter(estado=filtro)

    return render(request, "oct/mis_iniciativas.html", {
        "iniciativas": iniciativas,
        "chips": chips,
        "filtro": filtro,
        "total": sum(conteo.values()),
    })


@login_required
def detalle_iniciativa(request, pk):
    """Vista unificada: muestra la iniciativa, su formulación, documentos,
    bitácora y las acciones disponibles según el estado y el rol."""
    iniciativa = get_object_or_404(Iniciativa, pk=pk)
    if not puede_ver_iniciativa(request.user, iniciativa):
        raise PermissionDenied

    es_responsable = iniciativa.responsable_id == request.user.id

    return render(request, "oct/detalle_iniciativa.html", {
        "iniciativa": iniciativa,
        "formulacion": getattr(iniciativa, "formulacion", None),
        "documentos": iniciativa.documentos.all(),
        "movimientos": iniciativa.movimientos.select_related("usuario"),
        "es_responsable": es_responsable,
        "es_aprobador": es_aprobador(request.user),
        "Estado": Iniciativa.Estado,
    })


@login_required
def editar_iniciativa(request, pk):
    iniciativa = get_object_or_404(Iniciativa, pk=pk)

    if iniciativa.responsable != request.user:
        raise PermissionDenied

    # Solo se puede editar mientras no esté en revisión ni cerrada.
    estados_editables = [
        Iniciativa.Estado.BORRADOR,
        Iniciativa.Estado.DEVUELTA,
    ]
    if iniciativa.estado not in estados_editables:
        messages.warning(request, "Esta iniciativa no se puede editar en su estado actual.")
        return redirect("oct:detalle_iniciativa", pk=iniciativa.pk)

    if request.method == "POST":
        form = IniciativaForm(request.POST, instance=iniciativa)
        if form.is_valid():
            iniciativa = form.save()
            registrar_movimiento(
                iniciativa, request.user, MovimientoIniciativa.Tipo.EDICION,
                detalle="Datos de la iniciativa actualizados.",
            )
            if "enviar" in request.POST:
                estado_anterior = iniciativa.estado
                iniciativa.estado = Iniciativa.Estado.ENVIADA
                iniciativa.save(update_fields=["estado"])
                registrar_movimiento(
                    iniciativa, request.user, MovimientoIniciativa.Tipo.ENVIO,
                    detalle="Enviada (nuevamente) a revisión de la OCT.",
                    estado_anterior=estado_anterior,
                    estado_nuevo=Iniciativa.Estado.ENVIADA,
                )
                messages.success(request, "Iniciativa enviada a revisión.")
            else:
                messages.success(request, "Cambios guardados.")
            return redirect("oct:detalle_iniciativa", pk=iniciativa.pk)
    else:
        form = IniciativaForm(instance=iniciativa)

    return render(request, "oct/editar_iniciativa.html", {
        "form": form,
        "iniciativa": iniciativa,
    })


@login_required
@require_POST
def subir_documento_iniciativa(request, pk):
    iniciativa = get_object_or_404(Iniciativa, pk=pk)
    if iniciativa.responsable != request.user:
        raise PermissionDenied

    archivo = request.FILES.get("archivo")
    error = validar_documento(archivo)
    if error:
        messages.error(request, error)
        return redirect("oct:detalle_iniciativa", pk=pk)

    DocumentoIniciativa.objects.create(iniciativa=iniciativa, archivo=archivo)
    registrar_movimiento(
        iniciativa, request.user, MovimientoIniciativa.Tipo.DOCUMENTO,
        detalle=f'Documento adjuntado: "{archivo.name}".',
    )
    messages.success(request, "Documento adjuntado.")
    return redirect("oct:detalle_iniciativa", pk=pk)


@login_required
@require_POST
def eliminar_documento_iniciativa(request, pk):
    documento = get_object_or_404(DocumentoIniciativa, pk=pk)
    iniciativa = documento.iniciativa
    if iniciativa.responsable != request.user:
        raise PermissionDenied

    nombre = documento.nombre_archivo
    documento.delete()
    registrar_movimiento(
        iniciativa, request.user, MovimientoIniciativa.Tipo.DOCUMENTO,
        detalle=f'Documento eliminado: "{nombre}".',
    )
    messages.success(request, "Documento eliminado.")
    return redirect("oct:detalle_iniciativa", pk=iniciativa.pk)


@login_required
@require_POST
def marcar_adjudicada(request, pk):
    iniciativa = get_object_or_404(Iniciativa, pk=pk)
    if iniciativa.responsable != request.user:
        raise PermissionDenied
    if iniciativa.estado != Iniciativa.Estado.POSTULADA:
        messages.warning(request, "Solo puedes marcar el resultado de una iniciativa postulada.")
        return redirect("oct:detalle_iniciativa", pk=pk)

    estado_anterior = iniciativa.estado
    iniciativa.estado = Iniciativa.Estado.ADJUDICADA
    iniciativa.save(update_fields=["estado"])
    registrar_movimiento(
        iniciativa, request.user, MovimientoIniciativa.Tipo.CAMBIO_ESTADO,
        detalle="La iniciativa fue adjudicada. 🎉",
        estado_anterior=estado_anterior,
        estado_nuevo=Iniciativa.Estado.ADJUDICADA,
    )
    messages.success(request, "¡Iniciativa marcada como adjudicada!")
    return redirect("oct:detalle_iniciativa", pk=pk)


@login_required
@require_POST
def marcar_no_adjudicada(request, pk):
    iniciativa = get_object_or_404(Iniciativa, pk=pk)
    if iniciativa.responsable != request.user:
        raise PermissionDenied
    if iniciativa.estado != Iniciativa.Estado.POSTULADA:
        messages.warning(request, "Solo puedes marcar el resultado de una iniciativa postulada.")
        return redirect("oct:detalle_iniciativa", pk=pk)

    estado_anterior = iniciativa.estado
    iniciativa.estado = Iniciativa.Estado.NO_ADJUDICADA
    iniciativa.save(update_fields=["estado"])
    registrar_movimiento(
        iniciativa, request.user, MovimientoIniciativa.Tipo.CAMBIO_ESTADO,
        detalle="La iniciativa no fue adjudicada.",
        estado_anterior=estado_anterior,
        estado_nuevo=Iniciativa.Estado.NO_ADJUDICADA,
    )
    messages.info(request, "Resultado registrado: no adjudicada.")
    return redirect("oct:detalle_iniciativa", pk=pk)


# =============================================================
# INICIATIVAS — APROBADOR
# =============================================================

@aprobador_required
def panel_aprobacion(request):
    iniciativas = Iniciativa.objects.filter(
        estado=Iniciativa.Estado.ENVIADA
    ).order_by("-fecha_creacion")
    return render(request, "oct/panel_aprobacion.html", {
        "iniciativas": iniciativas,
        "total": iniciativas.count(),
    })


@aprobador_required
def detalle_iniciativa_aprobador(request, pk):
    iniciativa = get_object_or_404(Iniciativa, pk=pk)

    if request.method == "POST":
        accion = request.POST.get("accion")

        if accion == "aprobar":
            if iniciativa.estado != Iniciativa.Estado.ENVIADA:
                messages.warning(request, "Solo se pueden aprobar iniciativas enviadas.")
                return redirect("oct:panel_aprobacion")
            estado_anterior = iniciativa.estado
            iniciativa.estado = Iniciativa.Estado.APROBADA
            iniciativa.save(update_fields=["estado"])
            registrar_movimiento(
                iniciativa, request.user, MovimientoIniciativa.Tipo.APROBACION,
                detalle="Iniciativa aprobada por la OCT.",
                estado_anterior=estado_anterior,
                estado_nuevo=iniciativa.estado,
            )
            messages.success(request, "Iniciativa aprobada correctamente.")

        elif accion == "devolver":
            if iniciativa.estado != Iniciativa.Estado.ENVIADA:
                messages.warning(request, "Solo se pueden devolver iniciativas enviadas.")
                return redirect("oct:panel_aprobacion")
            observaciones = (request.POST.get("observaciones") or "").strip()
            if not observaciones:
                messages.error(request, "Debes indicar las observaciones para devolver la iniciativa.")
                return redirect("oct:detalle_aprobador", pk=iniciativa.pk)
            estado_anterior = iniciativa.estado
            iniciativa.estado = Iniciativa.Estado.DEVUELTA
            iniciativa.observaciones = observaciones
            iniciativa.save(update_fields=["estado", "observaciones"])
            registrar_movimiento(
                iniciativa, request.user, MovimientoIniciativa.Tipo.DEVOLUCION,
                detalle=f'Devuelta con observaciones: "{observaciones}"',
                estado_anterior=estado_anterior,
                estado_nuevo=iniciativa.estado,
            )
            messages.warning(request, "Iniciativa devuelta con observaciones.")

        return redirect("oct:panel_aprobacion")

    return render(request, "oct/detalle_aprobador.html", {"iniciativa": iniciativa})


# =============================================================
# FORMULACIÓN — RESPONSABLE
# =============================================================

@login_required
def formular_iniciativas(request):
    iniciativas = Iniciativa.objects.filter(
        responsable=request.user,
        estado=Iniciativa.Estado.APROBADA,
    ).select_related("formulacion")

    return render(request, "oct/formular_iniciativas.html", {
        "iniciativas": iniciativas,
        "form": FormulacionForm(),
    })


@login_required
def formular_iniciativa(request, pk):
    iniciativa = get_object_or_404(
        Iniciativa,
        pk=pk,
        responsable=request.user,
        estado=Iniciativa.Estado.APROBADA,
    )

    if request.method == "POST":
        form = FormulacionForm(request.POST)
        if form.is_valid():
            formulacion = form.save(commit=False)
            formulacion.iniciativa = iniciativa
            formulacion.save()
            registrar_movimiento(
                iniciativa, request.user, MovimientoIniciativa.Tipo.FORMULACION,
                detalle=f'Formulación creada para el fondo "{formulacion.nombre_fondo}".',
            )
            return redirect("oct:formular_iniciativas")
    else:
        form = FormulacionForm()

    return render(request, "oct/formular_iniciativa.html", {
        "form": form,
        "iniciativa": iniciativa,
    })


@login_required
@require_POST
def guardar_formulacion(request, pk):
    iniciativa = get_object_or_404(
        Iniciativa,
        pk=pk,
        responsable=request.user,
        estado=Iniciativa.Estado.APROBADA,
    )

    if hasattr(iniciativa, "formulacion"):
        messages.warning(request, "Esta iniciativa ya tiene una formulación.")
        return redirect("oct:formular_iniciativas")

    form = FormulacionForm(request.POST)
    if form.is_valid():
        formulacion = form.save(commit=False)
        formulacion.iniciativa = iniciativa
        formulacion.save()
        registrar_movimiento(
            iniciativa, request.user, MovimientoIniciativa.Tipo.FORMULACION,
            detalle=f'Formulación creada para el fondo "{formulacion.nombre_fondo}".',
        )
        messages.success(request, "Formulación guardada correctamente.")
    else:
        messages.error(request, "Revisa los datos de la formulación.")

    return redirect("oct:formular_iniciativas")


@login_required
def ver_formulacion(request, iniciativa_id):
    iniciativa = get_object_or_404(Iniciativa, id=iniciativa_id)
    if not puede_ver_iniciativa(request.user, iniciativa):
        raise PermissionDenied

    return render(request, "oct/ver_formulacion.html", {
        "iniciativa": iniciativa,
        "formulacion": getattr(iniciativa, "formulacion", None),
    })


@login_required
def editar_formulacion(request, pk):
    iniciativa = get_object_or_404(Iniciativa, pk=pk, responsable=request.user)
    formulacion = get_object_or_404(Formulacion, iniciativa=iniciativa)

    estados_editables = [Formulacion.Estado.BORRADOR, Formulacion.Estado.DEVUELTA]
    if formulacion.estado not in estados_editables:
        messages.warning(request, "La formulación no se puede editar en su estado actual.")
        return redirect("oct:formular_iniciativas")

    if request.method == "POST":
        form = FormulacionForm(request.POST, instance=formulacion)
        if form.is_valid():
            formulacion = form.save()
            if "enviar" in request.POST:
                formulacion.estado = Formulacion.Estado.ENVIADA
                formulacion.save(update_fields=["estado"])
                registrar_movimiento(
                    iniciativa, request.user, MovimientoIniciativa.Tipo.FORMULACION,
                    detalle="Formulación enviada a revisión.",
                )
            return redirect("oct:formular_iniciativas")
    else:
        form = FormulacionForm(instance=formulacion)

    return render(request, "oct/editar_formulacion.html", {
        "form": form,
        "iniciativa": iniciativa,
    })


@login_required
@require_POST
def enviar_formulacion(request, pk):
    iniciativa = get_object_or_404(Iniciativa, pk=pk, responsable=request.user)
    formulacion = get_object_or_404(Formulacion, iniciativa=iniciativa)

    estados_enviables = [Formulacion.Estado.BORRADOR, Formulacion.Estado.DEVUELTA]
    if formulacion.estado not in estados_enviables:
        messages.warning(request, "La formulación ya fue enviada o aprobada.")
        return redirect("oct:formular_iniciativas")

    formulacion.estado = Formulacion.Estado.ENVIADA
    formulacion.save(update_fields=["estado"])
    registrar_movimiento(
        iniciativa, request.user, MovimientoIniciativa.Tipo.FORMULACION,
        detalle="Formulación enviada a revisión.",
    )
    messages.success(request, "Formulación enviada a revisión.")
    return redirect("oct:formular_iniciativas")


@login_required
@require_POST
def subir_documento_formulacion(request, pk):
    formulacion = get_object_or_404(
        Formulacion.objects.select_related("iniciativa"), pk=pk,
    )
    iniciativa = formulacion.iniciativa
    if iniciativa.responsable != request.user:
        raise PermissionDenied

    archivo = request.FILES.get("archivo")
    error = validar_documento(archivo)
    if error:
        messages.error(request, error)
        return redirect("oct:ver_formulacion", iniciativa_id=iniciativa.id)

    DocumentoFormulacion.objects.create(formulacion=formulacion, archivo=archivo)
    registrar_movimiento(
        iniciativa, request.user, MovimientoIniciativa.Tipo.DOCUMENTO,
        detalle=f'Documento de formulación adjuntado: "{archivo.name}".',
    )
    messages.success(request, "Documento adjuntado.")
    return redirect("oct:ver_formulacion", iniciativa_id=iniciativa.id)


@login_required
@require_POST
def eliminar_documento_formulacion(request, pk):
    documento = get_object_or_404(
        DocumentoFormulacion.objects.select_related("formulacion__iniciativa"), pk=pk,
    )
    iniciativa = documento.formulacion.iniciativa
    if iniciativa.responsable != request.user:
        raise PermissionDenied

    nombre = documento.nombre_archivo
    documento.delete()
    registrar_movimiento(
        iniciativa, request.user, MovimientoIniciativa.Tipo.DOCUMENTO,
        detalle=f'Documento de formulación eliminado: "{nombre}".',
    )
    messages.success(request, "Documento eliminado.")
    return redirect("oct:ver_formulacion", iniciativa_id=iniciativa.id)


# =============================================================
# FORMULACIÓN — APROBADOR
# =============================================================

@aprobador_required
def revisar_formulaciones(request):
    formulaciones = Formulacion.objects.select_related("iniciativa").filter(
        estado=Formulacion.Estado.ENVIADA
    )
    return render(request, "oct/revisar_formulaciones.html", {
        "formulaciones": formulaciones,
        "total": formulaciones.count(),
    })


@aprobador_required
@require_POST
def aprobar_formulacion(request, pk):
    formulacion = get_object_or_404(
        Formulacion.objects.select_related("iniciativa"), pk=pk,
    )
    if formulacion.estado != Formulacion.Estado.ENVIADA:
        messages.warning(request, "Solo se pueden aprobar formulaciones enviadas.")
        return redirect("oct:revisar_formulaciones")

    formulacion.estado = Formulacion.Estado.APROBADA
    formulacion.save(update_fields=["estado"])

    # Al aprobar la formulación, la iniciativa avanza a "Postulada".
    iniciativa = formulacion.iniciativa
    estado_anterior = iniciativa.estado
    iniciativa.estado = Iniciativa.Estado.POSTULADA
    iniciativa.save(update_fields=["estado"])
    registrar_movimiento(
        iniciativa, request.user, MovimientoIniciativa.Tipo.APROBACION,
        detalle="Formulación aprobada. La iniciativa pasa a Postulada.",
        estado_anterior=estado_anterior,
        estado_nuevo=iniciativa.estado,
    )
    messages.success(request, "Formulación aprobada. La iniciativa quedó como postulada.")
    return redirect("oct:revisar_formulaciones")


@aprobador_required
@require_POST
def devolver_formulacion(request, pk):
    formulacion = get_object_or_404(
        Formulacion.objects.select_related("iniciativa"), pk=pk,
    )
    if formulacion.estado != Formulacion.Estado.ENVIADA:
        messages.warning(request, "Solo se pueden devolver formulaciones enviadas.")
        return redirect("oct:revisar_formulaciones")

    observaciones = (request.POST.get("observaciones") or "").strip()
    if not observaciones:
        messages.error(request, "Debes indicar las observaciones para devolver la formulación.")
        return redirect("oct:revisar_formulaciones")

    formulacion.estado = Formulacion.Estado.DEVUELTA
    formulacion.observaciones = observaciones
    formulacion.save(update_fields=["estado", "observaciones"])
    registrar_movimiento(
        formulacion.iniciativa, request.user, MovimientoIniciativa.Tipo.DEVOLUCION,
        detalle=f'Formulación devuelta con observaciones: "{observaciones}"',
    )
    messages.warning(request, "Formulación devuelta con observaciones.")
    return redirect("oct:revisar_formulaciones")

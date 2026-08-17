import time
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.db.models import Count
from django.http import Http404
from django.urls import reverse

from . import tablero
from .forms import (
    FormulacionForm,
    GestionForm,
    IniciativaForm,
    SubirPlanillaForm,
)
from .models import (
    Ambito,
    DocumentoFormulacion,
    DocumentoIniciativa,
    EstadoGestion,
    Formulacion,
    Gestion,
    Iniciativa,
    MetaAmbito,
    MovimientoIniciativa,
    Origen,
    ProyeccionMensual,
)
from .planilla import (
    CAMPOS as CAMPOS_PLANILLA,
    ErrorImportacion,
    ImportadorPlanilla,
    clave as normalizar,
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


# =============================================================
# TABLERO MAESTRO DE RESULTADOS
#
# Todo lo de acá abajo trabaja sobre la planilla de resultados OCT: el
# registro de gestiones (editable), los parámetros que en el Excel se
# escriben a mano, y la carga del archivo actualizado.
# =============================================================

SUBCARPETA_CARGAS = "oct/cargas"


def _anio_pedido(request):
    """Año en pantalla. Se recuerda en la sesión para no perderlo al navegar."""
    disponibles = tablero.anios_disponibles()
    crudo = request.GET.get("anio") or request.session.get("oct_tablero_anio")
    try:
        anio = int(crudo)
    except (TypeError, ValueError):
        anio = disponibles[0]
    if anio not in disponibles:
        anio = disponibles[0]
    request.session["oct_tablero_anio"] = anio
    return anio, disponibles


@login_required
def tablero_maestro(request):
    """La pantalla de visualización: cabecera, tablero de control y avance mensual."""
    anio, anios = _anio_pedido(request)
    gestiones = list(Gestion.objects.filter(anio=anio))

    filas, total = tablero.tablero_control(anio, gestiones)
    bloques = tablero.avance_mensual(anio, gestiones)
    proyeccion, proyeccion_total = tablero.proyeccion_por_mes(anio)

    # Gráficos: dos preguntas, no un muro de canvas. Cuánto se avanzó contra la
    # meta, y cómo se reparte el dinero a lo largo del año.
    avance_meta = {
        "etiquetas": [f["etiqueta"] for f in filas],
        "meta": [int(f["meta"]) for f in filas],
        "gestiones": [int(f["gestiones"]) for f in filas],
    }

    montos_mes = []
    for i, _ in enumerate(tablero.MESES):
        proyectado = proyeccion_total["meses"][i]
        efectivo = sum(
            (f["meses"][i] for b in bloques for f in b["filas"]
             if f["clave"] == "monto_adjudicado"),
            Decimal("0"),
        )
        montos_mes.append((proyectado, efectivo))

    dinero = {
        "etiquetas": [nombre for _, nombre in tablero.MESES],
        "proyectado": [int(p) for p, _ in montos_mes],
        "efectivo": [int(e) for _, e in montos_mes],
    }

    return render(request, "oct/tablero/tablero.html", {
        "anio": anio,
        "anios": anios,
        "filas": filas,
        "total": total,
        "bloques": bloques,
        "meses": tablero.MESES,
        "proyeccion": proyeccion,
        "proyeccion_total": proyeccion_total,
        "n_gestiones": len(gestiones),
        "editadas": sum(1 for g in gestiones if g.editada_en_sistema),
        "grafico_avance": avance_meta,
        "grafico_dinero": dinero,
        "colores": {
            "serie": tablero.COLOR_SERIE,
            "serie2": tablero.COLOR_SERIE_2,
            "apagado": tablero.COLOR_APAGADO,
        },
    })


@login_required
def tablero_registro(request):
    """El registro de gestiones, que es lo único que se edita a mano."""
    anio, anios = _anio_pedido(request)

    gestiones = Gestion.objects.filter(anio=anio)

    filtro_ambito = request.GET.get("ambito") or ""
    filtro_estado = request.GET.get("estado") or ""
    busqueda = (request.GET.get("q") or "").strip()

    if filtro_ambito:
        gestiones = gestiones.filter(ambito=filtro_ambito)
    if filtro_estado:
        gestiones = gestiones.filter(estado=filtro_estado)

    gestiones = list(gestiones.select_related("editado_por"))

    if busqueda:
        # La búsqueda se hace en Python a propósito. El `icontains` de SQLite
        # solo ignora mayúsculas en ASCII, así que "inglés" no encontraba
        # "CURSO DE INGLÉS"; comparando sin tildes ni mayúsculas sí. Son unas
        # pocas decenas de filas por año: no hay nada que optimizar.
        aguja = normalizar(busqueda)
        gestiones = [
            g for g in gestiones
            if aguja in normalizar(
                f"{g.nombre} {g.codigo} {g.institucion} {g.responsable} {g.tipo}")
        ]

    # Los conteos de los chips se calculan sobre el año completo, no sobre el
    # filtro: si no, al filtrar quedan todos en cero menos uno.
    del_anio = Gestion.objects.filter(anio=anio)
    conteos = {
        fila["ambito"]: fila["n"]
        for fila in del_anio.values("ambito").annotate(n=Count("id"))
    }
    chips = [
        {"valor": valor, "etiqueta": etiqueta, "n": conteos.get(valor, 0)}
        for valor, etiqueta in Ambito.choices
    ]

    return render(request, "oct/tablero/registro.html", {
        "anio": anio,
        "anios": anios,
        "gestiones": gestiones,
        "total_anio": del_anio.count(),
        "chips": chips,
        "ambitos": Ambito.choices,
        "estados": EstadoGestion.choices,
        "filtro_ambito": filtro_ambito,
        "filtro_estado": filtro_estado,
        "busqueda": busqueda,
    })


@login_required
def tablero_gestion_nueva(request):
    anio, _ = _anio_pedido(request)

    if request.method == "POST":
        form = GestionForm(request.POST)
        if form.is_valid():
            gestion = form.save(commit=False)
            gestion.anio = anio
            gestion.origen = Origen.MANUAL
            gestion.save()
            messages.success(request, f"Se agregó «{gestion.nombre}» al registro.")
            return redirect("oct:tablero_registro")
    else:
        form = GestionForm()

    return render(request, "oct/tablero/gestion_form.html", {
        "form": form, "anio": anio, "es_nueva": True,
    })


@login_required
def tablero_gestion_editar(request, pk):
    """Edición de una gestión.

    Acá está la mitad del trato con el Excel: se anota qué campos se tocaron,
    para que la próxima carga del archivo no los pise sin preguntar.
    """
    gestion = get_object_or_404(Gestion, pk=pk)

    if request.method == "POST":
        form = GestionForm(request.POST, instance=gestion)
        if form.is_valid():
            tocados = [c for c in form.changed_data if c in CAMPOS_PLANILLA]
            gestion = form.save(commit=False)
            protegidos = tocados and gestion.origen == Origen.IMPORTADO
            if protegidos:
                gestion.marcar_editada(tocados, request.user)
            gestion.save()
            if protegidos:
                messages.success(request, (
                    f"Guardado. La próxima carga del Excel preguntará antes de "
                    f"pisar {len(tocados)} campo{'s' if len(tocados) != 1 else ''} "
                    f"que acaba de editar."))
            else:
                messages.success(request, "Gestión actualizada.")
            return redirect("oct:tablero_registro")
    else:
        form = GestionForm(instance=gestion)

    return render(request, "oct/tablero/gestion_form.html", {
        "form": form, "gestion": gestion, "anio": gestion.anio, "es_nueva": False,
    })


@login_required
def tablero_gestion_eliminar(request, pk):
    gestion = get_object_or_404(Gestion, pk=pk)

    if request.method == "POST":
        nombre = gestion.nombre
        gestion.delete()
        messages.warning(request, f"Se eliminó «{nombre}» del registro.")
        return redirect("oct:tablero_registro")

    return render(request, "oct/tablero/gestion_eliminar.html", {"gestion": gestion})


def _entero(crudo):
    try:
        return max(0, int(float(str(crudo).replace(".", "").strip() or 0)))
    except (TypeError, ValueError):
        return 0


def _monto(crudo):
    limpio = str(crudo or "").replace("$", "").replace(".", "").replace(" ", "").strip()
    try:
        return Decimal(limpio or "0").quantize(Decimal("1"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


@login_required
def tablero_parametros(request):
    """Los dos datos que en el Excel se escriben a mano: la meta anual de
    gestiones y la proyección de ingresos mes a mes."""
    anio, anios = _anio_pedido(request)

    if request.method == "POST":
        guardados = 0
        for ambito, _etiqueta in Ambito.choices:
            meta, _ = MetaAmbito.objects.get_or_create(anio=anio, ambito=ambito)
            nueva = _entero(request.POST.get(f"meta-{ambito}"))
            if meta.meta_gestiones != nueva:
                meta.meta_gestiones = nueva
                meta.save(update_fields=["meta_gestiones"])
                guardados += 1

            for mes, _nombre in tablero.MESES:
                celda, _ = ProyeccionMensual.objects.get_or_create(
                    anio=anio, ambito=ambito, mes=mes)
                monto = _monto(request.POST.get(f"proy-{ambito}-{mes}"))
                if celda.monto != monto:
                    celda.monto = monto
                    celda.save(update_fields=["monto"])
                    guardados += 1

        if guardados:
            messages.success(request, f"Se guardaron {guardados} cambios.")
        else:
            messages.info(request, "No hubo cambios que guardar.")
        return redirect(f"{reverse('oct:tablero_parametros')}?anio={anio}")

    metas = {
        m.ambito: m.meta_gestiones
        for m in MetaAmbito.objects.filter(anio=anio)
    }
    guardado = {
        (p.ambito, p.mes): p.monto
        for p in ProyeccionMensual.objects.filter(anio=anio)
    }

    filas = []
    for ambito, etiqueta in Ambito.choices:
        celdas = [
            {"mes": mes, "valor": guardado.get((ambito, mes), Decimal("0"))}
            for mes, _ in tablero.MESES
        ]
        filas.append({
            "ambito": ambito,
            "etiqueta": etiqueta,
            "meta": metas.get(ambito, 0),
            "celdas": celdas,
            "total": sum((c["valor"] for c in celdas), Decimal("0")),
        })

    return render(request, "oct/tablero/parametros.html", {
        "anio": anio, "anios": anios, "filas": filas, "meses": tablero.MESES,
    })


def _ruta_carga(nombre):
    """Ruta absoluta de un archivo subido, validando que no escape la carpeta."""
    base = Path(settings.MEDIA_ROOT) / SUBCARPETA_CARGAS
    destino = (base / nombre).resolve()
    if base.resolve() not in destino.parents:
        raise Http404("Archivo no válido.")
    return destino


# Cuánto se guarda un archivo subido a la espera de que confirmen la vista
# previa. Quien analiza y se arrepiente deja el .xlsx en el disco: sin esta
# limpieza, la carpeta crece para siempre.
HORAS_DE_GRACIA = 24


def _limpiar_cargas_viejas(carpeta):
    limite = time.time() - HORAS_DE_GRACIA * 3600
    for viejo in carpeta.glob("*.xlsx"):
        try:
            if viejo.stat().st_mtime < limite:
                viejo.unlink()
        except OSError:
            continue    # si otro proceso ya lo borró, no es problema


@login_required
def tablero_importar(request):
    """Carga del Excel actualizado, con vista previa antes de guardar.

    Dos pasos a propósito: primero se muestra qué cambiaría —incluidos los
    choques con lo que se editó en pantalla— y recién entonces se aplica.
    """
    if request.method != "POST":
        return render(request, "oct/tablero/importar.html", {
            "form": SubirPlanillaForm(),
        })

    # --- Paso 2: confirmar una vista previa ya hecha ---
    if request.POST.get("confirmar"):
        nombre = request.session.get("oct_carga")
        if not nombre:
            messages.error(request, "La vista previa expiró. Suba el archivo otra vez.")
            return redirect("oct:tablero_importar")

        ruta = _ruta_carga(nombre)
        opciones = request.session.get("oct_carga_opciones", {})
        decisiones = {c: True for c in request.POST.getlist("usar_excel")}

        try:
            resultado = ImportadorPlanilla(
                ruta, decisiones=decisiones, usuario=request.user, **opciones
            ).ejecutar(aplicar=True)
        except ErrorImportacion as exc:
            messages.error(request, str(exc))
            return redirect("oct:tablero_importar")

        request.session.pop("oct_carga", None)
        request.session.pop("oct_carga_opciones", None)
        ruta.unlink(missing_ok=True)

        if resultado.hay_cambios:
            n = len(resultado.relevantes)
            messages.success(
                request, f"Se aplicó {n} cambio{'s' if n != 1 else ''}.")
        else:
            messages.info(request, "El archivo ya estaba reflejado: no hubo cambios.")

        return render(request, "oct/tablero/importar.html", {
            "form": SubirPlanillaForm(),
            "resultado": resultado,
            "aplicado": True,
        })

    # --- Paso 1: subir y previsualizar ---
    form = SubirPlanillaForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "oct/tablero/importar.html", {"form": form})

    carpeta = Path(settings.MEDIA_ROOT) / SUBCARPETA_CARGAS
    carpeta.mkdir(parents=True, exist_ok=True)
    _limpiar_cargas_viejas(carpeta)

    nombre = f"{uuid4().hex}.xlsx"
    ruta = carpeta / nombre
    with ruta.open("wb") as destino:
        for trozo in form.cleaned_data["archivo"].chunks():
            destino.write(trozo)

    opciones = {"podar": form.cleaned_data["podar"]}
    try:
        resultado = ImportadorPlanilla(ruta, usuario=request.user, **opciones).ejecutar()
    except ErrorImportacion as exc:
        ruta.unlink(missing_ok=True)
        messages.error(request, str(exc))
        return render(request, "oct/tablero/importar.html", {"form": form})

    request.session["oct_carga"] = nombre
    request.session["oct_carga_opciones"] = opciones

    return render(request, "oct/tablero/importar.html", {
        "form": form,
        "resultado": resultado,
        "previsualizacion": True,
        "archivo_original": form.cleaned_data["archivo"].name,
    })

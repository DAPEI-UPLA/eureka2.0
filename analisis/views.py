from collections import defaultdict

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.db.models import Count
from django.core.exceptions import PermissionDenied

from .forms import InformeForm
from .models import Informe, MovimientoInforme


ESTADOS_ORDEN = [
    Informe.Estado.PENDIENTE,
    Informe.Estado.EN_PROCESO,
    Informe.Estado.EN_REVISION,
    Informe.Estado.FINALIZADO,
    Informe.Estado.SUSPENDIDO,
]

ESTADOS_COLORES = {
    Informe.Estado.PENDIENTE:   "#94a3b8",
    Informe.Estado.EN_PROCESO:  "#009fe3",
    Informe.Estado.EN_REVISION: "#f59e0b",
    Informe.Estado.FINALIZADO:  "#22c55e",
    Informe.Estado.SUSPENDIDO:  "#ef4444",
}


def es_encargado_analisis(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name="encargado_analisis").exists()
    )


def puede_gestionar_informe(user, informe):
    """Un informe lo gestiona (edita/elimina/envía) su responsable o un encargado."""
    return es_encargado_analisis(user) or informe.responsable_id == user.id


@login_required
def analisis_home(request):
    return render(request, "analisis/home.html")


@login_required
def panel_informes(request):
    informes = Informe.objects.all()

    conteo = {e.value: 0 for e in Informe.Estado}
    for fila in informes.values("estado").annotate(n=Count("id")):
        conteo[fila["estado"]] = fila["n"]

    stats = {
        "total": informes.count(),
        "pendiente": conteo.get(Informe.Estado.PENDIENTE, 0),
        "en_proceso": conteo.get(Informe.Estado.EN_PROCESO, 0),
        "en_revision": conteo.get(Informe.Estado.EN_REVISION, 0),
        "finalizado": conteo.get(Informe.Estado.FINALIZADO, 0),
        "suspendido": conteo.get(Informe.Estado.SUSPENDIDO, 0),
    }

    return render(request, "analisis/panel_informes.html", {
        "informes": informes,
        "stats": stats,
        "es_encargado": es_encargado_analisis(request.user),
    })


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _form_response(request, form, informe=None, modo="crear", action_url=""):
    template = "analisis/_informe_form.html" if _is_htmx(request) else "analisis/informe_form.html"
    return render(request, template, {
        "form": form,
        "informe": informe,
        "modo": modo,
        "action_url": action_url,
    })


@login_required
def crear_informe(request):
    from django.urls import reverse
    action_url = reverse("analisis:crear_informe")

    if request.method == "POST":
        form = InformeForm(request.POST)
        if form.is_valid():
            informe = form.save(commit=False)
            informe.responsable = request.user
            informe.save()

            MovimientoInforme.objects.create(
                informe=informe,
                usuario=request.user,
                tipo=MovimientoInforme.Tipo.CREACION,
                estado_nuevo=informe.estado,
                detalle=f'Informe creado: "{informe.nombre}".',
            )

            messages.success(request, "Informe creado correctamente.")
            if _is_htmx(request):
                resp = HttpResponse(status=204)
                resp["HX-Refresh"] = "true"
                return resp
            return redirect("analisis:panel_informes")
    else:
        form = InformeForm()

    return _form_response(request, form, modo="crear", action_url=action_url)


@login_required
def editar_informe(request, pk):
    from django.urls import reverse
    informe = get_object_or_404(Informe, pk=pk)
    if not puede_gestionar_informe(request.user, informe):
        raise PermissionDenied
    action_url = reverse("analisis:editar_informe", args=[pk])

    if request.method == "POST":
        snapshot = {
            "nombre": informe.nombre,
            "descripcion": informe.descripcion,
            "estado": informe.estado,
            "fecha_estimada_termino": informe.fecha_estimada_termino,
        }

        form = InformeForm(request.POST, instance=informe)
        if form.is_valid():
            informe = form.save()

            if snapshot["estado"] != informe.estado:
                MovimientoInforme.objects.create(
                    informe=informe,
                    usuario=request.user,
                    tipo=MovimientoInforme.Tipo.CAMBIO_ESTADO,
                    estado_anterior=snapshot["estado"],
                    estado_nuevo=informe.estado,
                    detalle=(
                        f'Estado: "{Informe.Estado(snapshot["estado"]).label}" → '
                        f'"{Informe.Estado(informe.estado).label}".'
                    ),
                )

            cambios = []
            if snapshot["nombre"] != informe.nombre:
                cambios.append(f'Nombre: "{snapshot["nombre"]}" → "{informe.nombre}".')
            if snapshot["descripcion"] != informe.descripcion:
                cambios.append("Descripción actualizada.")
            if snapshot["fecha_estimada_termino"] != informe.fecha_estimada_termino:
                def _f(d):
                    return d.strftime("%d/%m/%Y") if d else "sin fecha"
                cambios.append(
                    f'Fecha estimada: {_f(snapshot["fecha_estimada_termino"])} → '
                    f'{_f(informe.fecha_estimada_termino)}.'
                )

            if cambios:
                MovimientoInforme.objects.create(
                    informe=informe,
                    usuario=request.user,
                    tipo=MovimientoInforme.Tipo.EDICION,
                    detalle=" ".join(cambios),
                )

            messages.success(request, "Informe actualizado correctamente.")
            if _is_htmx(request):
                resp = HttpResponse(status=204)
                resp["HX-Refresh"] = "true"
                return resp
            return redirect("analisis:panel_informes")
    else:
        form = InformeForm(instance=informe)

    return _form_response(request, form, informe=informe, modo="editar", action_url=action_url)


@login_required
def trazabilidad_informe(request, pk):
    if not es_encargado_analisis(request.user):
        raise PermissionDenied

    informe = get_object_or_404(Informe, pk=pk)
    movimientos = informe.movimientos.select_related("usuario").order_by("fecha")

    template = (
        "analisis/_trazabilidad.html"
        if _is_htmx(request)
        else "analisis/trazabilidad.html"
    )

    return render(request, template, {
        "informe": informe,
        "movimientos": movimientos,
    })


@login_required
def graficos_informes(request):
    informes_qs = Informe.objects.all()

    # ====== Distribución por estado ======
    conteo_estado = {e.value: 0 for e in Informe.Estado}
    for fila in informes_qs.values("estado").annotate(n=Count("id")):
        conteo_estado[fila["estado"]] = fila["n"]

    datos_estado = {
        "labels": [Informe.Estado(e).label for e in ESTADOS_ORDEN],
        "data":   [conteo_estado.get(e, 0) for e in ESTADOS_ORDEN],
        "colors": [ESTADOS_COLORES[e] for e in ESTADOS_ORDEN],
    }

    # ====== Por responsable, desglosado por estado ======
    resp_data = defaultdict(lambda: defaultdict(int))
    for fila in informes_qs.values(
        "responsable__username",
        "responsable__first_name",
        "responsable__last_name",
        "estado",
    ).annotate(n=Count("id")):
        full = f"{fila['responsable__first_name'] or ''} {fila['responsable__last_name'] or ''}".strip()
        nombre = full or fila["responsable__username"] or "Sin asignar"
        resp_data[nombre][fila["estado"]] += fila["n"]

    responsables = sorted(resp_data.keys(), key=lambda r: -sum(resp_data[r].values()))

    datasets = []
    for estado in ESTADOS_ORDEN:
        datasets.append({
            "label": Informe.Estado(estado).label,
            "data": [resp_data[r].get(estado, 0) for r in responsables],
            "backgroundColor": ESTADOS_COLORES[estado],
            "borderRadius": 6,
            "maxBarThickness": 38,
        })

    datos_responsables = {
        "labels": responsables,
        "datasets": datasets,
    }

    # ====== Resumen tabla por responsable ======
    resumen_responsables = []
    for r in responsables:
        total = sum(resp_data[r].values())
        fin = resp_data[r].get(Informe.Estado.FINALIZADO, 0)
        resumen_responsables.append({
            "nombre": r,
            "total": total,
            "pendiente":   resp_data[r].get(Informe.Estado.PENDIENTE, 0),
            "en_proceso":  resp_data[r].get(Informe.Estado.EN_PROCESO, 0),
            "en_revision": resp_data[r].get(Informe.Estado.EN_REVISION, 0),
            "finalizado":  fin,
            "suspendido":  resp_data[r].get(Informe.Estado.SUSPENDIDO, 0),
            "avance":      round((fin / total) * 100) if total else 0,
        })

    stats = {
        "total": informes_qs.count(),
        "pendiente":   conteo_estado.get(Informe.Estado.PENDIENTE, 0),
        "en_proceso":  conteo_estado.get(Informe.Estado.EN_PROCESO, 0),
        "en_revision": conteo_estado.get(Informe.Estado.EN_REVISION, 0),
        "finalizado":  conteo_estado.get(Informe.Estado.FINALIZADO, 0),
        "suspendido":  conteo_estado.get(Informe.Estado.SUSPENDIDO, 0),
    }

    return render(request, "analisis/graficos_informes.html", {
        "stats": stats,
        "datos_estado": datos_estado,
        "datos_responsables": datos_responsables,
        "resumen_responsables": resumen_responsables,
        "hay_datos": informes_qs.exists(),
        "es_encargado": es_encargado_analisis(request.user),
    })


def _htmx_refresh_or_redirect(request, target="analisis:panel_informes"):
    if _is_htmx(request):
        resp = HttpResponse(status=204)
        resp["HX-Refresh"] = "true"
        return resp
    return redirect(target)


EXTENSIONES_DOC_VALIDAS = (".pdf", ".doc", ".docx")
MIME_DOC_VALIDOS = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # Algunos navegadores envían genéricos; aceptamos si la extensión calza:
    "application/octet-stream",
}
MAX_DOC_BYTES = 10 * 1024 * 1024  # 10 MB

# Firmas (magic bytes) reales de cada formato aceptado. El content_type lo
# envía el cliente y es falsificable; esto valida el contenido real.
FIRMAS_DOC = (
    b"%PDF",            # PDF
    b"PK\x03\x04",      # DOCX (contenedor ZIP de OOXML)
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",  # DOC antiguo (OLE2)
)


def _validar_documento(archivo):
    """Valida un documento adjunto. Devuelve un mensaje de error o None si es OK."""
    if not archivo:
        return "Debes adjuntar un documento PDF o Word para enviar a revisión."

    if not archivo.name.lower().endswith(EXTENSIONES_DOC_VALIDAS):
        return "Solo se aceptan archivos PDF o Word (.pdf, .doc, .docx)."

    if archivo.content_type not in MIME_DOC_VALIDOS:
        return "El archivo no parece ser un PDF o Word válido."

    if archivo.size > MAX_DOC_BYTES:
        return "El documento no puede superar los 10 MB."

    # Verificación del contenido real por firma de archivo.
    cabecera = archivo.read(8)
    archivo.seek(0)
    if not any(cabecera.startswith(firma) for firma in FIRMAS_DOC):
        return "El archivo no es un PDF o Word válido (contenido no reconocido)."

    return None


@login_required
@require_POST
def enviar_a_revision(request, pk):
    informe = get_object_or_404(Informe, pk=pk)
    if not puede_gestionar_informe(request.user, informe):
        raise PermissionDenied

    if informe.estado != Informe.Estado.EN_PROCESO:
        messages.warning(request, "Solo puedes enviar a revisión informes en proceso.")
        return _htmx_refresh_or_redirect(request)

    archivo = request.FILES.get("documento")
    error = _validar_documento(archivo)
    if error:
        messages.error(request, error)
        return _htmx_refresh_or_redirect(request)

    estado_anterior = informe.estado
    informe.estado = Informe.Estado.EN_REVISION
    informe.save()

    MovimientoInforme.objects.create(
        informe=informe,
        usuario=request.user,
        tipo=MovimientoInforme.Tipo.CAMBIO_ESTADO,
        estado_anterior=estado_anterior,
        estado_nuevo=informe.estado,
        documento=archivo,
        detalle=(
            f'Estado: "{Informe.Estado(estado_anterior).label}" → '
            f'"{Informe.Estado(informe.estado).label}" '
            f'(enviado a revisión con documento "{archivo.name}").'
        ),
    )

    messages.success(request, "Informe enviado a revisión con el documento adjunto.")
    return _htmx_refresh_or_redirect(request)


@login_required
@require_POST
def aprobar_informe(request, pk):
    if not es_encargado_analisis(request.user):
        raise PermissionDenied

    informe = get_object_or_404(Informe, pk=pk)

    if informe.estado != Informe.Estado.EN_REVISION:
        messages.warning(request, "Solo se pueden aprobar informes en revisión.")
        return _htmx_refresh_or_redirect(request)

    comentario = (request.POST.get("comentario") or "").strip()
    estado_anterior = informe.estado
    informe.estado = Informe.Estado.FINALIZADO
    informe.save()

    nombre_usuario = request.user.get_full_name() or request.user.username
    detalle = f"Informe aprobado por {nombre_usuario}."
    if comentario:
        detalle += f' Comentario: "{comentario}"'

    MovimientoInforme.objects.create(
        informe=informe,
        usuario=request.user,
        tipo=MovimientoInforme.Tipo.APROBACION,
        estado_anterior=estado_anterior,
        estado_nuevo=informe.estado,
        detalle=detalle,
    )

    messages.success(request, "Informe aprobado correctamente.")
    return _htmx_refresh_or_redirect(request)


@login_required
@require_POST
def rechazar_informe(request, pk):
    if not es_encargado_analisis(request.user):
        raise PermissionDenied

    informe = get_object_or_404(Informe, pk=pk)

    if informe.estado != Informe.Estado.EN_REVISION:
        messages.warning(request, "Solo se pueden devolver informes en revisión.")
        return _htmx_refresh_or_redirect(request)

    observaciones = (request.POST.get("observaciones") or "").strip()
    if not observaciones:
        messages.error(request, "Debes indicar las observaciones para devolver el informe.")
        return _htmx_refresh_or_redirect(request)

    estado_anterior = informe.estado
    informe.estado = Informe.Estado.EN_PROCESO
    informe.save()

    nombre_usuario = request.user.get_full_name() or request.user.username
    detalle = f'Informe devuelto por {nombre_usuario}. Observaciones: "{observaciones}"'

    MovimientoInforme.objects.create(
        informe=informe,
        usuario=request.user,
        tipo=MovimientoInforme.Tipo.RECHAZO,
        estado_anterior=estado_anterior,
        estado_nuevo=informe.estado,
        detalle=detalle,
    )

    messages.success(request, "Informe devuelto con observaciones.")
    return _htmx_refresh_or_redirect(request)


@login_required
@require_POST
def eliminar_informe(request, pk):
    informe = get_object_or_404(Informe, pk=pk)
    if not puede_gestionar_informe(request.user, informe):
        raise PermissionDenied
    informe.delete()
    messages.success(request, "Informe eliminado correctamente.")
    if _is_htmx(request):
        resp = HttpResponse(status=204)
        resp["HX-Refresh"] = "true"
        return resp
    return redirect("analisis:panel_informes")

"""Pantallas del módulo de Evaluación de Desempeño.

Dos instrumentos conviven aquí y conviene no confundirlos:

* el **oficial**, réplica exacta del Excel validado, disponible por ahora solo
  para el T2 de Tesorería: pesos por ítem, factores UPLA y asistencia;
* el **genérico**, que arma los ítems desde el texto del perfil de cualquier
  cargo y promedia parejo, porque esos ítems no tienen peso asignado todavía.

El resultado de una evaluación no se guarda: estas vistas calculan y muestran.
Lo único que persiste es el nivel requerido de cada ítem, que es definición del
cargo y no medición de una persona.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone

from . import perfiles as perf
from .estructura import es_cargo, raices, recorrer
from .models import NIVEL_POR_DEFECTO, guardar_niveles, niveles_de
from .motor import (
    DatosAsistencia, asistencia_t2, evaluar, evaluar_generico, perfil_t2,
)

CARGO_INSTRUMENTO = "Técnico Educación Superior Senior – T2"


@login_required
def home(request):
    return render(request, "evaluaciones/home.html", {"raices": raices()})


@login_required
def nodo(request, ruta):
    """Navegación del organigrama: una rama muestra sus hijos, un cargo su ficha."""
    actual, breadcrumb, color = recorrer(ruta)

    if es_cargo(actual):
        datos = perf.perfil_de(actual.get("perfil"))
        perfil = None
        if datos:
            perfil = {"tipo": actual["perfil"][1], "campos": perf.campos_visibles(datos)}
        return render(request, "evaluaciones/cargo.html", {
            "actual": actual, "breadcrumb": breadcrumb, "color": color,
            "perfil": perfil, "instrumento": actual.get("instrumento"),
            "volver_ruta": breadcrumb[-2]["ruta"] if len(breadcrumb) >= 2 else None,
            "cargo_ruta": ruta.strip("/"),
        })

    tarjetas = []
    for hijo_id, hijo in (actual.get("hijos") or {}).items():
        ruta_hijo = f"{ruta.strip('/')}/{hijo_id}"
        if es_cargo(hijo):
            tarjetas.append({
                "tipo": "cargo", "nombre": hijo["nombre"], "ruta": ruta_hijo,
                "area": hijo.get("area", ""), "instrumento": hijo.get("instrumento"),
                "tiene_perfil": bool(hijo.get("perfil")),
            })
        else:
            nietos = hijo.get("hijos") or {}
            tiene_ramas = any(not es_cargo(x) for x in nietos.values())
            tarjetas.append({
                "tipo": "rama", "nombre": hijo["nombre"], "ruta": ruta_hijo,
                "n": len(nietos), "label": "áreas" if tiene_ramas else "perfiles",
            })

    return render(request, "evaluaciones/nodo.html", {
        "actual": actual, "breadcrumb": breadcrumb, "color": color,
        "cards": tarjetas,
    })


def _nivel(valor, por_defecto=0):
    """Lee un nivel del formulario acotado a la escala 0-4.

    Los <select> solo ofrecen 0..4, pero el POST llega por HTTP y nada impide
    mandar 9 a mano: con un requerido de 9 la brecha crece y la nota baja sin
    que la pantalla muestre de dónde salió.
    """
    try:
        return min(max(int(valor), 0), 4)
    except (TypeError, ValueError):
        return por_defecto


@login_required
def evaluar_cargo(request, ruta):
    """Instrumento genérico: evalúa un cargo con los ítems de su propio perfil."""
    actual, breadcrumb, color = recorrer(ruta)
    if not es_cargo(actual):
        raise Http404("El nodo no es un cargo")

    ruta = ruta.strip("/")
    datos = perf.perfil_de(actual.get("perfil"))
    secciones_def = perf.secciones_evaluables(datos)

    guardado = niveles_de(ruta)
    requeridos = {c: guardado.get(c, NIVEL_POR_DEFECTO) for c in perf.claves(secciones_def)}
    observados = {c: 0 for c in requeridos}

    resultado = None
    guardado_ok = False
    if request.method == "POST":
        for clave in requeridos:
            requeridos[clave] = _nivel(request.POST.get(f"req_{clave}"), requeridos[clave])
            observados[clave] = _nivel(request.POST.get(f"obs_{clave}"))
        # El nivel requerido se guarda con cualquiera de los dos botones: es
        # definición del cargo, no parte del cálculo que se está haciendo.
        guardar_niveles(ruta, requeridos)
        guardado_ok = True
        if request.POST.get("accion") == "calcular":
            resultado = evaluar_generico(secciones_def, requeridos, observados)

    secciones = [{
        "titulo": s["titulo"],
        "items": [{"key": f"{s['id']}-{i}", "texto": texto,
                   "req": requeridos[f"{s['id']}-{i}"],
                   "obs": observados[f"{s['id']}-{i}"]}
                  for i, texto in enumerate(s["items"])],
    } for s in secciones_def]

    return render(request, "evaluaciones/evaluar_cargo.html", {
        "actual": actual, "breadcrumb": breadcrumb, "color": color,
        "secciones": secciones, "escala": perf.ESCALA_NIVEL, "resultado": resultado,
        "perfil_tipo": actual["perfil"][1] if actual.get("perfil") else None,
        "ficha_ruta": ruta, "guardado_ok": guardado_ok,
        "sin_perfil": datos is None,
        "nivel_por_defecto": NIVEL_POR_DEFECTO,
    })


def _dias(valor):
    """Lee un contador de días del formulario; nunca negativo."""
    try:
        return max(int(valor), 0)
    except (TypeError, ValueError):
        return 0


def _leer_instrumento(request):
    """Arma (elementos, asistencia, identificación) desde el POST del formulario."""
    elementos = perfil_t2()
    for e in elementos:
        e.nivel_observado = _nivel(request.POST.get(f"obs_{e.id}"))

    asistencia = DatosAsistencia(**{campo: _dias(request.POST.get(campo))
                                    for campo, _ in perf.CAMPOS_ASISTENCIA})
    ident = {campo: request.POST.get(campo, "").strip() for campo, _ in perf.CAMPOS_IDENT}
    return elementos, asistencia, ident


@login_required
def instrumento(request):
    """Instrumento oficial del T2 de Tesorería (la réplica validada del Excel)."""
    if request.method == "POST":
        elementos, asistencia, ident = _leer_instrumento(request)
        resultado = evaluar(elementos, asistencia)
    else:
        elementos = perfil_t2()
        asistencia = asistencia_t2()
        ident = {campo: "" for campo, _ in perf.CAMPOS_IDENT}
        resultado = None

    return render(request, "evaluaciones/instrumento.html", {
        "secciones": _agrupar(elementos),
        "escala": perf.ESCALA_NIVEL,
        "campos_asistencia": [(c, etiqueta, getattr(asistencia, c))
                              for c, etiqueta in perf.CAMPOS_ASISTENCIA],
        "campos_ident": [(c, etiqueta, ident[c]) for c, etiqueta in perf.CAMPOS_IDENT],
        "resultado": resultado,
        "cargo": CARGO_INSTRUMENTO,
    })


@login_required
def informe_instrumento(request):
    """Informe imprimible del instrumento oficial.

    No se genera un PDF en el servidor: es la misma decisión que en proyectos y
    en OCT (ver `proyectos/views/exportar.py`). El navegador imprime a PDF sin
    ayuda, y meter una librería de PDF significa arrastrar reportlab, lxml y
    compañía a un despliegue que hoy solo depende de Django y openpyxl.
    """
    if request.method != "POST":
        raise Http404("El informe se genera desde el formulario de evaluación")

    elementos, asistencia, ident = _leer_instrumento(request)
    return render(request, "evaluaciones/informe.html", {
        "resultado": evaluar(elementos, asistencia),
        "cargo": CARGO_INSTRUMENTO,
        "ident": ident,
        "fecha": timezone.localdate().strftime("%d-%m-%Y"),
        "auto_imprimir": request.POST.get("accion") == "informe",
    })


def _agrupar(elementos):
    """Agrupa los elementos por categoría y subtipo para mostrarlos en secciones."""
    titulos = [
        (("funcion", "Principal"), "Funciones principales"),
        (("funcion", "Secundaria"), "Funciones secundarias"),
        (("competencia", "Genérica"), "Competencias genéricas"),
        (("competencia", "Específica"), "Competencias específicas"),
        (("conocimiento", "Obligatorio"), "Conocimientos obligatorios"),
        (("conocimiento", "Deseable"), "Conocimientos deseables"),
    ]
    secciones = []
    for clave, titulo in titulos:
        items = [e for e in elementos if (e.categoria, e.subtipo) == clave]
        if items:
            secciones.append({"titulo": titulo, "items": items})
    return secciones

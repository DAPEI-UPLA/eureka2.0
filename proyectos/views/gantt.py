"""Carta Gantt del proyecto.

Dibuja las actividades sobre una línea de tiempo de meses. Todo el cálculo se
hace acá y la plantilla sólo pinta porcentajes: así el mismo resultado se puede
probar sin navegador, que es lo que costó caro en los formularios de dinero.

Tres decisiones que no son obvias y conviene no revertir sin leer esto:

1. **Sin fecha de inicio no hay barra, hay un hito.** La actividad guarda
   cuándo hay que tenerla lista, no cuánto dura. Estirar la barra desde el
   inicio del proyecto —o darle un ancho fijo— produce una duración que nadie
   declaró pero que se lee como declarada. El rombo dice la verdad: sólo se
   conoce la fecha de término.

2. **El arrastre se dibuja aparte.** `fecha_limite_original` es el compromiso y
   `fecha_limite` es lo que se sostiene hoy. Si sólo se pintara la vigente, una
   actividad corrida tres veces se vería igual de sana que una que nunca se
   movió. El tramo fantasma entre ambas es justamente el atraso.

3. **Lo que no se puede ubicar se informa, no se esconde.** Las actividades sin
   ninguna fecha salen listadas bajo la carta. Si desaparecieran, la carta se
   vería completa estando incompleta.
"""

from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from ..models import Proyecto
from .permisos import es_jefe, usuario_es_responsable

MESES = (
    "", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
)

MESES_LARGOS = (
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


# ---------------------------------------------------------------------------
# Calendario
# ---------------------------------------------------------------------------

def _primer_dia(anio, mes):
    return date(anio, mes, 1)


def _ultimo_dia(anio, mes):
    if mes == 12:
        return date(anio, 12, 31)
    return date(anio, mes + 1, 1) - timedelta(days=1)


def _meses_entre(inicio, fin):
    """[(año, mes), ...] desde el mes de `inicio` hasta el de `fin`, inclusive."""
    anio, mes = inicio.year, inicio.month
    salida = []
    while (anio, mes) <= (fin.year, fin.month):
        salida.append((anio, mes))
        mes += 1
        if mes == 13:
            anio, mes = anio + 1, 1
    return salida


# ---------------------------------------------------------------------------
# Filtros de la URL
# ---------------------------------------------------------------------------

def _entero(valor, minimo=None, maximo=None):
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError, AttributeError):
        return None
    if minimo is not None and numero < minimo:
        return None
    if maximo is not None and numero > maximo:
        return None
    return numero


def _filtros(request, anios_disponibles):
    """Año calendario y rango de meses pedidos, ya saneados.

    Los meses sólo se aplican con un año elegido: un rango «marzo a junio» sobre
    un proyecto de tres años no dice de cuál marzo se habla. Con «todo el
    proyecto» se ignoran en vez de adivinar.
    """
    anio = _entero(request.GET.get("anio"))
    if anio not in anios_disponibles:
        anio = None

    desde = hasta = None
    if anio is not None:
        desde = _entero(request.GET.get("mes_desde"), 1, 12) or 1
        hasta = _entero(request.GET.get("mes_hasta"), 1, 12) or 12
        if desde > hasta:
            desde, hasta = hasta, desde

    return anio, desde, hasta


# ---------------------------------------------------------------------------
# Armado de las filas
# ---------------------------------------------------------------------------

def _fechas_de(actividad):
    return [
        f for f in (
            actividad.fecha_inicio,
            actividad.fecha_limite,
            actividad.fecha_limite_original,
            actividad.fecha_efectiva,
        ) if f
    ]


def _estado(actividad):
    """Cómo se pinta la fila. El rojo se reserva para el atraso real."""
    if actividad.fecha_efectiva:
        return "cerrada"
    if actividad.cumplimiento >= 100:
        return "completada"
    if actividad.atrasada:
        return "atrasada"
    if actividad.cumplimiento > 0:
        return "en_curso"
    return "pendiente"


class _Escala:
    """Convierte fechas en porcentajes dentro de la ventana visible."""

    def __init__(self, inicio, fin):
        self.inicio = inicio
        self.fin = fin
        self.dias = max((fin - inicio).days + 1, 1)

    def pos(self, fecha):
        """0 = borde izquierdo de la ventana, 100 = borde derecho."""
        return round((fecha - self.inicio).days / self.dias * 100, 4)

    def tramo(self, desde, hasta):
        """Recorta un tramo a la ventana. None si queda completamente fuera.

        Devuelve además si se recortó por cada lado, para que la plantilla
        dibuje la flecha de «sigue más allá» y no se lea como si la actividad
        empezara o terminara justo en el borde.
        """
        if hasta < self.inicio or desde > self.fin:
            return None
        izquierda = max(self.pos(desde), 0.0)
        # +1 día: una actividad que empieza y termina el mismo día tiene que
        # verse, no medir cero de ancho.
        derecha = min(self.pos(hasta + timedelta(days=1)), 100.0)
        return {
            "izquierda": izquierda,
            "ancho": max(round(derecha - izquierda, 4), 0.6),
            "recorte_izq": desde < self.inicio,
            "recorte_der": hasta > self.fin,
        }


def _fila(actividad, etiqueta, escala):
    """Una actividad ubicada en la ventana, o None si no cae dentro."""
    fechas = _fechas_de(actividad)
    if not fechas:
        return None

    termino = actividad.fecha_termino_dibujada
    fila = {
        "actividad": actividad,
        "etiqueta": etiqueta,
        "estado": _estado(actividad),
        "avance": float(actividad.cumplimiento),
        "barra": None,
        "hito": None,
        "arrastre": None,
    }

    if actividad.tiene_barra:
        fila["barra"] = escala.tramo(actividad.fecha_inicio, termino)
    elif termino:
        if escala.inicio <= termino <= escala.fin:
            fila["hito"] = escala.pos(termino)

    # El tramo que se corrió la fecha límite. Se dibuja aunque la actividad ya
    # esté cerrada: el atraso ocurrió igual.
    original = actividad.fecha_limite_original
    vigente = actividad.fecha_limite
    if original and vigente and original != vigente:
        desde, hasta = min(original, vigente), max(original, vigente)
        fila["arrastre"] = escala.tramo(desde, hasta)
        fila["arrastre_dias"] = (vigente - original).days

    dentro = fila["barra"] or fila["hito"] is not None or fila["arrastre"]
    return fila if dentro else None


def _orden_cronologico(fila):
    """Por cuándo arranca lo dibujado. Las sin barra se ordenan por su hito."""
    actividad = fila["actividad"]
    ancla = actividad.fecha_inicio or actividad.fecha_termino_dibujada
    return (ancla or date.max, actividad.orden, actividad.pk)


# ---------------------------------------------------------------------------
# Vista
# ---------------------------------------------------------------------------

@login_required
def gantt_proyecto(request, pk):
    proyecto = get_object_or_404(
        Proyecto.objects.prefetch_related("objetivos__resultados__actividades"),
        pk=pk,
    )

    # Etiqueta OE1.R2.A3, calculada por posición: los objetivos y resultados no
    # guardan número propio, sólo `orden`, y ese orden es el que se ve en el
    # detalle. Así la fila de la carta se puede buscar allá.
    actividades, sin_fecha = [], []
    for i, objetivo in enumerate(proyecto.objetivos.all(), start=1):
        for j, resultado in enumerate(objetivo.resultados.all(), start=1):
            for k, actividad in enumerate(resultado.actividades.all(), start=1):
                etiqueta = f"OE{i}.R{j}.A{k}"
                if _fechas_de(actividad):
                    actividades.append((actividad, etiqueta, resultado))
                else:
                    sin_fecha.append((actividad, etiqueta, resultado))

    todas_las_fechas = [f for a, _, _ in actividades for f in _fechas_de(a)]
    # El rango completo de años, no sólo aquellos en los que cae alguna fecha.
    # Una actividad que va de noviembre de 2025 a febrero de 2027 pasa por 2026
    # entero, y si 2026 no fuera ofrecible el filtro se saltaría justo el año
    # que esa actividad ocupa por completo.
    anios_disponibles = (
        list(range(min(todas_las_fechas).year, max(todas_las_fechas).year + 1))
        if todas_las_fechas else []
    )
    anio_sel, mes_desde, mes_hasta = _filtros(request, anios_disponibles)

    contexto = {
        "proyecto": proyecto,
        "es_encargado": usuario_es_responsable(request.user, proyecto),
        "es_jefe": es_jefe(request.user),
        "anios": anios_disponibles,
        "anio_sel": anio_sel,
        "mes_desde": mes_desde,
        "mes_hasta": mes_hasta,
        "meses_opciones": [(n, MESES_LARGOS[n].capitalize()) for n in range(1, 13)],
        "sin_fecha": sin_fecha,
        "total_actividades": len(actividades) + len(sin_fecha),
    }

    if not todas_las_fechas:
        contexto.update({"filas": [], "meses": [], "anios_cabecera": [], "vacia": True})
        return render(request, "proyectos/gantt_proyecto.html", contexto)

    if anio_sel is not None:
        ventana_ini = _primer_dia(anio_sel, mes_desde)
        ventana_fin = _ultimo_dia(anio_sel, mes_hasta)
    else:
        # Todo el proyecto: los meses completos que tocan las actividades. Las
        # fechas del proyecto no se usan para estirar la ventana porque un
        # proyecto de 36 meses con actividades sólo en el primero dejaría dos
        # tercios de carta en blanco.
        primera, ultima = min(todas_las_fechas), max(todas_las_fechas)
        ventana_ini = _primer_dia(primera.year, primera.month)
        ventana_fin = _ultimo_dia(ultima.year, ultima.month)

    escala = _Escala(ventana_ini, ventana_fin)

    filas = []
    for actividad, etiqueta, resultado in actividades:
        fila = _fila(actividad, etiqueta, escala)
        if fila:
            fila["resultado"] = resultado
            filas.append(fila)
    filas.sort(key=_orden_cronologico)

    # Cabecera de meses. El ancho de cada columna es proporcional a sus días
    # dentro de la ventana, no 1/n: con anchos iguales, febrero y marzo medirían
    # lo mismo y las barras dejarían de coincidir con la grilla.
    meses, anios_cabecera = [], []
    for anio, mes in _meses_entre(ventana_ini, ventana_fin):
        desde = max(_primer_dia(anio, mes), ventana_ini)
        hasta = min(_ultimo_dia(anio, mes), ventana_fin)
        ancho = round(((hasta - desde).days + 1) / escala.dias * 100, 4)
        meses.append({
            "anio": anio,
            "mes": mes,
            "nombre": MESES[mes],
            "ancho": ancho,
            "inicio_de_anio": mes == 1 or not meses,
        })
        if anios_cabecera and anios_cabecera[-1]["anio"] == anio:
            anios_cabecera[-1]["ancho"] = round(anios_cabecera[-1]["ancho"] + ancho, 4)
        else:
            anios_cabecera.append({"anio": anio, "ancho": ancho})

    hoy = date.today()
    contexto.update({
        "filas": filas,
        "meses": meses,
        # Ancho mínimo de la pista, para que la carta se desplace en vez de
        # comprimirse. Sin esto, un proyecto de 36 meses entra igual en la
        # pantalla con columnas de 30px: se ve completo y no se lee nada.
        "ancho_minimo": len(meses) * 58,
        "anios_cabecera": anios_cabecera,
        "ventana_ini": ventana_ini,
        "ventana_fin": ventana_fin,
        "hoy": escala.pos(hoy) if ventana_ini <= hoy <= ventana_fin else None,
        "fuera_de_ventana": len(actividades) - len(filas),
        "vacia": False,
    })
    return render(request, "proyectos/gantt_proyecto.html", contexto)

import json
from decimal import Decimal

from ..numeros import a_decimal


def _to_decimal(value, default=Decimal("0")):
    return a_decimal(value, default)


# ---------------------------------------------------------------------------
# Eventos HTMX
# ---------------------------------------------------------------------------
# Toda mutación de la estructura del proyecto (objetivos, resultados,
# actividades, presupuesto) publica eventos en `HX-Trigger`. El detalle del
# proyecto los escucha para refrescar sólo lo que cambió, de modo que nunca
# haga falta apretar F5.
#
#   estructuraActualizada  -> dashboard, gráficos y planes de gasto
#   resultadoActualizado   -> fila del resultado y cabecera de su objetivo
#   actividadActualizada   -> tabla de actividades, fila del resultado y cabecera
#   guardado               -> aviso flotante "Guardado" en pantalla

def disparar(response, *, guardado=None, **eventos):
    """Añade eventos HX-Trigger a la respuesta, conservando los ya presentes."""
    actuales = {}
    if response.has_header("HX-Trigger"):
        try:
            actuales = json.loads(response["HX-Trigger"])
        except (ValueError, TypeError):
            actuales = {}
    actuales.update(eventos)
    if guardado:
        actuales["guardado"] = {"mensaje": guardado}
    response["HX-Trigger"] = json.dumps(actuales)
    return response


def detalle_resultado(resultado):
    """Payload común de los eventos que afectan a un resultado."""
    return {"resultado_id": resultado.pk, "objetivo_id": resultado.objetivo_id}


# ---------------------------------------------------------------------------
# Año en pantalla
# ---------------------------------------------------------------------------
# El detalle del proyecto se puede mirar completo o año por año. Lo que filtra
# el año es el **dinero** —presupuesto, planes de gasto y gastos—, nunca la
# estructura: los objetivos, resultados y actividades son los mismos todos los
# años, y esconder unos u otros daría a entender que el proyecto cambia de
# forma según el año, que no es lo que pasa.

def anio_seleccionado(request, proyecto):
    """El `PresupuestoAnual` que se está mirando, o None para «todo el proyecto».

    Se recibe el año calendario (`?anio=2027`) y no el número de año, porque es
    lo que ya viaja en el resto de la app: `PlanDeGasto.anio` y el filtro de
    gastos hablan en calendario. Un año que no existe en el proyecto se trata
    como si no se hubiera pedido nada, en vez de dejar la pantalla vacía.
    """
    crudo = request.GET.get("anio")
    if not crudo:
        return None
    try:
        calendario = int(str(crudo).strip())
    except (TypeError, ValueError):
        return None
    return proyecto.presupuesto_del_calendario(calendario)

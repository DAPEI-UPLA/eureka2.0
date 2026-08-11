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

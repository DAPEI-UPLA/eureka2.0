"""Valor ganado (EVM) de un proyecto.

Responde tres preguntas que por separado ya se podían mirar, pero que sólo
juntas dicen algo:

    ¿Cuánto trabajo debería llevar hecho a esta fecha?   -> PV, valor planificado
    ¿Cuánto llevo hecho de verdad?                        -> EV, valor ganado
    ¿Cuánto me costó llevarlo?                            -> AC, costo real

De ahí salen los dos índices:

    SPI = EV / PV   ¿voy a tiempo?      1,00 = al día
    CPI = EV / AC   ¿voy en precio?     1,00 = en presupuesto

La gracia es que se leen igual: por debajo de 1 hay problema, y el número dice
cuánto. SPI 0,80 significa que por cada peso de trabajo que debería estar hecho
sólo hay 80 centavos. Un avance del 40% con un 70% del plazo consumido y el 90%
de la plata gastada son tres cifras que hay que cruzar a mano; SPI y CPI ya las
cruzaron.

De dónde sale cada número en ESTE sistema
-----------------------------------------

**BAC** — el presupuesto repartido en objetivos, no el total del proyecto. La
plata que todavía no se reparte no tiene trabajo asociado, así que no puede
ganarse: metiéndola en la base, el proyecto arrastraría un déficit permanente
que no habla ni de plazo ni de costo. Lo que falta por repartir se informa
aparte, que es donde sí significa algo.

**EV** — de abajo hacia arriba: cada resultado gana su propio presupuesto en
proporción a su avance. No se usa el avance global del proyecto multiplicado
por el BAC porque el avance global ya viene ponderado por presupuesto y
volvería a ponderar dos veces.

**PV** — repartido en el tiempo con el presupuesto anual de cada resultado, que
es la única línea base con fechas que tiene el sistema. Los años cerrados
cuentan completos y el año en curso cuenta la fracción transcurrida. Un
proyecto sin reparto anual cae a una regla más gruesa —la fracción del plazo
total consumida— y se dice cuál se usó, porque la segunda es mucho más
discutible que la primera.

**AC** — todo lo que el proyecto ya consumió: pagado más comprometido. Dejar
fuera lo comprometido haría aparecer un CPI excelente el día antes de pagar la
factura, y hundirse al día siguiente sin que hubiera pasado nada.

Nada de esto escribe en la base. Es lectura y aritmética.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

CERO = Decimal("0")
UNO = Decimal("1")

# Umbrales del semáforo.
#
# 0,95 y 0,85 no son un estándar universal: son la convención más difundida en
# gestión de proyectos y sirven de punto de partida. Si el equipo decide que en
# proyectos públicos chilenos el amarillo debe partir antes, se cambian acá y
# cambia en todas las pantallas.
UMBRAL_ATENCION = Decimal("0.95")
UMBRAL_CRITICO = Decimal("0.85")

BIEN, ATENCION, CRITICO, SIN_DATO = "bien", "atencion", "critico", "sin_dato"

# Nivel de aviso que NO es un juicio sobre el proyecto sino sobre sus datos.
# Va aparte del semáforo: pintar de rojo a un equipo por no haber cargado
# todavía su avance quema la alerta antes de que sirva para algo.
DATOS = "datos"


def _semaforo(indice):
    if indice is None:
        return SIN_DATO
    if indice < UMBRAL_CRITICO:
        return CRITICO
    if indice < UMBRAL_ATENCION:
        return ATENCION
    return BIEN


def _indice(numerador, denominador):
    """Un cociente, o None cuando el denominador es cero.

    Devolver 0 o 1 en ese caso sería inventar una lectura: un proyecto que aún
    no gasta nada no tiene CPI infinito ni perfecto, simplemente no tiene CPI
    todavía. La pantalla lo dice con «—» en vez de con un número falso.
    """
    if not denominador:
        return None
    return (Decimal(numerador) / Decimal(denominador)).quantize(Decimal("0.001"))


def _pesos(valor):
    return Decimal(valor or 0).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# El tiempo
# ---------------------------------------------------------------------------

def fraccion_transcurrida_del_anio(anio, hoy):
    """Cuánto se lleva consumido del año calendario `anio` al día `hoy`."""
    if anio < hoy.year:
        return UNO
    if anio > hoy.year:
        return CERO
    dias_del_anio = (date(anio, 12, 31) - date(anio, 1, 1)).days + 1
    transcurridos = (hoy - date(anio, 1, 1)).days + 1
    return Decimal(transcurridos) / Decimal(dias_del_anio)


def _ventana_del_respaldo(proyecto):
    """(inicio, fin, origen) del tramo contra el que se mide sin reparto anual.

    Manda el **Año 1 declarado**: va del 1 de enero de ese año al 31 de
    diciembre del último. Un proyecto que llega en octubre y declara que
    ejecuta desde enero siguiente no debe acumular valor planificado en esos
    dos meses y medio; contando desde `fecha_inicio` arrancaba con el SPI ya
    castigado por un tramo que nadie se comprometió a ejecutar.

    Las fechas quedan de segundo respaldo, para los proyectos que todavía no
    declaran su Año 1.
    """
    anios = proyecto.anios_calendario_esperados
    if anios:
        return date(anios[0], 1, 1), date(anios[-1], 12, 31), "anios_declarados"

    inicio, fin = proyecto.fecha_inicio, proyecto.fecha_fin
    if inicio and fin and fin >= inicio:
        return inicio, fin, "plazo_total"
    return None, None, "sin_base"


def _fraccion_transcurrida(inicio, fin, hoy):
    """Cuánto va corrido del tramo, entre 0 y 1."""
    if hoy <= inicio:
        return CERO
    if hoy >= fin:
        return UNO
    total = Decimal((fin - inicio).days + 1)
    corrido = Decimal((hoy - inicio).days + 1)
    return corrido / total


# ---------------------------------------------------------------------------
# Los tres montos
# ---------------------------------------------------------------------------

def _resultados_vivos(proyecto):
    """Los resultados que cuentan, respetando el prefetch de quien llame.

    Se usa `.all()` y no `.filter(eliminado=False)` a propósito: el manager por
    defecto de objetivos y resultados ya descarta los eliminados, y un `filter`
    encima descartaría el prefetch y volvería a consultar la base una vez por
    proyecto. En la lista de proyectos eso son doce consultas extra por página.
    """
    return [
        resultado
        for objetivo in proyecto.objetivos.all()
        for resultado in objetivo.resultados.all()
    ]


def _conteo_de_avance(resultados):
    """(actividades, resultados con avance > 0).

    El avance se cuenta a nivel de RESULTADO y no de actividad porque cada
    resultado puede medirse de tres formas distintas. Contando actividades, un
    proyecto que mide todo por metas contables aparecía como «nadie ha cargado
    avance» aunque tuviera sus metas al día: no tiene actividades que contar.

    Las actividades se siguen contando aparte, sólo para poder decir cuántas
    están en cero cuando ése es el método que se usa.
    """
    actividades = con_avance = 0
    for resultado in resultados:
        actividades += len(resultado.actividades.all())
        if resultado.cumplimiento and resultado.cumplimiento > 0:
            con_avance += 1
    return actividades, con_avance


def _valor_ganado(resultados):
    """Cada resultado gana su presupuesto en proporción a lo que lleva hecho."""
    return sum(
        (
            (r.presupuesto_asignado or CERO) * (r.cumplimiento or CERO) / Decimal("100")
            for r in resultados
        ),
        CERO,
    )


def _valor_planificado(proyecto, resultados, bac, hoy):
    """(PV, origen). El origen dice con qué regla se calculó.

    Se prefiere el reparto anual de los resultados porque es una línea base
    declarada por el equipo. La regla del plazo total es un sustituto: supone
    que el gasto es parejo mes a mes, cosa que en estos proyectos casi nunca
    ocurre, así que conviene que la pantalla admita que la está usando.
    """
    # `.all()` y no `.select_related("anio")`: agregar select_related construye
    # un queryset nuevo y descarta el prefetch de quien llamó, con lo que el
    # reparto anual se consultaba una vez POR RESULTADO. Quien necesite el año
    # sin pagar una consulta extra lo pide en su propio `prefetch_related`,
    # como hacen la lista y el panel.
    asignaciones = [
        asignacion
        for r in resultados
        for asignacion in r.presupuestos_anuales.all()
    ]

    if asignaciones:
        planificado = sum(
            (
                asignacion.presupuesto_total
                * fraccion_transcurrida_del_anio(asignacion.anio.anio_calendario, hoy)
                for asignacion in asignaciones
            ),
            CERO,
        )
        return planificado, "reparto_anual"

    inicio, fin, origen = _ventana_del_respaldo(proyecto)
    if inicio is None:
        return None, origen
    return bac * _fraccion_transcurrida(inicio, fin, hoy), origen


# ---------------------------------------------------------------------------
# El resultado
# ---------------------------------------------------------------------------

@dataclass
class ValorGanado:
    """Los indicadores de un proyecto en una fecha. Sólo lectura."""

    hoy: date

    bac: Decimal = CERO          # presupuesto de la línea base
    pv: Decimal = None           # lo que debería llevar hecho
    ev: Decimal = CERO           # lo que lleva hecho
    ac: Decimal = CERO           # lo que le costó

    spi: Decimal = None
    cpi: Decimal = None
    eac: Decimal = None          # costo final estimado al ritmo actual
    vac: Decimal = None          # cuánto sobra o falta al final

    origen_pv: str = "sin_base"
    sin_repartir: Decimal = CERO  # presupuesto del proyecto aún sin objetivo
    actividades: int = 0
    resultados_con_avance: int = 0
    alertas: list = field(default_factory=list)

    @property
    def avance_cargado(self):
        """¿Alguien tocó siquiera una actividad?

        Mientras no, el EV es cero por falta de dato y no por atraso, y el SPI
        que sale de ahí no dice nada sobre el proyecto.
        """
        return self.resultados_con_avance > 0

    @property
    def sv(self):
        """Adelanto (+) o atraso (−) en pesos de trabajo."""
        return None if self.pv is None else self.ev - self.pv

    @property
    def cv(self):
        """Ahorro (+) o sobrecosto (−) en pesos."""
        return self.ev - self.ac

    @property
    def estado_spi(self):
        # Sin avance cargado el SPI da cero por construcción: el EV no puede
        # ser otra cosa. Pintarlo de rojo sería culpar al proyecto de un dato
        # que nadie ingresó.
        if not self.avance_cargado:
            return SIN_DATO
        return _semaforo(self.spi)

    @property
    def estado_cpi(self):
        return _semaforo(self.cpi)

    @property
    def hay_alerta(self):
        return any(a["nivel"] == CRITICO for a in self.alertas)

    @property
    def hay_aviso(self):
        return bool(self.alertas)

    @property
    def estado(self):
        """El peor de los dos semáforos: es el que manda en la tarjeta."""
        for nivel in (CRITICO, ATENCION):
            if nivel in (self.estado_spi, self.estado_cpi):
                return nivel
        if self.estado_spi == self.estado_cpi == SIN_DATO:
            return SIN_DATO
        return BIEN

    @property
    def medible(self):
        """Si no hay línea base ni gasto, no hay nada que informar."""
        return self.spi is not None or self.cpi is not None


def _alertas(v):
    """Los avisos, en castellano y con el monto, no sólo el índice.

    Un «SPI 0,78» no mueve a nadie; «va atrasado en $47.000.000 de trabajo» sí.
    """
    avisos = []

    if v.spi is not None and not v.avance_cargado:
        # No es una alerta de plazo sino de datos, y por eso va en otro nivel:
        # decirle a un equipo que va atrasado cuando lo que pasa es que no ha
        # cargado su avance es una acusación falsa, y la primera hace dudar de
        # todas las siguientes.
        if v.actividades:
            detalle = (
                f"Ningún resultado registra avance y las {v.actividades} "
                f"actividades del proyecto están en 0%. Mientras no se cargue "
                f"el avance no se puede saber si va a tiempo: el indicador da "
                f"cero por falta de dato, no por atraso."
            )
        else:
            detalle = (
                "Ningún resultado registra avance. Defínele a cada uno cómo se "
                "mide —una meta contable o un tramo de la escala— y carga lo "
                "que lleva hecho."
            )
        avisos.append({
            "nivel": DATOS,
            "indice": "Avance",
            "titulo": "Nadie ha cargado avance todavía",
            "detalle": detalle,
        })

    elif v.spi is not None and v.spi < UMBRAL_ATENCION:
        avisos.append({
            "nivel": _semaforo(v.spi),
            "indice": "SPI",
            "titulo": "Avance por debajo de lo planificado",
            "detalle": (
                f"A esta fecha debería llevar ${_miles(v.pv)} de trabajo hecho y "
                f"lleva ${_miles(v.ev)}: faltan ${_miles(abs(v.sv))}."
            ),
        })

    if v.cpi is not None and v.cpi < UMBRAL_ATENCION:
        avisos.append({
            "nivel": _semaforo(v.cpi),
            "indice": "CPI",
            "titulo": "Está costando más de lo presupuestado",
            "detalle": (
                f"Lleva gastados ${_miles(v.ac)} para producir ${_miles(v.ev)} "
                f"de trabajo: ${_miles(abs(v.cv))} por sobre lo previsto."
            ),
        })

    if v.vac is not None and v.vac < 0:
        avisos.append({
            "nivel": CRITICO if v.cpi is not None and v.cpi < UMBRAL_CRITICO else ATENCION,
            "indice": "EAC",
            "titulo": "Al ritmo actual, el presupuesto no alcanza",
            "detalle": (
                f"Terminar costaría ${_miles(v.eac)} contra un presupuesto de "
                f"${_miles(v.bac)}: faltarían ${_miles(abs(v.vac))}."
            ),
        })

    return avisos


def _miles(valor):
    return f"{_pesos(valor):,.0f}".replace(",", ".")


def calcular(proyecto, hoy=None):
    """Los indicadores de valor ganado del proyecto completo.

    Va sobre todo el proyecto y no sobre el año en pantalla a propósito: el
    valor ganado mide cómo va el proyecto contra su compromiso total, y un SPI
    del año 2 aislado no dice si el proyecto llega o no llega. El selector de
    año sigue filtrando la plata; esto no.
    """
    hoy = hoy or date.today()
    resultados = _resultados_vivos(proyecto)

    bac = _pesos(proyecto.presupuesto_asignado)
    ev = _pesos(_valor_ganado(resultados))
    ac = _pesos(proyecto.gastos_total)
    pv, origen = _valor_planificado(proyecto, resultados, bac, hoy)

    actividades, con_avance = _conteo_de_avance(resultados)
    v = ValorGanado(
        hoy=hoy,
        bac=bac,
        actividades=actividades,
        resultados_con_avance=con_avance,
        pv=None if pv is None else _pesos(pv),
        ev=ev,
        ac=ac,
        origen_pv=origen,
        sin_repartir=_pesos((proyecto.presupuesto_total or CERO) - bac),
    )
    v.spi = _indice(v.ev, v.pv)
    v.cpi = _indice(v.ev, v.ac)

    # EAC = BAC / CPI: si hasta acá cada peso rindió lo que rindió, terminar
    # cuesta lo que falta al mismo rendimiento. Es la estimación estándar y la
    # más pesimista de las razonables; sirve para alertar, no para presupuestar.
    if v.cpi:
        v.eac = _pesos(v.bac / v.cpi)
        v.vac = v.bac - v.eac

    v.alertas = _alertas(v)
    return v

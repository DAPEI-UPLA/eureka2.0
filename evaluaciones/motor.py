# -*- coding: utf-8 -*-
"""Motor de cálculo de la Evaluación de Desempeño UPLA.

Reproduce la lógica de "Instrumento_T2_automatico.xlsx" desacoplada de Excel:
recibe el perfil del cargo (niveles requeridos + pesos) y los niveles OBSERVADOS
por el evaluador, y devuelve todas las notas más el plan de desarrollo.

Todo lo que en el Excel estaba incrustado en fórmulas vive en `Config`, así que
cambiar un peso o un umbral no obliga a tocar el cálculo. La verificación contra
los valores exactos del Excel está en `tests.py`; era un bloque `__main__` que
había que acordarse de correr a mano.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

Categoria = Literal["funcion", "competencia", "conocimiento"]
FactorUPLA = Literal["1A", "1B", "2A", "2B", "3A", "3B"]

# Cómo se escribe cada categoría cuando la lee una persona. El literal interno
# ("funcion") es identificador, no rótulo: sin esto sale sin tilde en el informe.
CATEGORIAS = {
    "funcion": "Función",
    "competencia": "Competencia",
    "conocimiento": "Conocimiento",
}

# Descripción oficial de cada factor de la pauta UPLA (sale en el informe).
FACTORES = {
    "1A": "Cumplimiento de la labor realizada",
    "1B": "Calidad de la labor realizada",
    "2A": "Interés por el trabajo que realiza",
    "2B": "Capacidad para trabajos en equipo",
    "3A": "Cumplimiento de normas e instrucciones",
    "3B": "Asistencia y puntualidad",
}


@dataclass(frozen=True)
class Config:
    # Pesos de los 4 componentes de la nota final
    peso_funciones: float = 0.50
    peso_competencias: float = 0.30
    peso_conocimientos: float = 0.15
    peso_asistencia: float = 0.05

    # Escala nota por ítem: nota = max(nota_minima, 10 - puntos_por_brecha * brecha)
    nota_minima_item: float = 2.0
    puntos_por_brecha: float = 2.0

    # Penalizaciones de asistencia (por cada evento)
    penalizacion_atraso: float = 0.005
    penalizacion_salida: float = 0.005

    # Escala de la nota 3B (asistencia): lista de (umbral_incumplimiento, nota).
    # Se asigna la nota del primer umbral que el incumplimiento NO supera.
    escala_asistencia: tuple = (
        (0.03, 10), (0.05, 8), (0.07, 6), (0.10, 4),
    )
    nota_asistencia_peor: float = 2.0

    # Interpretación de la nota final: (nota_minima, etiqueta), de mayor a menor
    escala_interpretacion: tuple = (
        (9.0, "Sobresaliente"), (8.0, "Muy Bueno"), (7.0, "Bueno"),
        (6.0, "Aceptable"), (5.0, "Requiere mejora"),
    )
    interpretacion_peor: str = "Crítico"


@dataclass
class Elemento:
    """Un ítem evaluable del perfil (función, competencia o conocimiento)."""
    id: str
    categoria: Categoria
    subtipo: str                # Principal/Secundaria, Genérica/Específica, Obligatorio/Deseable
    nombre: str
    factor_upla: FactorUPLA
    peso: float
    nivel_requerido: int        # 0-4
    nivel_observado: int | None = None  # 0-4, lo ingresa el evaluador

    @property
    def brecha(self) -> int:
        return max(self.nivel_requerido - (self.nivel_observado or 0), 0)

    def nota(self, cfg: Config) -> float:
        return max(cfg.nota_minima_item, 10 - cfg.puntos_por_brecha * self.brecha)


@dataclass
class DatosAsistencia:
    dias_habiles: int
    dias_asistidos: int
    atrasos: int = 0
    salidas_anticipadas: int = 0
    inasistencias_justificadas: int = 0
    inasistencias_injustificadas: int = 0


def _promedio_ponderado(pares: list[tuple[float, float]]) -> float | None:
    """pares = [(nota, peso), ...] -> promedio ponderado, o None si no hay pesos."""
    total_peso = sum(p for _, p in pares)
    if total_peso == 0:
        return None
    return sum(n * p for n, p in pares) / total_peso


def nota_componente(elementos: list[Elemento], categoria: Categoria, cfg: Config):
    pares = [(e.nota(cfg), e.peso) for e in elementos if e.categoria == categoria]
    return _promedio_ponderado(pares)


def nota_factor(elementos: list[Elemento], factor: FactorUPLA, cfg: Config):
    """Nota de un factor UPLA, agregando funciones + competencias + conocimientos."""
    pares = [(e.nota(cfg), e.peso) for e in elementos if e.factor_upla == factor]
    return _promedio_ponderado(pares)


def evaluar_asistencia(a: DatosAsistencia, cfg: Config) -> dict:
    # Réplica fiel del Excel: el "total inasistencias" considera SOLO las
    # injustificadas. Las justificadas se registran pero no penalizan.
    total_inasistencias = a.inasistencias_injustificadas
    pct_inasistencia = total_inasistencias / a.dias_habiles if a.dias_habiles else 0.0
    pen_atrasos = a.atrasos * cfg.penalizacion_atraso
    pen_salidas = a.salidas_anticipadas * cfg.penalizacion_salida
    pct_incumplimiento = pct_inasistencia + pen_atrasos + pen_salidas

    nota = cfg.nota_asistencia_peor
    for umbral, n in cfg.escala_asistencia:
        if pct_incumplimiento <= umbral:
            nota = n
            break

    # Control de consistencia (mismo criterio del Excel)
    dias_no_asistidos = max(a.dias_habiles - a.dias_asistidos, 0)
    consistente = (dias_no_asistidos == total_inasistencias)

    return {
        "pct_incumplimiento": pct_incumplimiento,
        "nota": float(nota),
        "dias_no_asistidos": dias_no_asistidos,
        "consistente": consistente,
        "alerta": "OK" if consistente else "REVISAR DATOS",
    }


def interpretar(nota_final: float, cfg: Config) -> str:
    for minimo, etiqueta in cfg.escala_interpretacion:
        if nota_final >= minimo:
            return etiqueta
    return cfg.interpretacion_peor


@dataclass
class ResultadoEvaluacion:
    nota_funciones: float
    nota_competencias: float
    nota_conocimientos: float
    nota_asistencia: float
    nota_final: float
    interpretacion: str
    notas_por_factor: dict
    asistencia: dict
    brechas_prioritarias: list  # alimenta el Plan de Desarrollo


def evaluar(elementos: list[Elemento], asistencia: DatosAsistencia,
            cfg: Config = Config()) -> ResultadoEvaluacion:
    nf = nota_componente(elementos, "funcion", cfg)
    nc = nota_componente(elementos, "competencia", cfg)
    nk = nota_componente(elementos, "conocimiento", cfg)
    asis = evaluar_asistencia(asistencia, cfg)
    na = asis["nota"]

    nota_final = (nf * cfg.peso_funciones + nc * cfg.peso_competencias +
                  nk * cfg.peso_conocimientos + na * cfg.peso_asistencia)

    factores = {f: nota_factor(elementos, f, cfg) for f in ("1A", "1B", "2A", "2B", "3A")}
    factores["3B"] = na  # la asistencia ES el factor 3B

    # Plan de desarrollo automático: todo ítem con brecha >= 1, mayor brecha primero
    brechas = sorted(
        [{"id": e.id, "categoria": CATEGORIAS.get(e.categoria, e.categoria),
          "nombre": e.nombre,
          "factor": e.factor_upla, "descripcion_factor": FACTORES.get(e.factor_upla, ""),
          "brecha": e.brecha, "requerido": e.nivel_requerido,
          "observado": e.nivel_observado}
         for e in elementos if e.brecha >= 1],
        key=lambda d: d["brecha"], reverse=True)

    return ResultadoEvaluacion(
        nota_funciones=nf, nota_competencias=nc, nota_conocimientos=nk,
        nota_asistencia=na, nota_final=nota_final,
        interpretacion=interpretar(nota_final, cfg),
        notas_por_factor=factores, asistencia=asis,
        brechas_prioritarias=brechas,
    )


def evaluar_generico(secciones, requeridos, observados, cfg: Config = Config()) -> dict:
    """Evalúa un cargo sin instrumento oficial, con promedio simple.

    Los ítems de estos cargos se sacan del texto del perfil (ver `perfiles.py`),
    así que no traen peso ni factor UPLA. Sin esos dos datos no hay forma de
    reproducir la ponderación 50/30/15/5 del instrumento oficial, y tampoco de
    calcular la asistencia. Se promedia parejo y la pantalla lo dice: una nota
    que se parece a la oficial sin serlo termina citada como si lo fuera.
    """
    detalle, todas, brechas = [], [], []
    for seccion in secciones:
        notas = []
        for i, texto in enumerate(seccion["items"]):
            clave = f"{seccion['id']}-{i}"
            brecha = max(requeridos[clave] - observados[clave], 0)
            nota = max(cfg.nota_minima_item, 10 - cfg.puntos_por_brecha * brecha)
            notas.append(nota)
            todas.append(nota)
            if brecha >= 1:
                brechas.append({"texto": texto, "seccion": seccion["titulo"],
                                "brecha": brecha, "req": requeridos[clave],
                                "obs": observados[clave]})
        detalle.append({"titulo": seccion["titulo"],
                        "promedio": sum(notas) / len(notas) if notas else None,
                        "n": len(notas)})

    final = sum(todas) / len(todas) if todas else 0
    brechas.sort(key=lambda b: b["brecha"], reverse=True)
    return {"secciones": detalle, "final": final,
            "interpretacion": interpretar(final, cfg), "brechas": brechas,
            "n_items": len(todas)}


# ---------------------------------------------------------------------------
# Perfil del cargo T2 de Tesorería, tal como viene del Excel oficial.
#
# Es el único cargo con instrumento completo (pesos y niveles requeridos
# validados). El resto de los cargos se evalúa con el instrumento genérico que
# arma `perfiles.py` a partir del texto del perfil.
# ---------------------------------------------------------------------------

P8, P125 = 8.0, 1.25                       # pesos funciones (principal / secundaria)
PG = float(Fraction(9, 8))                 # 1.125          competencia genérica
PE = float(Fraction(21, 11))               # 1.9090909...   competencia específica
KO, KD = 1.5, 0.75                         # conocimiento obligatorio / deseable


def perfil_t2() -> list[Elemento]:
    f = lambda i, sub, nom, fac, peso, req, obs: Elemento(
        i, "funcion", sub, nom, fac, peso, req, obs)
    c = lambda i, sub, nom, fac, peso, req, obs: Elemento(
        i, "competencia", sub, nom, fac, peso, req, obs)
    k = lambda i, sub, nom, fac, peso, req, obs: Elemento(
        i, "conocimiento", sub, nom, fac, peso, req, obs)

    return [
        # Funciones principales (peso 8)
        f("FP01", "Principal", "Ejecutar pagos institucionales", "1A", P8, 4, 3),
        f("FP02", "Principal", "Verificar documentación de respaldo", "1B", P8, 4, 4),
        f("FP03", "Principal", "Registrar y respaldar operaciones", "1B", P8, 4, 2),
        f("FP04", "Principal", "Aplicar controles internos", "3A", P8, 4, 2),
        f("FP05", "Principal", "Detectar e informar inconsistencias", "1B", P8, 3, 1),
        # Funciones secundarias (peso 1.25)
        f("FS01", "Secundaria", "Mantener archivo de respaldos", "1A", P125, 3, 2),
        f("FS02", "Secundaria", "Apoyar revisión de antecedentes", "1B", P125, 3, 2),
        f("FS03", "Secundaria", "Preparar reportes básicos de pagos", "1B", P125, 2, 1),
        f("FS04", "Secundaria", "Actualizar planillas/registros", "1A", P125, 3, 3),
        f("FS05", "Secundaria", "Apoyar coordinación con unidades", "2B", P125, 2, 1),
        f("FS06", "Secundaria", "Participar en mejora continua", "2A", P125, 2, 1),
        f("FS07", "Secundaria", "Apoyar cierre mensual/conciliación", "1A", P125, 3, 2),
        # Competencias genéricas (peso 1.125)
        c("CG01", "Genérica", "Probidad y Transparencia", "3A", PG, 4, 4),
        c("CG02", "Genérica", "Compromiso con la Institución", "2A", PG, 3, 3),
        c("CG03", "Genérica", "Trabajo en Equipo", "2B", PG, 3, 3),
        c("CG04", "Genérica", "Comunicación Efectiva", "2B", PG, 3, 3),
        c("CG05", "Genérica", "Adaptación al Cambio", "2A", PG, 2, 2),
        c("CG06", "Genérica", "Orientación al Usuario Interno", "2A", PG, 3, 3),
        c("CG07", "Genérica", "Uso de Tecnologías de Información", "1A", PG, 3, 3),
        c("CG08", "Genérica", "Inclusión y Respeto por la Diversidad", "3A", PG, 3, 3),
        # Competencias específicas (peso 21/11)
        c("CE01", "Específica", "Atención al detalle", "1B", PE, 4, 4),
        c("CE02", "Específica", "Organización y control documental", "1B", PE, 4, 4),
        c("CE03", "Específica", "Cumplimiento normativo", "3A", PE, 4, 3),
        c("CE04", "Específica", "Control y rigurosidad operativa", "1A", PE, 4, 3),
        c("CE05", "Específica", "Confidencialidad de información sensible", "3A", PE, 4, 3),
        c("CE06", "Específica", "Capacidad analítica", "1B", PE, 3, 3),
        c("CE07", "Específica", "Gestión del tiempo", "1A", PE, 3, 3),
        c("CE08", "Específica", "Resolución de problemas", "2A", PE, 3, 2),
        c("CE09", "Específica", "Mejora continua", "2A", PE, 2, 2),
        c("CE10", "Específica", "Comunicación escrita técnica", "1B", PE, 2, 1),
        c("CE11", "Específica", "Herramientas de análisis de datos", "1B", PE, 2, 1),
        # Conocimientos obligatorios (peso 1.5)
        k("CO01", "Obligatorio", "Normativa financiera y administrativa", "3A", KO, 4, 3),
        k("CO02", "Obligatorio", "Procedimientos institucionales de pago", "3A", KO, 4, 3),
        k("CO03", "Obligatorio", "ERP y sistemas de información financiera", "1A", KO, 4, 3),
        k("CO04", "Obligatorio", "Control documental y trazabilidad", "1B", KO, 4, 3),
        k("CO05", "Obligatorio", "Estatuto Administrativo", "3A", KO, 3, 3),
        k("CO06", "Obligatorio", "Probidad", "3A", KO, 3, 3),
        k("CO07", "Obligatorio", "Ley Karin", "3A", KO, 2, 1),
        k("CO08", "Obligatorio", "Inclusión y no discriminación", "3A", KO, 2, 1),
        # Conocimientos deseables (peso 0.75)
        k("CD01", "Deseable", "Compras públicas", "3A", KD, 2, 2),
        k("CD02", "Deseable", "Gestión presupuestaria", "1B", KD, 2, 2),
        k("CD03", "Deseable", "Gestión documental electrónica", "1B", KD, 2, 2),
        k("CD04", "Deseable", "Control interno y auditoría", "3A", KD, 2, 2),
    ]


def asistencia_t2() -> DatosAsistencia:
    """Datos de asistencia del ejemplo del Excel (valores iniciales del formulario)."""
    return DatosAsistencia(
        dias_habiles=22, dias_asistidos=21, atrasos=1, salidas_anticipadas=1,
        inasistencias_justificadas=1, inasistencias_injustificadas=0,
    )

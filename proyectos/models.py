from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Sum, Q, DecimalField as DBDecimal
from django.db.models.functions import Coalesce
from django.utils import timezone

from .numeros import pesos


# =========================
# AUDITORÍA / SOFT DELETE
# =========================

class AuditableModel(models.Model):
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_creados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    actualizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_actualizados",
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ActivosManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(eliminado=False)


# =========================
# CORRIENTE / CAPITAL
# =========================
# Las dos bolsas que arrastra toda la cadena (proyecto → objetivo → resultado →
# actividad). No son intercambiables: gastar capital no libera corriente. El
# presupuesto ya venía separado; lo que faltaba era separar también lo gastado,
# y para eso hay que saber a qué bolsa pertenece cada gasto. Eso lo define la
# transferencia del catálogo, que es de donde cuelga todo gasto elegible.

CORRIENTE = "CORRIENTE"
CAPITAL = "CAPITAL"

NATURALEZAS = [
    (CORRIENTE, "Corriente"),
    (CAPITAL, "Capital"),
]


class ResumenDeGastos:
    """Lo comprometido y lo pagado de un conjunto de gastos, por bolsa.

    Es la única forma de sumar gastos en el sistema: proyecto, resultado y plan
    de gasto preguntan lo mismo sobre distintos conjuntos, así que la semántica
    (qué cuenta como pagado, cómo se reparten las cuotas de un honorario) vive
    en un solo lugar.
    """

    __slots__ = ("comprometido_corriente", "comprometido_capital",
                 "pagado_corriente", "pagado_capital")

    def __init__(self):
        for campo in self.__slots__:
            setattr(self, campo, Decimal("0"))

    def agregar(self, es_capital, comprometido, pagado):
        bolsa = "capital" if es_capital else "corriente"
        setattr(self, f"comprometido_{bolsa}",
                getattr(self, f"comprometido_{bolsa}") + comprometido)
        setattr(self, f"pagado_{bolsa}", getattr(self, f"pagado_{bolsa}") + pagado)

    @property
    def comprometido(self):
        return self.comprometido_corriente + self.comprometido_capital

    @property
    def pagado(self):
        return self.pagado_corriente + self.pagado_capital

    @property
    def total(self):
        return self.comprometido + self.pagado

    @property
    def total_corriente(self):
        return self.comprometido_corriente + self.pagado_corriente

    @property
    def total_capital(self):
        return self.comprometido_capital + self.pagado_capital


def resumir_egresos(egresos):
    """Agrupa una lista de egresos en un ResumenDeGastos."""
    resumen = ResumenDeGastos()
    for egreso in egresos:
        _total, pagado, comprometido = egreso.montos
        resumen.agregar(egreso.es_capital, comprometido, pagado)
    return resumen


# =========================
# CATÁLOGO
# =========================

class TipoProyecto(models.Model):
    nombre = models.CharField(max_length=100, default="General")

    def __str__(self):
        return self.nombre


# =========================
# PROYECTO
# =========================

class ProyectoQuerySet(models.QuerySet):
    def activos(self):
        return self.filter(eliminado=False)

    def with_resumen(self):
        return self.annotate(
            _corriente_asig=Coalesce(
                Sum(
                    "objetivos__presupuesto_corriente",
                    filter=Q(objetivos__eliminado=False),
                ),
                Decimal("0"),
                output_field=DBDecimal(max_digits=15, decimal_places=2),
            ),
            _capital_asig=Coalesce(
                Sum(
                    "objetivos__presupuesto_capital",
                    filter=Q(objetivos__eliminado=False),
                ),
                Decimal("0"),
                output_field=DBDecimal(max_digits=15, decimal_places=2),
            ),
        )


class Proyecto(models.Model):

    TIPO_PROYECTO = [
        ('PACE', 'Pace'),
        ('FORT', 'Fortalecimiento'),
        ('REG', 'Regionales'),
        ('ADAIN', 'Adain'),
        ('GORE', 'Gore'),
        ('RED', 'RED'),
    ]

    ESTADOS = [
        ('PLANIFICADO', 'Planificado'),
        ('EN_EJECUCION', 'En ejecución'),
        ('FINALIZADO', 'Finalizado'),
        ('SUSPENDIDO', 'Suspendido'),
    ]

    PRIORIDADES = [
        ('BAJA', 'Baja'),
        ('MEDIA', 'Media'),
        ('ALTA', 'Alta'),
    ]

    nombre = models.CharField(max_length=500)
    codigo = models.CharField(
        "Código de proyecto", max_length=50, blank=True
    )
    descripcion = models.TextField(blank=True)

    tipo = models.CharField(max_length=10, choices=TIPO_PROYECTO, default='PACE')

    responsable = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='proyectos_responsable',
        null=True,
        blank=True,
    )

    creado_por = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='proyectos_creados',
        null=True,
        blank=True,
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    actualizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='proyectos_actualizados',
        null=True,
        blank=True,
    )
    actualizado_en = models.DateTimeField(auto_now=True, null=True)

    duracion_meses = models.PositiveIntegerField(default=0, blank=True)

    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)

    prioridad = models.CharField(max_length=10, choices=PRIORIDADES, default='MEDIA')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PLANIFICADO')

    eliminado = models.BooleanField(default=False, db_index=True)

    # PRESUPUESTO
    presupuesto_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    presupuesto_corriente = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    presupuesto_capital = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    porcentaje_corriente = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    porcentaje_capital = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # MANAGERS
    objects = ActivosManager.from_queryset(ProyectoQuerySet)()
    all_objects = models.Manager.from_queryset(ProyectoQuerySet)()

    class Meta:
        ordering = ['-fecha_creacion']

    # VALIDACIONES
    def clean(self):
        # Los montos pueden llegar como string/None si otro campo del formulario
        # falló antes de convertirlos (model.clean corre igual durante full_clean).
        # En ese caso, los errores de esos campos ya se reportan en su sitio, así
        # que omitimos las comparaciones de presupuesto para no provocar un 500
        # ("'<' not supported between instances of 'str' and 'int'").
        corriente = self._as_decimal(self.presupuesto_corriente)
        capital = self._as_decimal(self.presupuesto_capital)
        total = self._as_decimal(self.presupuesto_total)

        if corriente is not None and capital is not None:
            if corriente < 0 or capital < 0:
                raise ValidationError("El presupuesto no puede ser negativo.")
            if total is not None and (corriente + capital) != total:
                raise ValidationError(
                    "Corriente + Capital debe ser igual al presupuesto total."
                )

        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError("La fecha fin no puede ser anterior a la fecha inicio.")

    @staticmethod
    def _as_decimal(value):
        if value is None or value == "":
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    def save(self, *args, **kwargs):
        if self.porcentaje_corriente is not None and self.porcentaje_capital is not None:
            self.presupuesto_corriente = (
                self.presupuesto_total * self.porcentaje_corriente / 100
            )
            self.presupuesto_capital = (
                self.presupuesto_total * self.porcentaje_capital / 100
            )
        super().save(*args, **kwargs)

    def soft_delete(self):
        self.eliminado = True
        self.save(update_fields=['eliminado'])

    # PRESUPUESTO DERIVADO
    @property
    def corriente_asignado(self):
        if hasattr(self, '_corriente_asig'):
            return self._corriente_asig or Decimal("0")
        return self.objetivos.filter(eliminado=False).aggregate(
            total=Sum("presupuesto_corriente")
        )["total"] or Decimal("0")

    @property
    def capital_asignado(self):
        if hasattr(self, '_capital_asig'):
            return self._capital_asig or Decimal("0")
        return self.objetivos.filter(eliminado=False).aggregate(
            total=Sum("presupuesto_capital")
        )["total"] or Decimal("0")

    @property
    def presupuesto_asignado(self):
        return self.corriente_asignado + self.capital_asignado

    @property
    def presupuesto_disponible_real(self):
        return self.presupuesto_total - self.presupuesto_asignado

    @property
    def corriente_disponible(self):
        return self.presupuesto_corriente - self.corriente_asignado

    @property
    def capital_disponible(self):
        return self.presupuesto_capital - self.capital_asignado

    @property
    def porcentaje_asignado(self):
        if self.presupuesto_total == 0:
            return Decimal("0")
        return (self.presupuesto_asignado / self.presupuesto_total) * 100

    @property
    def porcentaje_corriente_usado(self):
        if self.presupuesto_corriente == 0:
            return Decimal("0")
        return (self.corriente_asignado / self.presupuesto_corriente) * 100

    @property
    def porcentaje_capital_usado(self):
        if self.presupuesto_capital == 0:
            return Decimal("0")
        return (self.capital_asignado / self.presupuesto_capital) * 100

    # CUMPLIMIENTO DERIVADO
    @property
    def cumplimiento(self):
        resultados = []
        for objetivo in self.objetivos.filter(eliminado=False):
            for r in objetivo.resultados.filter(eliminado=False):
                resultados.append(r)
        if not resultados:
            return Decimal("0")
        pesos = sum((r.presupuesto_asignado for r in resultados), Decimal("0"))
        if pesos == 0:
            return (
                sum((r.cumplimiento for r in resultados), Decimal("0")) / len(resultados)
            ).quantize(Decimal("0.01"))
        ponderado = sum(
            (r.cumplimiento * r.presupuesto_asignado for r in resultados),
            Decimal("0"),
        )
        return (ponderado / pesos).quantize(Decimal("0.01"))

    # PLANIFICACIÓN (POA: la suma de los planes de gasto)
    @property
    def planificado(self):
        from django.db.models import Sum
        total = PlanDeGasto.objects.filter(
            actividad__resultado__eliminado=False,
            actividad__resultado__objetivo__eliminado=False,
            actividad__resultado__objetivo__proyecto=self,
        ).aggregate(total=Sum("monto"))["total"]
        return total or Decimal("0")

    # `comprometido` era esto mismo, y por eso chocaba con el comprometido de
    # los gastos, que es otra cosa. Se conserva el nombre para no romper lo que
    # ya lo usa, pero lo que manda es `planificado`.
    comprometido = planificado

    @property
    def ejecutado(self):
        return self.gastos_pagados

    @property
    def saldo(self):
        return self.presupuesto_total - self.planificado

    # GASTOS (Egresos): compras con IVA + honorarios por cuotas
    def resumen_gastos(self):
        if not hasattr(self, "_resumen_gastos"):
            self._resumen_gastos = resumir_egresos(
                self.egresos.filter(eliminado=False).select_related(
                    "plan_de_gasto__gasto_elegible__gasto__tipo_gasto__transferencia",
                    "gasto_elegible__gasto__tipo_gasto__transferencia",
                )
            )
        return self._resumen_gastos

    @property
    def gastos_comprometidos(self):
        return self.resumen_gastos().comprometido

    @property
    def gastos_pagados(self):
        return self.resumen_gastos().pagado

    @property
    def gastos_total(self):
        return self.resumen_gastos().total

    @property
    def gastos_corriente(self):
        return self.resumen_gastos().total_corriente

    @property
    def gastos_capital(self):
        return self.resumen_gastos().total_capital

    @property
    def corriente_disponible_para_gastar(self):
        return self.presupuesto_corriente - self.gastos_corriente

    @property
    def capital_disponible_para_gastar(self):
        return self.presupuesto_capital - self.gastos_capital

    @property
    def disponible_para_gastar(self):
        return self.presupuesto_total - self.gastos_total

    @property
    def porcentaje_gastado(self):
        if not self.presupuesto_total:
            return Decimal("0")
        return (self.gastos_total / self.presupuesto_total * 100).quantize(Decimal("0.01"))

    # FECHAS / SALUD
    @property
    def dias_restantes(self):
        if not self.fecha_fin:
            return None
        return (self.fecha_fin - date.today()).days

    @property
    def atrasado(self):
        if self.estado == 'FINALIZADO' or not self.fecha_fin:
            return False
        return date.today() > self.fecha_fin

    # UI
    def __str__(self):
        return self.nombre

    @property
    def clase_borde(self):
        return {
            'PLANIFICADO': 'borde-planificado',
            'EN_EJECUCION': 'borde-ejecucion',
            'FINALIZADO': 'borde-finalizado',
            'SUSPENDIDO': 'borde-suspendido',
        }.get(self.estado, '')

    @property
    def clase_badge_estado(self):
        return {
            'PLANIFICADO': 'bg-secondary',
            'EN_EJECUCION': 'bg-primary',
            'FINALIZADO': 'bg-success',
            'SUSPENDIDO': 'bg-danger',
        }.get(self.estado, 'bg-light')


# =========================
# OBJETIVO ESPECÍFICO
# =========================

class ObjetivoEspecifico(AuditableModel):

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name='objetivos',
        null=True,
        blank=True,
    )

    descripcion = models.TextField(blank=True, default="")

    presupuesto_corriente = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    presupuesto_capital = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    orden = models.PositiveIntegerField(default=0, db_index=True)

    eliminado = models.BooleanField(default=False, db_index=True)

    objects = ActivosManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["orden", "id"]

    @property
    def presupuesto_asignado(self):
        return self.presupuesto_corriente + self.presupuesto_capital

    @property
    def corriente_distribuido(self):
        return self.resultados.filter(eliminado=False).aggregate(
            total=Sum("presupuesto_corriente")
        )["total"] or Decimal("0")

    @property
    def capital_distribuido(self):
        return self.resultados.filter(eliminado=False).aggregate(
            total=Sum("presupuesto_capital")
        )["total"] or Decimal("0")

    @property
    def corriente_disponible(self):
        return self.presupuesto_corriente - self.corriente_distribuido

    @property
    def capital_disponible(self):
        return self.presupuesto_capital - self.capital_distribuido

    @property
    def presupuesto_disponible(self):
        return self.corriente_disponible + self.capital_disponible

    def soft_delete(self):
        self.eliminado = True
        self.save(update_fields=['eliminado'])

    def clean(self):
        if self.presupuesto_corriente < 0 or self.presupuesto_capital < 0:
            raise ValidationError("El presupuesto no puede ser negativo.")

        if self.proyecto:
            total_corriente = self.proyecto.objetivos.exclude(pk=self.pk).aggregate(
                total=Sum("presupuesto_corriente")
            )["total"] or 0
            total_capital = self.proyecto.objetivos.exclude(pk=self.pk).aggregate(
                total=Sum("presupuesto_capital")
            )["total"] or 0

            if total_corriente + self.presupuesto_corriente > self.proyecto.presupuesto_corriente:
                raise ValidationError(
                    f"Excede presupuesto corriente del proyecto. "
                    f"Disponible: ${self.proyecto.presupuesto_corriente - total_corriente:,.0f}"
                )

            if total_capital + self.presupuesto_capital > self.proyecto.presupuesto_capital:
                raise ValidationError(
                    f"Excede presupuesto capital del proyecto. "
                    f"Disponible: ${self.proyecto.presupuesto_capital - total_capital:,.0f}"
                )

            # Hacia abajo: reducir por debajo de lo ya repartido a sus resultados
            # los dejaría financiados con dinero que el objetivo ya no tiene.
            if self.pk:
                for etiqueta, campo in (("corriente", "presupuesto_corriente"),
                                        ("capital", "presupuesto_capital")):
                    repartido = self.resultados.aggregate(
                        total=Sum(campo)
                    )["total"] or Decimal("0")
                    propuesto = getattr(self, campo) or Decimal("0")
                    if propuesto < repartido:
                        raise ValidationError(
                            f"No puedes dejar el presupuesto {etiqueta} en "
                            f"${propuesto:,.0f}: los resultados de este objetivo ya "
                            f"tienen repartidos ${repartido:,.0f}. Baja primero el "
                            f"monto de los resultados."
                        )

    def __str__(self):
        return f"Objetivo - {self.proyecto.nombre if self.proyecto else 'Sin proyecto'}"


# =========================
# RESULTADO
# =========================

class Resultado(AuditableModel):

    ESTADOS_RESULTADO = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_PROCESO', 'En proceso'),
        ('COMPLETADO', 'Completado'),
    ]

    objetivo = models.ForeignKey(
        "ObjetivoEspecifico",
        on_delete=models.CASCADE,
        related_name='resultados',
    )

    responsable = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='resultados_asignados',
        null=True,
        blank=True,
    )

    descripcion = models.TextField(blank=True, default="")
    duracion_meses = models.PositiveIntegerField(default=0)

    presupuesto_corriente = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    presupuesto_capital = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    orden = models.PositiveIntegerField(default=0, db_index=True)

    eliminado = models.BooleanField(default=False, db_index=True)

    objects = ActivosManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["orden", "id"]

    @property
    def presupuesto_asignado(self):
        return self.presupuesto_corriente + self.presupuesto_capital

    @property
    def corriente_distribuido(self):
        return self.actividades.aggregate(
            total=Sum("presupuesto_corriente")
        )["total"] or Decimal("0")

    @property
    def capital_distribuido(self):
        return self.actividades.aggregate(
            total=Sum("presupuesto_capital")
        )["total"] or Decimal("0")

    @property
    def presupuesto_distribuido(self):
        return self.corriente_distribuido + self.capital_distribuido

    @property
    def corriente_disponible(self):
        return self.presupuesto_corriente - self.corriente_distribuido

    @property
    def capital_disponible(self):
        return self.presupuesto_capital - self.capital_distribuido

    @property
    def presupuesto_sin_asignar(self):
        return self.presupuesto_asignado - self.presupuesto_distribuido

    # CUMPLIMIENTO DERIVADO
    @property
    def cumplimiento(self):
        actividades = list(self.actividades.all())
        if not actividades:
            return Decimal("0")
        pesos = sum((a.presupuesto for a in actividades), Decimal("0"))
        if pesos == 0:
            return (
                sum((Decimal(a.cumplimiento) for a in actividades), Decimal("0")) / len(actividades)
            ).quantize(Decimal("0.01"))
        ponderado = sum(
            (Decimal(a.cumplimiento) * a.presupuesto for a in actividades),
            Decimal("0"),
        )
        return (ponderado / pesos).quantize(Decimal("0.01"))

    @property
    def estado(self):
        c = self.cumplimiento
        if c >= 100:
            return 'COMPLETADO'
        if c > 0:
            return 'EN_PROCESO'
        return 'PENDIENTE'

    def get_estado_display(self):
        return dict(self.ESTADOS_RESULTADO).get(self.estado, self.estado)

    # EJECUCIÓN
    #
    # Se lee de los gastos cargados a los planes del resultado, no de los planes
    # mismos: un plan es una intención, y lo que consume presupuesto es el gasto.
    # Antes esto sumaba `PlanDeGasto.monto` y `PlanDeGasto.ejecutado`, y como
    # nada escribía esa segunda columna, un gasto marcado «Pagado» no aparecía
    # nunca en el ejecutado del resultado.
    def resumen_gastos(self):
        if not hasattr(self, "_resumen_gastos"):
            self._resumen_gastos = resumir_egresos(
                Egreso.objects
                .filter(plan_de_gasto__actividad__resultado=self)
                .select_related(
                    "plan_de_gasto__gasto_elegible__gasto__tipo_gasto__transferencia",
                    "gasto_elegible__gasto__tipo_gasto__transferencia",
                )
            )
        return self._resumen_gastos

    def gastos(self):
        """Los gastos cargados a los planes de este resultado, del último al primero."""
        return (
            Egreso.objects
            .filter(plan_de_gasto__actividad__resultado=self)
            .select_related(
                "plan_de_gasto__actividad",
                "plan_de_gasto__gasto_elegible__gasto__tipo_gasto__transferencia",
                "gasto_elegible",
            )
            .order_by("-fecha", "-creado_en")
        )

    @property
    def planificado(self):
        """Lo que suman los planes de gasto de sus actividades (el POA)."""
        return PlanDeGasto.objects.filter(
            actividad__resultado=self
        ).aggregate(total=Sum("monto"))["total"] or Decimal("0")

    @property
    def comprometido(self):
        return self.resumen_gastos().comprometido

    @property
    def comprometido_corriente(self):
        return self.resumen_gastos().comprometido_corriente

    @property
    def comprometido_capital(self):
        return self.resumen_gastos().comprometido_capital

    @property
    def ejecutado(self):
        return self.resumen_gastos().pagado

    @property
    def ejecutado_corriente(self):
        return self.resumen_gastos().pagado_corriente

    @property
    def ejecutado_capital(self):
        return self.resumen_gastos().pagado_capital

    @property
    def gastos_total(self):
        return self.resumen_gastos().total

    # El saldo descuenta las dos cosas: lo comprometido está tomado aunque no
    # se haya pagado todavía.
    @property
    def saldo(self):
        return self.presupuesto_asignado - self.gastos_total

    @property
    def saldo_corriente(self):
        return self.presupuesto_corriente - self.resumen_gastos().total_corriente

    @property
    def saldo_capital(self):
        return self.presupuesto_capital - self.resumen_gastos().total_capital

    def soft_delete(self):
        self.eliminado = True
        self.save(update_fields=['eliminado'])

    def clean(self):
        if self.presupuesto_corriente < 0 or self.presupuesto_capital < 0:
            raise ValidationError("El presupuesto no puede ser negativo.")
        if not self.objetivo:
            return

        objetivo = self.objetivo

        # El tope de un resultado es lo que le queda a su objetivo una vez
        # descontado lo que ya tienen los demás resultados. Como la pantalla suma
        # sobre el monto actual, el mensaje dice en cuánto quedaría: si no,
        # «disponible $600.000» parece contradecir que no quepan $500.000 cuando
        # el resultado ya llevaba $200.000.
        for etiqueta, campo in (("corriente", "presupuesto_corriente"),
                                ("capital", "presupuesto_capital")):
            usado_por_otros = objetivo.resultados.exclude(pk=self.pk).aggregate(
                total=Sum(campo)
            )["total"] or Decimal("0")
            del_objetivo = getattr(objetivo, campo)
            propuesto = getattr(self, campo)
            if usado_por_otros + propuesto > del_objetivo:
                tope = del_objetivo - usado_por_otros
                raise ValidationError(
                    f"Excede el presupuesto {etiqueta} del objetivo. "
                    f"El objetivo tiene ${del_objetivo:,.0f} y los demás resultados "
                    f"ya usan ${usado_por_otros:,.0f}, así que este resultado puede "
                    f"llegar hasta ${tope:,.0f} y quedaría en ${propuesto:,.0f}."
                )

            # Y hacia abajo: bajar el monto por debajo de lo que sus actividades
            # ya tienen repartido las dejaría financiadas con dinero inexistente.
            if self.pk:
                repartido = self.actividades.aggregate(total=Sum(campo))["total"] or Decimal("0")
                if propuesto < repartido:
                    raise ValidationError(
                        f"No puedes dejar el presupuesto {etiqueta} en ${propuesto:,.0f}: "
                        f"las actividades de este resultado ya tienen repartidos "
                        f"${repartido:,.0f}. Baja primero el monto de las actividades."
                    )

    def __str__(self):
        return f"Resultado - {self.objetivo.proyecto.nombre if self.objetivo else 'Sin proyecto'}"


# =========================
# ACTIVIDAD
# =========================

class Actividad(AuditableModel):

    resultado = models.ForeignKey(
        "Resultado",
        on_delete=models.CASCADE,
        related_name="actividades",
    )

    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)

    responsable = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='actividades_asignadas',
        null=True,
        blank=True,
    )

    fecha_limite = models.DateField(null=True, blank=True)

    # Cuándo terminó de verdad. Se llena a mano al cerrar la actividad, para
    # poder contrastar lo planificado con lo ocurrido (y corregirlo si se
    # anotó mal); queda vacía mientras la actividad sigue abierta.
    fecha_efectiva = models.DateField(null=True, blank=True)

    cumplimiento = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    # El presupuesto se separa en las dos bolsas que arrastra toda la cadena
    # (proyecto → objetivo → resultado → actividad): cada una se descuenta de la
    # del resultado que corresponde, porque no son intercambiables.
    presupuesto_corriente = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    presupuesto_capital = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    orden = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["orden", "id"]

    @property
    def presupuesto(self):
        """Total de la actividad. Se conserva el nombre porque es lo que leen
        el cumplimiento ponderado, los planes de gasto y las pantallas."""
        return (self.presupuesto_corriente or Decimal("0")) + (self.presupuesto_capital or Decimal("0"))

    def clean(self):
        for etiqueta, campo in (("corriente", "presupuesto_corriente"),
                                ("capital", "presupuesto_capital")):
            propuesto = getattr(self, campo) or Decimal("0")
            if propuesto < 0:
                raise ValidationError({campo: "El presupuesto no puede ser negativo."})

            usado_por_otras = self.resultado.actividades.exclude(pk=self.pk).aggregate(
                total=Sum(campo)
            )["total"] or Decimal("0")
            asignado = getattr(self.resultado, campo)

            if usado_por_otras + propuesto > asignado:
                if asignado == 0:
                    raise ValidationError({campo: (
                        f"El resultado no tiene presupuesto {etiqueta} asignado, así que "
                        f"esta actividad no puede recibir ese tipo de gasto. Asigna "
                        f"presupuesto {etiqueta} al resultado o deja el monto en $0."
                    )})
                raise ValidationError({campo: (
                    f"Supera el presupuesto {etiqueta} del resultado. "
                    f"Asignado ${asignado:,.0f} · ya distribuido ${usado_por_otras:,.0f} · "
                    f"disponible ${asignado - usado_por_otras:,.0f}."
                )})

    @property
    def tiempo_restante(self):
        if not self.fecha_limite:
            return None
        return (self.fecha_limite - timezone.now().date()).days

    @property
    def dias_restantes(self):
        if self.fecha_limite:
            return (self.fecha_limite - date.today()).days
        return None

    @property
    def atrasada(self):
        d = self.dias_restantes
        return d is not None and d < 0 and self.cumplimiento < 100

    @property
    def desviacion_dias(self):
        """Días entre la fecha efectiva y la límite. Positivo = terminó tarde.

        Solo tiene sentido una vez cerrada la actividad; mientras no haya fecha
        efectiva se informa el atraso con `dias_restantes`.
        """
        if not self.fecha_limite or not self.fecha_efectiva:
            return None
        return (self.fecha_efectiva - self.fecha_limite).days

    @property
    def cerrada_a_tiempo(self):
        d = self.desviacion_dias
        return None if d is None else d <= 0

    @property
    def presupuesto_planificado(self):
        return self.planes_gasto.aggregate(total=Sum("monto"))["total"] or Decimal("0")

    @property
    def presupuesto_disponible(self):
        return self.presupuesto - self.presupuesto_planificado

    @property
    def saldo(self):
        return self.presupuesto_disponible

    def __str__(self):
        return self.nombre


# =========================
# CATÁLOGO DE GASTOS
# =========================

class Transferencia(AuditableModel):
    nombre = models.CharField(max_length=255)

    # Guardarla como dato y no deducirla del nombre: el catálogo se puede
    # renombrar o crecer desde el admin, y de esto dependen todos los saldos.
    naturaleza = models.CharField(
        max_length=10,
        choices=NATURALEZAS,
        default=CORRIENTE,
        verbose_name="Bolsa presupuestaria",
        help_text="A qué presupuesto se descuenta lo que se gaste en esta transferencia.",
    )

    @property
    def es_capital(self):
        return self.naturaleza == CAPITAL

    def __str__(self):
        return self.nombre


class TipoGasto(AuditableModel):
    transferencia = models.ForeignKey(
        Transferencia,
        on_delete=models.CASCADE,
        related_name="tipos_gasto",
    )
    nombre = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.transferencia} - {self.nombre}"


class Gasto(AuditableModel):
    tipo_gasto = models.ForeignKey(
        TipoGasto,
        on_delete=models.CASCADE,
        related_name="gastos",
    )
    nombre = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.tipo_gasto} - {self.nombre}"


class GastoElegible(AuditableModel):
    gasto = models.ForeignKey(
        Gasto,
        on_delete=models.CASCADE,
        related_name="elegibles",
    )
    nombre = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.gasto} - {self.nombre}"


class Unidad(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    codigo = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Unidad responsable"
        verbose_name_plural = "Unidades responsables"

    def __str__(self):
        return f"{self.codigo}-{self.nombre}" if self.codigo else self.nombre


# =========================
# PLAN DE GASTO
# =========================

class PlanDeGasto(models.Model):

    actividad = models.ForeignKey(
        "Actividad",
        on_delete=models.CASCADE,
        related_name="planes_gasto",
    )

    gasto_elegible = models.ForeignKey(
        "GastoElegible",
        on_delete=models.PROTECT,
        related_name="planes_gasto",
    )

    unidad_responsable = models.ForeignKey(
        "Unidad",
        on_delete=models.PROTECT,
        related_name="planes_gasto",
        null=True,
        blank=True,
    )

    anio = models.PositiveIntegerField()

    monto = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["actividad", "gasto_elegible", "anio"],
                name="uniq_plan_actividad_gasto_anio",
            ),
        ]
        ordering = ["-anio", "actividad_id"]

    @property
    def gasto(self):
        return self.gasto_elegible.gasto

    @property
    def tipo_gasto(self):
        return self.gasto_elegible.gasto.tipo_gasto

    @property
    def transferencia(self):
        return self.gasto_elegible.gasto.tipo_gasto.transferencia

    @property
    def naturaleza(self):
        return self.transferencia.naturaleza

    # GASTOS (Egresos) cargados a este plan: compras con IVA + honorarios por cuotas
    def resumen_gastos(self):
        if not hasattr(self, "_resumen_gastos"):
            self._resumen_gastos = resumir_egresos(
                self.egresos.filter(eliminado=False).select_related(
                    "plan_de_gasto__gasto_elegible__gasto__tipo_gasto__transferencia",
                    "gasto_elegible__gasto__tipo_gasto__transferencia",
                )
            )
        return self._resumen_gastos

    @property
    def egresos_comprometidos(self):
        return self.resumen_gastos().comprometido

    @property
    def egresos_pagados(self):
        return self.resumen_gastos().pagado

    @property
    def egresos_total(self):
        return self.resumen_gastos().total

    @property
    def egresos_disponible(self):
        return self.monto - self.egresos_total

    def disponible_para(self, egreso=None):
        """Cuánto cabe todavía en el plan, sin contar el gasto que se edita.

        Es `egresos_disponible` visto desde el gasto que se está guardando: al
        editar uno ya cargado, su propio monto no puede contarse como ocupado o
        no habría forma de corregirlo.
        """
        otros = self.egresos.filter(eliminado=False)
        if egreso is not None and egreso.pk:
            otros = otros.exclude(pk=egreso.pk)
        ocupado = sum((e.montos[0] for e in otros), Decimal("0"))
        return self.monto - ocupado

    # `ejecutado` era una columna que ningún formulario escribía: quedaba en $0
    # para siempre y arrastraba a cero el ejecutado del resultado y del POA.
    # Ahora los tres nombres cortos leen los gastos realmente cargados al plan.
    comprometido = egresos_comprometidos
    ejecutado = egresos_pagados
    saldo = egresos_disponible

    @property
    def nombre_corto(self):
        actividad = self.actividad
        resultado = actividad.resultado
        objetivo = resultado.objetivo
        ge = self.gasto_elegible
        unidad_codigo = (
            self.unidad_responsable.codigo
            if self.unidad_responsable and self.unidad_responsable.codigo
            else (f"U{self.unidad_responsable_id}" if self.unidad_responsable_id else "U?")
        )
        return (
            f"{self.anio}/O{objetivo.id}/R{resultado.id}/A{actividad.id}/"
            f"T{ge.gasto.tipo_gasto.transferencia_id}/TG{ge.gasto.tipo_gasto_id}/"
            f"G{ge.gasto_id}/GE{ge.id}/{unidad_codigo}"
        )

    @property
    def nombre_completo(self):
        return f"{self.nombre_corto}/{self.gasto_elegible}"

    def clean(self):
        if self.monto is None or self.monto < 0:
            raise ValidationError("El monto no puede ser negativo.")

        total_actual = self.actividad.planes_gasto.aggregate(
            total=Sum("monto")
        )["total"] or 0

        if self.pk:
            anterior = PlanDeGasto.objects.filter(pk=self.pk).first()
            if anterior:
                total_actual -= anterior.monto

        if total_actual + self.monto > self.actividad.presupuesto:
            raise ValidationError(
                "El plan de gasto excede el presupuesto de la actividad."
            )

    def __str__(self):
        return self.nombre_completo


# =========================
# EGRESO (Compras / Honorarios / Viáticos)
# =========================

class Egreso(AuditableModel):

    TIPO_COMPRA = 'COMPRA'
    TIPO_HONORARIO = 'HONORARIO'
    TIPO_VIATICO = 'VIATICO'

    TIPOS = [
        (TIPO_COMPRA, 'Compra'),
        (TIPO_HONORARIO, 'Honorario'),
        (TIPO_VIATICO, 'Viático'),
    ]

    SUB_BIENES_INSUMOS = 'BIENES_INSUMOS'
    SUB_ALIMENTACION = 'ALIMENTACION'
    SUB_ARRIENDO_VEHICULO = 'ARRIENDO_VEHICULO'
    SUB_ALOJAMIENTO = 'ALOJAMIENTO'
    SUB_PASAJE_NACIONAL = 'PASAJE_AEREO_NACIONAL'
    SUB_PASAJE_INTERNACIONAL = 'PASAJE_AEREO_INTERNACIONAL'

    SUBTIPOS_COMPRA = [
        (SUB_BIENES_INSUMOS, 'Bienes/Insumos'),
        (SUB_ALIMENTACION, 'Alimentación'),
        (SUB_ARRIENDO_VEHICULO, 'Arriendo Vehículo'),
        (SUB_ALOJAMIENTO, 'Alojamiento'),
        (SUB_PASAJE_NACIONAL, 'Pasaje aéreo nacional'),
        (SUB_PASAJE_INTERNACIONAL, 'Pasaje aéreo internacional'),
    ]

    ESTADO_COMPROMETIDO = 'COMPROMETIDO'
    ESTADO_PAGADO = 'PAGADO'

    ESTADOS = [
        (ESTADO_COMPROMETIDO, 'Comprometido'),
        (ESTADO_PAGADO, 'Pagado'),
    ]

    # Mapeo subtipo de compra → filtro sobre GastoElegible.
    SUBTIPO_ELEGIBLE_FILTER = {
        SUB_BIENES_INSUMOS: {'gasto__nombre__iexact': 'Bienes'},
        SUB_ALIMENTACION: {'nombre__icontains': 'alimentación'},
        SUB_ARRIENDO_VEHICULO: {'nombre__icontains': 'arriendo de equipamiento y vehículos'},
        SUB_ALOJAMIENTO: {'nombre__icontains': 'arriendo de espacios'},
        SUB_PASAJE_NACIONAL: {'nombre__icontains': 'movilización'},
        SUB_PASAJE_INTERNACIONAL: {'nombre__icontains': 'movilización'},
    }

    # Mapeo tipo (no-Compra) → filtro sobre GastoElegible.
    TIPO_ELEGIBLE_FILTER = {
        TIPO_HONORARIO: {'nombre__iexact': 'Honorarios'},
        TIPO_VIATICO: {'nombre__icontains': 'viáticos'},
    }

    # Retención de impuesto a los honorarios (Chile, 15.25%).
    IMPUESTO_HONORARIOS = Decimal('0.1525')

    IVA = Decimal('0.19')

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name='egresos',
    )

    tipo = models.CharField(max_length=15, choices=TIPOS)
    subtipo_compra = models.CharField(
        max_length=30,
        choices=SUBTIPOS_COMPRA,
        blank=True,
    )

    # Centro de responsabilidad (número ingresado por el usuario)
    centro_responsabilidad = models.CharField(max_length=50, blank=True)

    plan_de_gasto = models.ForeignKey(
        PlanDeGasto,
        on_delete=models.PROTECT,
        related_name='egresos',
        null=True,
        blank=True,
    )
    gasto = models.ForeignKey(
        Gasto,
        on_delete=models.PROTECT,
        related_name='egresos',
        null=True,
        blank=True,
    )
    gasto_elegible = models.ForeignKey(
        GastoElegible,
        on_delete=models.PROTECT,
        related_name='egresos',
        null=True,
        blank=True,
    )

    # === COMPRAS ===
    cantidad = models.PositiveIntegerField(default=1)
    valor_sin_iva = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # === HONORARIOS ===
    nombre_persona = models.CharField(max_length=100, blank=True)
    apellido_persona = models.CharField(max_length=100, blank=True)
    profesion = models.CharField(max_length=100, blank=True)
    monto_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    meses = models.PositiveIntegerField(default=0)
    cuota_mensual = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # El monto de cada cuota, una por elemento y en orden. Con una sola cuota
    # mensual no había forma de repartir un total que no se divide en pesos
    # exactos ($5.000.000 en 9), ni de hacer un anticipo mayor: siempre sobraba
    # o faltaba algo. Los honorarios cargados antes no la tienen y siguen
    # funcionando: sus cuotas son todas iguales a `cuota_mensual`.
    cuotas = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Monto de cada cuota",
        help_text="Un monto por cuota, en orden. Vacío = todas iguales.",
    )
    cuotas_pagadas = models.PositiveIntegerField(default=0)
    impuestos_pagados = models.PositiveIntegerField(default=0)
    descripcion = models.CharField(max_length=500, blank=True)

    estado = models.CharField(
        max_length=15,
        choices=ESTADOS,
        default=ESTADO_COMPROMETIDO,
    )

    # === DOCUMENTOS DE LA COMPRA ===
    # El recorrido administrativo de un gasto: se solicita (SC), se ordena al
    # proveedor (OC) y se factura. Son folios, no montos: el monto ya está en el
    # gasto. Van sueltos y opcionales porque llegan en momentos distintos y casi
    # nunca están los tres el día que se registra el gasto.
    solicitud_compra = models.CharField(
        max_length=50, blank=True,
        verbose_name="Solicitud de compra (SC)",
    )
    orden_compra = models.CharField(
        max_length=50, blank=True,
        verbose_name="Orden de compra (OC)",
    )
    factura = models.CharField(
        max_length=50, blank=True,
        verbose_name="Factura",
    )

    fecha = models.DateField(default=timezone.now)
    observaciones = models.TextField(blank=True, default="")

    eliminado = models.BooleanField(default=False, db_index=True)

    objects = ActivosManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ['-fecha', '-creado_en']

    # --- DOCUMENTOS ---
    @property
    def documentos(self):
        """[(sigla, folio)] de los que estén cargados, en orden de trámite."""
        return [
            (sigla, folio) for sigla, folio in (
                ("SC", self.solicitud_compra),
                ("OC", self.orden_compra),
                ("Factura", self.factura),
            ) if folio
        ]

    # --- BOLSA (corriente / capital) ---
    @property
    def transferencia(self):
        """De qué transferencia del catálogo cuelga este gasto.

        El plan manda cuando lo hay, porque es el que descuenta presupuesto; si
        el gasto quedó sin plan se cae al gasto elegible, que apunta al mismo
        árbol del catálogo.
        """
        elegible = None
        if self.plan_de_gasto_id:
            elegible = self.plan_de_gasto.gasto_elegible
        elif self.gasto_elegible_id:
            elegible = self.gasto_elegible
        return elegible.gasto.tipo_gasto.transferencia if elegible else None

    @property
    def es_capital(self):
        transferencia = self.transferencia
        return bool(transferencia and transferencia.es_capital)

    @property
    def montos(self):
        """(total, pagado, comprometido) de este gasto.

        Las compras y los viáticos cuentan enteros según su estado; los
        honorarios se reparten por cuotas, así que un contrato a medio pagar
        aporta a las dos columnas a la vez.
        """
        if self.tipo == self.TIPO_HONORARIO:
            return (
                self.monto_total or Decimal("0"),
                self.monto_pagado_honorario,
                self.monto_pendiente_honorario,
            )
        total = self.total_con_iva
        if self.estado == self.ESTADO_PAGADO:
            return total, total, Decimal("0")
        return total, Decimal("0"), total

    # --- COMPRA ---
    @property
    def total_sin_iva(self):
        return (self.cantidad or 0) * (self.valor_sin_iva or Decimal('0'))

    @property
    def iva_monto(self):
        return self.total_sin_iva * self.IVA

    @property
    def total_con_iva(self):
        return self.total_sin_iva * (Decimal('1') + self.IVA)

    # --- HONORARIO ---
    @property
    def montos_de_cuotas(self):
        """El monto de cada cuota, en orden.

        Un honorario que nunca se detalló —o que se cargó antes de que se
        pudiera— no tiene la lista: sus cuotas son todas iguales, así que se
        arma con la cuota mensual y así el resto del código no necesita saber
        de dónde vino.
        """
        detalladas = [Decimal(str(monto)) for monto in (self.cuotas or [])]
        if detalladas:
            return detalladas
        return [self.cuota_mensual or Decimal('0')] * (self.meses or 0)

    @property
    def cuotas_son_iguales(self):
        return len(set(self.montos_de_cuotas)) <= 1

    @property
    def monto_proxima_cuota(self):
        """Lo que toca pagar en la próxima cuota."""
        montos = self.montos_de_cuotas
        siguiente = self.cuotas_pagadas or 0
        return montos[siguiente] if siguiente < len(montos) else Decimal('0')

    @property
    def cuotas_pendientes(self):
        return max(0, (self.meses or 0) - (self.cuotas_pagadas or 0))

    # Pagado y pendiente se apoyan en el monto total y no en cuotas × valor:
    # cuando el total no se divide en pesos exactos ($5.000.000 en 6 meses son
    # $833.333,33), esa multiplicación nunca da el total y el contrato quedaría
    # descuadrado por unos pesos. La diferencia la absorbe la última cuota, que
    # es lo que pasa en la práctica.
    @property
    def monto_pagado_honorario(self):
        montos = self.montos_de_cuotas
        pagadas = min(self.cuotas_pagadas or 0, len(montos))
        if montos and pagadas >= len(montos):
            # La última cuota cierra el contrato, se haya redondeado o no.
            return self.monto_total or Decimal('0')
        return sum(montos[:pagadas], Decimal('0'))

    @property
    def monto_pendiente_honorario(self):
        pendiente = (self.monto_total or Decimal('0')) - self.monto_pagado_honorario
        return max(Decimal('0'), pendiente)

    def impuesto_de_cuota(self, indice):
        montos = self.montos_de_cuotas
        if 0 <= indice < len(montos):
            return montos[indice] * self.IMPUESTO_HONORARIOS
        return Decimal('0')

    @property
    def impuesto_por_cuota(self):
        """El de la próxima cuota con impuesto pendiente.

        Con cuotas de distinto monto ya no hay un único impuesto por cuota; lo
        que se necesita saber al pagar es el de la que viene.
        """
        return self.impuesto_de_cuota(self.impuestos_pagados or 0)

    @property
    def impuestos_pendientes(self):
        # solo se puede pagar impuesto de cuotas ya pagadas
        return max(0, (self.cuotas_pagadas or 0) - (self.impuestos_pagados or 0))

    @property
    def impuesto_pendiente_total(self):
        montos = self.montos_de_cuotas
        desde = self.impuestos_pagados or 0
        hasta = min(self.cuotas_pagadas or 0, len(montos))
        return sum(montos[desde:hasta], Decimal('0')) * self.IMPUESTO_HONORARIOS

    @property
    def impuesto_pagado_total(self):
        montos = self.montos_de_cuotas
        return (sum(montos[:self.impuestos_pagados or 0], Decimal('0'))
                * self.IMPUESTO_HONORARIOS)

    @property
    def retencion_total(self):
        """El 15,25% de todo el contrato."""
        return (self.monto_total or Decimal('0')) * self.IMPUESTO_HONORARIOS

    @property
    def progreso_cuotas_pct(self):
        if not self.meses:
            return Decimal('0')
        return (Decimal(self.cuotas_pagadas) / Decimal(self.meses) * 100).quantize(Decimal('0.1'))

    @property
    def nombre_completo_persona(self):
        return f"{self.nombre_persona} {self.apellido_persona}".strip()

    def soft_delete(self):
        self.eliminado = True
        self.save(update_fields=['eliminado'])

    def clean(self):
        """Lo único que bloquea es el tope de lo disponible en el plan.

        Antes había una decena de reglas que exigían que los datos cuadraran
        entre sí —cantidad ≥ 1, cuotas × meses igual al total, subtipo, gasto
        elegible— y ninguna protegía el presupuesto: sólo dejaban gastos
        imposibles de editar, incluso para corregirlos. Los datos del contrato
        se guardan como se escriban; el que manda para el presupuesto es el
        monto, y ése sí tiene techo.
        """
        self._alinear_con_el_plan()

        if self.tipo == self.TIPO_HONORARIO:
            self._cuadrar_las_cuotas()

        # El plan es lo que hace que el gasto se descuente de alguna parte: sin
        # él no hay presupuesto contra el cual medirlo ni aparece en el
        # resultado. Es la única otra cosa que se sigue exigiendo.
        if self.tipo in (self.TIPO_COMPRA, self.TIPO_HONORARIO) and not self.plan_de_gasto_id:
            raise ValidationError(
                "Elija el plan de gasto al que se carga: es lo que dice de qué "
                "presupuesto sale."
            )

        if (self.plan_de_gasto_id
                and self.plan_de_gasto.actividad.resultado.objetivo.proyecto_id
                != self.proyecto_id):
            raise ValidationError("El Plan de gasto no pertenece a este proyecto.")

        self._validar_cupo_del_plan()

    def _cuadrar_las_cuotas(self):
        """Con las cuotas detalladas, ellas mandan.

        Los meses son cuántas son y el total es lo que suman, así que ya no hay
        nada que «cuadrar» a mano ni un total que pueda contradecir a las
        cuotas. Si no vinieron detalladas (o vinieron todas en cero), el
        honorario sigue como antes: un total y una cuota pareja.
        """
        montos = [Decimal(str(monto)) for monto in (self.cuotas or [])]
        if not any(montos):
            self.cuotas = []
            return

        self.cuotas = [str(monto) for monto in montos]
        self.meses = len(montos)
        self.monto_total = sum(montos, Decimal('0'))
        self.cuota_mensual = montos[0]

    def _alinear_con_el_plan(self):
        """El plan manda: de él salen el gasto elegible y el gasto.

        Antes esto se comprobaba y se rechazaba el gasto cuando no coincidían,
        pero esa discrepancia nunca venía de una decisión de quien carga: salía
        de un formulario a medio recargar. Alinearlos es lo que se quería.
        """
        if self.plan_de_gasto_id:
            self.gasto_elegible = self.plan_de_gasto.gasto_elegible
        if self.gasto_elegible_id:
            self.gasto = self.gasto_elegible.gasto

    def _como_esta_guardado(self):
        """El gasto tal como está en la base, para comparar con lo editado."""
        if not self.pk:
            return None
        return Egreso.all_objects.filter(pk=self.pk).first()

    def _validar_cupo_del_plan(self):
        """El plan de gasto es el techo del gasto que se le carga.

        Sin esto se podía cargar un gasto de $15.300.000 a un plan de
        $15.000.000: el sistema lo aceptaba y el disponible quedaba en rojo, que
        es avisar de un problema **después** de haberlo dejado ocurrir. El plan
        ya está topado contra el presupuesto de la actividad, así que dejar
        pasar esto rompe toda la cadena de arriba.
        """
        if not self.plan_de_gasto_id:
            return

        plan = self.plan_de_gasto
        total = self.montos[0]
        disponible = plan.disponible_para(self)
        if total <= disponible:
            return

        # Un gasto que ya estaba pasado —cargado antes de esta regla, o cuyo
        # plan se llenó después— no puede quedar imposible de editar: sin esto
        # no había forma de corregirlo ni de anotarle la factura, porque
        # cualquier guardado volvía a chocar con el tope. Mientras no crezca ni
        # se mude a otro plan, se deja pasar.
        anterior = self._como_esta_guardado()
        if (anterior is not None
                and anterior.plan_de_gasto_id == self.plan_de_gasto_id
                and total <= anterior.montos[0]):
            return

        ocupado = plan.monto - disponible
        detalle = (
            f" ({pesos(ocupado)} ya están tomados por otros gastos)"
            if ocupado else ""
        )
        raise ValidationError(
            f"El gasto es de {pesos(total)} y el plan «{plan.gasto_elegible.nombre}» "
            f"sólo tiene {pesos(disponible)} disponibles{detalle}. "
            f"Baje el monto del gasto o suba el del plan."
        )

    def __str__(self):
        return f"{self.get_tipo_display()} #{self.pk or '-'} ({self.proyecto.nombre})"

from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Sum



# AUDITORÍA 

class AuditableModel(models.Model):
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="%(class)s_creados"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    actualizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_actualizados"
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TipoProyecto(models.Model):
    nombre = models.CharField(max_length=100, default="General")

    def __str__(self):
        return self.nombre


class Proyecto(models.Model):

    TIPO_PROYECTO = [
        ('PACE', 'Pace'),
        ('FORT', 'Fortalecimiento'),
        ('REG', 'Regionales'),
        ('ADAIN', 'Adain'),
        ('GORE', 'Gore'),
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

    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)


    tipo = models.CharField(
        max_length=10,
        choices=TIPO_PROYECTO,
        default='PACE'
    )

    responsable = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='proyectos_responsable',
        null=True,
        blank=True
    )

    creado_por = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='proyectos_creados',
        null=True,
        blank=True
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    duracion_meses = models.PositiveIntegerField(
        default=0,
        blank=True
    )

    prioridad = models.CharField(
        max_length=10,
        choices=PRIORIDADES,
        default='MEDIA'
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='PLANIFICADO'
    )

    cumplimiento = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    presupuesto_total = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    presupuesto_disponible = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    def save(self, *args, **kwargs):

        if not self.pk:
            self.presupuesto_disponible = self.presupuesto_total
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

    @property
    def clase_borde(self):
        mapa = {
            'PLANIFICADO': 'borde-planificado',
            'EN_EJECUCION': 'borde-ejecucion',
            'FINALIZADO': 'borde-finalizado',
            'SUSPENDIDO': 'borde-suspendido',
        }
        return mapa.get(self.estado, '')
    @property
    def clase_badge_estado(self):
        mapa = {
            'PLANIFICADO': 'bg-secondary',
            'EN_EJECUCION': 'bg-primary',
            'FINALIZADO': 'bg-success',
            'SUSPENDIDO': 'bg-danger',
        }
        return mapa.get(self.estado, 'bg-light')



class ObjetivoEspecifico(models.Model):

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name='objetivos',
        null=True,
        blank=True
    )

    descripcion = models.TextField(default="Objetivo sin descripción")

    def __str__(self):
        return f"Objetivo - {self.proyecto.nombre if self.proyecto else 'Sin proyecto'}"



from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Sum


class Resultado(models.Model):

    ESTADOS_RESULTADO = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_PROCESO', 'En proceso'),
        ('COMPLETADO', 'Completado'),
    ]

    objetivo = models.ForeignKey(
        "ObjetivoEspecifico",
        on_delete=models.CASCADE,
        related_name='resultados'
    )

    responsable = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='resultados_asignados',
        null=True,
        blank=True
    )

    descripcion = models.TextField(blank=True, default="")

    duracion_meses = models.PositiveIntegerField(default=0)

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS_RESULTADO,
        default='PENDIENTE'
    )

    cumplimiento = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    presupuesto_corriente = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    presupuesto_capital = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    @property
    def presupuesto_asignado(self):
        return self.presupuesto_corriente + self.presupuesto_capital

    @property
    def presupuesto_distribuido(self):
        return self.actividades.aggregate(
            total=Sum("presupuesto")
        )["total"] or 0

    @property
    def presupuesto_sin_asignar(self):
        return self.presupuesto_asignado - self.presupuesto_distribuido

    @property
    def ejecutado(self):
        total_resultado = self.gastos.filter(estado="EJE").aggregate(
            total=Sum("monto")
        )["total"] or 0

        total_actividades = self.actividades.aggregate(
            total=Sum("gastos__monto", filter=models.Q(gastos__estado="EJE"))
        )["total"] or 0

        return total_resultado + total_actividades

    @property
    def comprometido(self):
        total_resultado = self.gastos.filter(estado="COM").aggregate(
            total=Sum("monto")
        )["total"] or 0

        total_actividades = self.actividades.aggregate(
            total=Sum("gastos__monto", filter=models.Q(gastos__estado="COM"))
        )["total"] or 0

        return total_resultado + total_actividades

    @property
    def saldo(self):
        return self.presupuesto_asignado - (self.ejecutado + self.comprometido)

    def clean(self):
        if self.presupuesto_corriente < 0 or self.presupuesto_capital < 0:
            raise ValidationError("El presupuesto no puede ser negativo.")

    def save(self, *args, **kwargs):
        self.full_clean()

        if self.objetivo:
            proyecto = self.objetivo.proyecto

            nuevo_total = self.presupuesto_asignado

            if self.pk:
                anterior = Resultado.objects.get(pk=self.pk)
                total_anterior = anterior.presupuesto_asignado
            else:
                total_anterior = 0

            diferencia = nuevo_total - total_anterior

            if diferencia > 0:
                if diferencia > proyecto.presupuesto_disponible:
                    raise ValidationError("No hay presupuesto suficiente en el proyecto.")

                proyecto.presupuesto_disponible -= diferencia
                proyecto.save()

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.objetivo:
            proyecto = self.objetivo.proyecto
            proyecto.presupuesto_disponible += self.presupuesto_asignado
            proyecto.save()

        super().delete(*args, **kwargs)

    def __str__(self):
        return f"Resultado - {self.objetivo.proyecto.nombre if self.objetivo else 'Sin proyecto'}"



class Actividad(AuditableModel):

    resultado = models.ForeignKey(
        "Resultado",
        on_delete=models.CASCADE,
        related_name="actividades"
    )

    nombre = models.CharField(max_length=255)

    descripcion = models.TextField(blank=True)

    responsable = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='actividades_asignadas',
        null=True,
        blank=True
    )

    fecha_limite = models.DateField(null=True, blank=True)

    cumplimiento = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    presupuesto = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    orden = models.PositiveIntegerField(default=0)

    # 🔥 VALIDACIÓN CLAVE
    def clean(self):
        total_actual = self.resultado.actividades.exclude(pk=self.pk).aggregate(
            total=Sum("presupuesto")
        )["total"] or 0

        if total_actual + self.presupuesto > self.resultado.presupuesto_asignado:
            raise ValidationError("El presupuesto excede el disponible del resultado.")

    # 🔹 DERIVADOS
    @property
    def tiempo_restante(self):
        if not self.fecha_limite:
            return None
        return (self.fecha_limite - timezone.now().date()).days

    @property
    def ejecutado(self):
        return self.gastos.filter(estado="EJE").aggregate(
            total=Sum("monto")
        )["total"] or 0

    @property
    def comprometido(self):
        return self.gastos.filter(estado="COM").aggregate(
            total=Sum("monto")
        )["total"] or 0

    @property
    def saldo(self):
        return self.presupuesto - (self.ejecutado + self.comprometido)

    

# Gastos (Compras, corriente y capital)

class GastoReal(models.Model):

    class TipoGasto(models.TextChoices):
        CORRIENTE = "COR", "Corriente"
        CAPITAL = "CAP", "Capital"

    class EstadoGasto(models.TextChoices):
        COMPROMETIDO = "COM", "Comprometido"
        EJECUTADO = "EJE", "Ejecutado"

    # RELACIÓN
    resultado = models.ForeignKey(
        "Resultado",
        on_delete=models.CASCADE,
        related_name="gastos"
    )

    # DATOS
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)

    monto = models.DecimalField(
        max_digits=15,
        decimal_places=2
    )

    tipo_gasto = models.CharField(
        max_length=3,
        choices=TipoGasto.choices
    )

    estado = models.CharField(
        max_length=3,
        choices=EstadoGasto.choices,
        default=EstadoGasto.COMPROMETIDO
    )

    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} - ${self.monto}"
    


# TRANSFERENCIA

class Transferencia(AuditableModel):
    nombre = models.CharField(max_length=255)

    def __str__(self):
        return self.nombre



# TIPO DE GASTO

class TipoGasto(AuditableModel):
    transferencia = models.ForeignKey(
        Transferencia,
        on_delete=models.CASCADE,
        related_name="tipos_gasto"
    )
    nombre = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.transferencia} - {self.nombre}"



# GASTO (CATEGORÍA)

class Gasto(AuditableModel):
    tipo_gasto = models.ForeignKey(
        TipoGasto,
        on_delete=models.CASCADE,
        related_name="gastos"
    )
    nombre = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.tipo_gasto} - {self.nombre}"



# GASTO ELEGIBLE (DETALLE)

class GastoElegible(AuditableModel):
    gasto = models.ForeignKey(
        Gasto,
        on_delete=models.CASCADE,
        related_name="elegibles"
    )
    nombre = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.gasto} - {self.nombre}"
    

class PlanDeGasto(AuditableModel):

    # PERIODO
    anio = models.PositiveIntegerField()

    # ESTRUCTURA
    objetivo = models.ForeignKey(
        ObjetivoEspecifico,
        on_delete=models.CASCADE,
        related_name="planes_gasto"
    )

    resultado = models.ForeignKey(
        Resultado,
        on_delete=models.CASCADE,
        related_name="planes_gasto"
    )

    # FUTURO
    # actividad = models.ForeignKey(...)

    # CLASIFICACIÓN
    tipo_gasto = models.ForeignKey(TipoGasto, on_delete=models.PROTECT)
    gasto = models.ForeignKey(Gasto, on_delete=models.PROTECT)
    gasto_elegible = models.ForeignKey(GastoElegible, on_delete=models.PROTECT)

    # FUTURO
    # unidad_academica = models.ForeignKey(...)

    # MONTO PLANIFICADO
    monto = models.DecimalField(max_digits=15, decimal_places=2)

    def clean(self):

        # consistencia estructural
        if self.resultado.objetivo != self.objetivo:
            raise ValidationError("El resultado no pertenece al objetivo.")

    def __str__(self):
        return f"{self.anio} / OE{self.objetivo.id} / R{self.resultado.id}"
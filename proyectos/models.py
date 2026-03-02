from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


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


class Resultado(models.Model):

    ESTADOS_RESULTADO = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_PROCESO', 'En proceso'),
        ('COMPLETADO', 'Completado'),
    ]

    objetivo = models.ForeignKey(
        ObjetivoEspecifico,
        on_delete=models.CASCADE,
        related_name='resultados',
        null=True,
        blank=True
    )

    descripcion = models.TextField(default="Resultado sin descripción")

    responsable = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='resultados_asignados',
        null=True,
        blank=True
    )

    duracion_meses = models.PositiveIntegerField(
        default=0
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS_RESULTADO,
        default='PENDIENTE'
    )

    cumplimiento = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    presupuesto_asignado = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    

    def clean(self):
        if self.objetivo:
            proyecto = self.objetivo.proyecto
            if proyecto and self.presupuesto_asignado > proyecto.presupuesto_disponible:
                raise ValidationError("No hay presupuesto disponible suficiente en el proyecto.")

    def save(self, *args, **kwargs):

        if self.objetivo:
            proyecto = self.objetivo.proyecto

            # Si es nuevo resultado
            if not self.pk:
                if self.presupuesto_asignado > proyecto.presupuesto_disponible:
                    raise ValidationError("Presupuesto insuficiente.")

                proyecto.presupuesto_disponible -= self.presupuesto_asignado
                proyecto.save()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Resultado - {self.objetivo.proyecto.nombre if self.objetivo else 'Sin proyecto'}"

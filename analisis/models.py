from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator


class Informe(models.Model):

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        EN_PROCESO = "EN_PROCESO", "En proceso"
        EN_REVISION = "EN_REVISION", "En revisión"
        FINALIZADO = "FINALIZADO", "Finalizado"
        SUSPENDIDO = "SUSPENDIDO", "Suspendido"

    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(max_length=1000)

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE
    )

    fecha_estimada_termino = models.DateField(null=True, blank=True)

    responsable = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="informes",
        null=True,
        blank=True,
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"{self.nombre} - {self.get_estado_display()}"


class MovimientoInforme(models.Model):

    class Tipo(models.TextChoices):
        CREACION = "CREACION", "Creación"
        EDICION = "EDICION", "Edición"
        CAMBIO_ESTADO = "CAMBIO_ESTADO", "Cambio de estado"
        APROBACION = "APROBACION", "Aprobación"
        RECHAZO = "RECHAZO", "Devolución"

    informe = models.ForeignKey(
        Informe,
        on_delete=models.CASCADE,
        related_name="movimientos",
    )
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_informe",
    )
    tipo = models.CharField(
        max_length=20,
        choices=Tipo.choices,
    )

    estado_anterior = models.CharField(max_length=20, blank=True)
    estado_nuevo = models.CharField(max_length=20, blank=True)

    detalle = models.TextField(blank=True)

    documento = models.FileField(
        upload_to="informes/revisiones/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "doc", "docx"])],
    )

    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.informe.nombre} ({self.fecha:%Y-%m-%d %H:%M})"

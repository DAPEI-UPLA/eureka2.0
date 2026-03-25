from django.db import models
from django.contrib.auth.models import User


class Iniciativa(models.Model):

    class FuncionInstitucional(models.TextChoices):
        DOCENCIA = "DOCENCIA", "Docencia"
        INVESTIGACION = "INVESTIGACION", "Investigación"
        VINCULACION = "VINCULACION", "Vinculación con el Medio"
        GESTION = "GESTION", "Gestión Estratégica"

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        ENVIADA = "ENVIADA", "Enviada"
        REVISION_OCT = "REVISION_OCT", "Revisión OCT"
        DEVUELTA = "DEVUELTA", "Devuelta con observaciones"
        APROBADA = "APROBADA", "Aprobada por OCT"
        POSTULADA = "POSTULADA", "Postulada"
        ADJUDICADA = "ADJUDICADA", "Adjudicada"
        NO_ADJUDICADA = "NO_ADJUDICADA", "No adjudicada"

    nombre = models.CharField(max_length=255)
    descripcion = models.CharField(max_length=500)

    unidad = models.CharField(max_length=255)

    responsable = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="iniciativas"
    )

    funcion_institucional = models.CharField(
        max_length=30,
        choices=FuncionInstitucional.choices
    )

    estado = models.CharField(
        max_length=30,
        choices=Estado.choices,
        default=Estado.BORRADOR
    )

    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_termino = models.DateField(null=True, blank=True)

    descarga_horas = models.BooleanField(default=False)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.nombre} - {self.get_estado_display()}"
    

class DocumentoIniciativa(models.Model):
    iniciativa = models.ForeignKey(
        Iniciativa,
        on_delete=models.CASCADE,
        related_name="documentos"
    )

    archivo = models.FileField(upload_to="iniciativas/")
    fecha_subida = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Documento - {self.iniciativa.nombre}"
    
    
class Formulacion(models.Model):

    class Estado(models.TextChoices):
        BORRADOR = "BOR", "Borrador"
        ENVIADA = "ENV", "Enviada a revisión"
        DEVUELTA = "DEV", "Devuelta con observaciones"
        APROBADA = "APR", "Aprobada"

    iniciativa = models.OneToOneField(
        "Iniciativa",
        on_delete=models.CASCADE,
        related_name="formulacion"
    )

    nombre_fondo = models.CharField(
        max_length=200
    )

    link_convocatoria = models.URLField(
        blank=True,
        null=True
    )

    estado = models.CharField(
        max_length=3,
        choices=Estado.choices,
        default=Estado.BORRADOR
    )

    observaciones = models.TextField(
        blank=True,
        null=True
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)




    
class DocumentoFormulacion(models.Model):

    formulacion = models.ForeignKey(
        Formulacion,
        on_delete=models.CASCADE,
        related_name="documentos"
    )

    archivo = models.FileField(
        upload_to="formulaciones/"
    )

    fecha_subida = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Documento {self.formulacion.iniciativa.nombre}"
    
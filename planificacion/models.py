from django.db import models
from django.conf import settings



# TIPO DE INDICADOR


class TipoIndicador(models.Model):
    nombre = models.CharField(max_length=50)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Tipo de Indicador"
        verbose_name_plural = "Tipos de Indicadores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

#------------------------------------------------------------------------

# PROGRAMA


class Programa(models.Model):

    nombre = models.CharField(max_length=100)

    objetivos = models.ManyToManyField(
        "Objetivo",
        blank=True,
        related_name="programas_asociados"  
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="programas_creados"
    )

    class Meta:
        verbose_name = "Programa / PD"
        verbose_name_plural = "Programas / PD"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def total_objetivos(self):
        return self.objetivos.count()

#----------------------------------------------------------------------------------------

# OBJETIVO


class Objetivo(models.Model):

    class TipoObjetivo(models.TextChoices):
        ESTRATEGICO = "ESTRATEGICO", "Estratégico"
        ESPECIFICO = "ESPECIFICO", "Específico"

    nombre = models.CharField(
        max_length=200,
        verbose_name="Nombre"
    )

    descripcion = models.TextField(
        verbose_name="Descripción",
        max_length= 500
    )

    tipo = models.CharField(
        max_length=20,
        choices=TipoObjetivo.choices,
        verbose_name="Tipo de objetivo"
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación"
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="objetivos_creados",
        verbose_name="Creado por"
    )

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Objetivo"
        verbose_name_plural = "Objetivos"

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"


#-----------------------------------------------------------------------------------

# INDICADOR

class Indicador(models.Model):

    # =========================
    # CHOICES
    # =========================
    class UnidadMedida(models.TextChoices):
        CARACTERES = "CAR", "Caracteres"
        PORCENTUAL = "POR", "Porcentual"
        UNITARIO = "UNI", "Unitario"

    # =========================
    # RELACIONES
    # =========================
    objetivo = models.ForeignKey(
        "Objetivo",
        on_delete=models.CASCADE,
        related_name="indicadores",
    )

    # =========================
    # DATOS PRINCIPALES
    # =========================
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField()

    formula = models.TextField(
        blank=True,
        help_text="Ej: (Cantidad lograda / Meta) * 100"
    )


    unidad_medida = models.CharField(
        max_length=3,
        choices=UnidadMedida.choices,
        default=UnidadMedida.UNITARIO
    )

    # =========================
    # CONFIGURACIÓN DEL INDICADOR
    # =========================
    linea_base = models.BooleanField(
        default=False,
        verbose_name="¿Aplica línea base?"
    )

    calculo_invertido = models.BooleanField(
        default=False,
        verbose_name="¿Es cálculo invertido?"
    )

    acumulativo = models.BooleanField(
        default=False,
        verbose_name="¿Es acumulativo?"
    )

    # =========================
    # AUDITORÍA
    # =========================
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="indicadores_creados"
    )

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Indicador"
        verbose_name_plural = "Indicadores"

    def __str__(self):
        return self.nombre

#-----------------------------------------------------------------


# ESTRATEGIA


class Estrategia(models.Model):

    class Plazo(models.TextChoices):
        CORTO = "CORTO", "Corto plazo"
        MEDIANO = "MEDIANO", "Mediano plazo"
        LARGO = "LARGO", "Largo plazo"

    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.CASCADE,
        related_name="estrategias",
        null=True,
        blank=True
    )

    nombre = models.CharField(
        max_length=200,
        verbose_name="Nombre"
    )

    descripcion = models.TextField(
        verbose_name="Descripción"
    )

    plazo = models.CharField(
        max_length=10,
        choices=Plazo.choices,
        default=Plazo.CORTO
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación"
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="estrategias_creadas",
        verbose_name="Creado por"
    )

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Estrategia"
        verbose_name_plural = "Estrategias"

    def __str__(self):
        return f"{self.nombre} ({self.get_plazo_display()})"
    

class ProgramaIndicador(models.Model):

    programa = models.ForeignKey(
        "Programa",
        on_delete=models.CASCADE,
        related_name="programas_indicadores"
    )

    indicador = models.ForeignKey(
        "Indicador",
        on_delete=models.CASCADE,
        related_name="indicadores_programa"
    )

    meta = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    anio_meta = models.IntegerField(
        null=True,
        blank=True
    )

    linea_base_valor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    class Meta:
        unique_together = ("programa", "indicador")


class SeguimientoIndicador(models.Model):

    programa_indicador = models.ForeignKey(
        "ProgramaIndicador",
        on_delete=models.CASCADE,
        related_name="seguimientos"
    )

    anio = models.IntegerField()

    valor = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("programa_indicador", "anio")
        ordering = ["anio"]
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


# =============================================================
# MANAGERS
# =============================================================

class ActivosManager(models.Manager):
    """Excluye registros con eliminado=True."""
    def get_queryset(self):
        return super().get_queryset().filter(eliminado=False)


# =============================================================
# TIPO INDICADOR
# =============================================================

class TipoIndicador(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Tipo de Indicador"
        verbose_name_plural = "Tipos de Indicadores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


# =============================================================
# PROGRAMA
# =============================================================

class Programa(models.Model):

    class TipoPrograma(models.TextChoices):
        PEI = "PEI", "PEI"
        PD_UNIDADES = "PD_UNI", "PD Unidades Académicas"
        PD_FUNCIONES = "PD_FUN", "PD Funciones Institucionales"

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        VIGENTE = "VIGENTE", "Vigente"
        CERRADO = "CERRADO", "Cerrado"

    nombre = models.CharField(max_length=100)

    tipo = models.CharField(
        max_length=10,
        choices=TipoPrograma.choices,
        default=TipoPrograma.PEI,
    )

    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )

    objetivos = models.ManyToManyField(
        "Objetivo",
        blank=True,
        related_name="programas_asociados",
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="programas_creados",
    )

    eliminado = models.BooleanField(default=False)

    objects = ActivosManager()
    todos = models.Manager()

    class Meta:
        verbose_name = "Programa / PD"
        verbose_name_plural = "Programas / PD"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["nombre", "tipo"],
                condition=models.Q(eliminado=False),
                name="programa_unico_nombre_tipo_activo",
            ),
        ]

    def __str__(self):
        return self.nombre

    def total_objetivos(self):
        return self.objetivos.count()

    @property
    def es_editable(self):
        return self.estado != self.Estado.CERRADO


# =============================================================
# OBJETIVO
# =============================================================

class Objetivo(models.Model):

    class TipoObjetivo(models.TextChoices):
        ESTRATEGICO = "ESTRATEGICO", "Estratégico"
        ESPECIFICO = "ESPECIFICO", "Específico"

    nombre = models.CharField(max_length=500, verbose_name="Nombre")
    descripcion = models.TextField(verbose_name="Descripción", max_length=500)

    tipo = models.CharField(
        max_length=20,
        choices=TipoObjetivo.choices,
        verbose_name="Tipo de objetivo",
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True, verbose_name="Fecha de creación"
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="objetivos_creados",
        verbose_name="Creado por",
    )

    eliminado = models.BooleanField(default=False)

    objects = ActivosManager()
    todos = models.Manager()

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Objetivo"
        verbose_name_plural = "Objetivos"

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"


# =============================================================
# INDICADOR
# =============================================================

class Indicador(models.Model):

    class UnidadMedida(models.TextChoices):
        CARACTERES = "CAR", "Caracteres"
        PORCENTUAL = "POR", "Porcentual"
        UNITARIO = "UNI", "Unitario"

    class Frecuencia(models.TextChoices):
        SEMESTRAL = "SEMESTRAL", "Semestral"
        ANUAL = "ANUAL", "Anual"

    objetivo = models.ForeignKey(
        "Objetivo",
        on_delete=models.CASCADE,
        related_name="indicadores",
    )

    nombre = models.CharField(max_length=200)
    descripcion = models.TextField()
    formula = models.TextField(
        blank=True,
        help_text="Ej: (Cantidad lograda / Meta) * 100",
    )

    unidad_medida = models.CharField(
        max_length=3,
        choices=UnidadMedida.choices,
        default=UnidadMedida.UNITARIO,
    )

    frecuencia = models.CharField(
        max_length=10,
        choices=Frecuencia.choices,
        default=Frecuencia.SEMESTRAL,
    )

    linea_base = models.BooleanField(
        default=False, verbose_name="¿Aplica línea base?"
    )
    calculo_invertido = models.BooleanField(
        default=False, verbose_name="¿Es cálculo invertido?"
    )
    acumulativo = models.BooleanField(
        default=False, verbose_name="¿Es acumulativo?"
    )

    # Umbrales de avance (en %): por defecto 70 y 90 según institución
    umbral_aceptable = models.PositiveSmallIntegerField(
        default=70,
        help_text="Avance % desde el cual se considera amarillo (aceptable).",
    )
    umbral_optimo = models.PositiveSmallIntegerField(
        default=90,
        help_text="Avance % desde el cual se considera verde (óptimo).",
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="indicadores_creados",
    )

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Indicador"
        verbose_name_plural = "Indicadores"

    def __str__(self):
        return self.nombre


# =============================================================
# ESTRATEGIA
# =============================================================

class Estrategia(models.Model):

    class Plazo(models.TextChoices):
        CORTO = "CORTO", "Corto plazo"
        MEDIANO = "MEDIANO", "Mediano plazo"
        LARGO = "LARGO", "Largo plazo"

    indicadores = models.ManyToManyField(
        Indicador,
        blank=True,
        related_name="estrategias",
        verbose_name="Indicadores asociados",
    )

    nombre = models.CharField(max_length=200, verbose_name="Nombre")
    descripcion = models.TextField(verbose_name="Descripción")

    plazo = models.CharField(
        max_length=10,
        choices=Plazo.choices,
        default=Plazo.CORTO,
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True, verbose_name="Fecha de creación"
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="estrategias_creadas",
        verbose_name="Creado por",
    )

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Estrategia"
        verbose_name_plural = "Estrategias"

    def __str__(self):
        return f"{self.nombre} ({self.get_plazo_display()})"


# =============================================================
# PROGRAMA <-> INDICADOR
# =============================================================

class ProgramaIndicador(models.Model):

    programa = models.ForeignKey(
        "Programa",
        on_delete=models.CASCADE,
        related_name="programas_indicadores",
    )

    indicador = models.ForeignKey(
        "Indicador",
        on_delete=models.CASCADE,
        related_name="indicadores_programa",
    )

    # Meta legacy (se mantiene como meta por defecto si no hay MetaIndicador específico)
    meta = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    anio_meta = models.IntegerField(null=True, blank=True)
    linea_base_valor = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    peso = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Peso relativo del indicador para el avance global ponderado.",
    )

    class Meta:
        unique_together = ("programa", "indicador")

    def __str__(self):
        return f"{self.programa} ↔ {self.indicador}"

    def clean(self):
        super().clean()
        if self.programa_id and self.indicador_id:
            # El objetivo del indicador debe estar en el programa
            obj_indicador_id = self.indicador.objetivo_id
            if not self.programa.objetivos.filter(id=obj_indicador_id).exists():
                raise ValidationError(
                    "El objetivo del indicador no está asociado al programa."
                )

    def meta_para(self, anio):
        """Devuelve dict {valor, estado, display} para el año pedido."""
        m = self.metas_anuales.filter(anio=anio).first()
        if m:
            return {"valor": m.valor, "estado": m.estado, "display": m.display}
        if self.meta is not None:
            return {"valor": self.meta, "estado": "VALOR", "display": self.meta}
        return {"valor": None, "estado": "VALOR", "display": None}


class MetaIndicador(models.Model):
    """Meta específica del indicador para un año dado, dentro de un programa."""

    class EstadoMeta(models.TextChoices):
        VALOR = "VALOR", "Valor"
        SIN_MEDICION = "SM", "Sin medición"
        NO_APLICA = "NA", "No aplica"

    programa_indicador = models.ForeignKey(
        ProgramaIndicador,
        on_delete=models.CASCADE,
        related_name="metas_anuales",
    )

    anio = models.IntegerField()

    valor = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    estado = models.CharField(
        max_length=5,
        choices=EstadoMeta.choices,
        default=EstadoMeta.VALOR,
    )

    class Meta:
        unique_together = ("programa_indicador", "anio")
        ordering = ["anio"]
        indexes = [models.Index(fields=["anio"])]

    def __str__(self):
        if self.estado != self.EstadoMeta.VALOR:
            return f"Meta {self.anio}: {self.get_estado_display()}"
        return f"Meta {self.anio}: {self.valor}"

    @property
    def display(self):
        if self.estado == self.EstadoMeta.SIN_MEDICION:
            return "S/M"
        if self.estado == self.EstadoMeta.NO_APLICA:
            return "N/A"
        return self.valor


# =============================================================
# SEGUIMIENTO
# =============================================================

class SeguimientoIndicador(models.Model):

    class Semestre(models.IntegerChoices):
        S1 = 1, "Primer semestre"
        S2 = 2, "Segundo semestre"

    class EstadoMedicion(models.TextChoices):
        VALOR = "VALOR", "Valor"
        SIN_MEDICION = "SM", "Sin medición"
        NO_APLICA = "NA", "No aplica"

    programa_indicador = models.ForeignKey(
        "ProgramaIndicador",
        on_delete=models.CASCADE,
        related_name="seguimientos",
    )

    anio = models.IntegerField()
    semestre = models.PositiveSmallIntegerField(
        choices=Semestre.choices, default=Semestre.S2
    )

    valor = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    estado = models.CharField(
        max_length=5,
        choices=EstadoMedicion.choices,
        default=EstadoMedicion.VALOR,
    )

    comentario = models.TextField(blank=True)
    evidencia = models.FileField(
        upload_to="planificacion/evidencias/", blank=True, null=True
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="seguimientos_registrados",
    )

    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("programa_indicador", "anio", "semestre")
        ordering = ["anio", "semestre"]
        indexes = [
            models.Index(fields=["anio", "semestre"]),
            models.Index(fields=["programa_indicador", "anio"]),
        ]

    def __str__(self):
        return f"{self.programa_indicador} — {self.anio}/S{self.semestre}: {self.display}"

    @property
    def display(self):
        if self.estado == self.EstadoMedicion.SIN_MEDICION:
            return "S/M"
        if self.estado == self.EstadoMedicion.NO_APLICA:
            return "N/A"
        return self.valor

    @property
    def es_valor_numerico(self):
        return self.estado == self.EstadoMedicion.VALOR and self.valor is not None


# =============================================================
# CIERRE ANUAL
# =============================================================

class CierreAnual(models.Model):
    programa = models.ForeignKey(
        Programa,
        on_delete=models.CASCADE,
        related_name="cierres",
    )
    anio = models.IntegerField()

    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    fecha_cierre = models.DateTimeField(auto_now_add=True)
    comentario = models.TextField(blank=True)

    class Meta:
        unique_together = ("programa", "anio")
        ordering = ["-anio"]

    def __str__(self):
        return f"Cierre {self.programa} — {self.anio}"

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


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

    @property
    def nombre_archivo(self):
        import os
        return os.path.basename(self.archivo.name)
    
    
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

    @property
    def nombre_archivo(self):
        import os
        return os.path.basename(self.archivo.name)


class MovimientoIniciativa(models.Model):
    """Bitácora de eventos de una iniciativa (creación, envíos, aprobaciones,
    devoluciones, formulación y cambios de estado del ciclo de vida)."""

    class Tipo(models.TextChoices):
        CREACION = "CREACION", "Creación"
        ENVIO = "ENVIO", "Envío a revisión"
        APROBACION = "APROBACION", "Aprobación"
        DEVOLUCION = "DEVOLUCION", "Devolución"
        EDICION = "EDICION", "Edición"
        FORMULACION = "FORMULACION", "Formulación"
        CAMBIO_ESTADO = "CAMBIO_ESTADO", "Cambio de estado"
        DOCUMENTO = "DOCUMENTO", "Documento"

    iniciativa = models.ForeignKey(
        Iniciativa,
        on_delete=models.CASCADE,
        related_name="movimientos",
    )
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_iniciativa",
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    estado_anterior = models.CharField(max_length=30, blank=True)
    estado_nuevo = models.CharField(max_length=30, blank=True)
    detalle = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.iniciativa.nombre} ({self.fecha:%Y-%m-%d %H:%M})"


# =============================================================
# TABLERO MAESTRO DE RESULTADOS
#
# Sistematiza «Planilla_Resultados_OCT_2026.xlsx». La planilla tiene una sola
# hoja de datos —"Registro iniciativas"— más dos hojas de parámetros que se
# escriben a mano (la proyección financiera y las metas anuales); todo lo
# demás son fórmulas. Acá pasa lo mismo: se guardan los datos y los
# parámetros, y el avance mensual y el tablero de control se calculan en
# ``oct/tablero.py``. Así no hay dos versiones del mismo número.
# =============================================================


class Ambito(models.TextChoices):
    """Las cuatro líneas de trabajo del tablero. Los rótulos son los mismos que
    usa la lista desplegable del Excel, así el archivo se lee sin traducir."""

    PROYECTOS = "PROYECTOS", "Proyectos"
    LICITACIONES = "LICITACIONES", "Licitaciones"
    CONVENIOS = "CONVENIOS", "Convenios"
    DONACIONES = "DONACIONES", "Donaciones"


class EstadoGestion(models.TextChoices):
    """Los nueve estados de la validación de datos de la planilla."""

    EN_IDENTIFICACION = "EN_IDENTIFICACION", "En identificación"
    EN_PREPARACION = "EN_PREPARACION", "En preparación"
    PRESENTADA = "PRESENTADA", "Presentada"
    EN_EVALUACION = "EN_EVALUACION", "En evaluación"
    ADJUDICADA = "ADJUDICADA", "Adjudicada"
    NO_ADJUDICADA = "NO_ADJUDICADA", "No adjudicada"
    DESISTIDA = "DESISTIDA", "Desistida"
    SUSCRITA = "SUSCRITA", "Suscrita"
    RECIBIDA = "RECIBIDA", "Recibida"


# Estados que el Excel cuenta como "presentada/formalizada": la gestión salió
# de la casa y está en manos del financista.
ESTADOS_PRESENTADOS = frozenset({
    EstadoGestion.PRESENTADA,
    EstadoGestion.EN_EVALUACION,
    EstadoGestion.ADJUDICADA,
    EstadoGestion.NO_ADJUDICADA,
    EstadoGestion.SUSCRITA,
    EstadoGestion.RECIBIDA,
})

# Qué significa "resultado exitoso" en cada ámbito. Un convenio no se adjudica,
# se suscribe; una donación se recibe. El Excel usa un estado distinto por
# ámbito y acá se respeta.
ESTADO_EXITOSO = {
    Ambito.PROYECTOS: EstadoGestion.ADJUDICADA,
    Ambito.LICITACIONES: EstadoGestion.ADJUDICADA,
    Ambito.CONVENIOS: EstadoGestion.SUSCRITA,
    Ambito.DONACIONES: EstadoGestion.RECIBIDA,
}


class Origen(models.TextChoices):
    """De dónde vino el registro.

    Es lo que impide que la carga de un Excel borre en silencio lo que se
    cargó a mano: al podar, el importador solo mira lo IMPORTADO.
    """

    IMPORTADO = "IMPORTADO", "Importado del Excel"
    MANUAL = "MANUAL", "Cargado en el sistema"


class Gestion(models.Model):
    """Una fila de la hoja «Registro iniciativas»: una postulación, oferta,
    convenio o donación en curso."""

    anio = models.PositiveSmallIntegerField("Año", default=2026, db_index=True)

    codigo = models.CharField("Código", max_length=100, blank=True)
    ambito = models.CharField("Ámbito", max_length=20, choices=Ambito.choices)
    tipo = models.CharField("Tipo de iniciativa", max_length=200, blank=True)
    nombre = models.CharField("Nombre de la iniciativa", max_length=300)
    institucion = models.CharField("Institución", max_length=200, blank=True)

    fecha_ingreso = models.DateField("Fecha de ingreso", null=True, blank=True)
    monto_postulado = models.DecimalField(
        "Monto postulado", max_digits=14, decimal_places=0, default=0)

    estado = models.CharField(
        max_length=20, choices=EstadoGestion.choices,
        default=EstadoGestion.EN_IDENTIFICACION)

    fecha_resultado = models.DateField("Fecha de resultado", null=True, blank=True)
    monto_adjudicado = models.DecimalField(
        "Monto adjudicado", max_digits=14, decimal_places=0, default=0)

    responsable = models.CharField(max_length=200, blank=True)
    observaciones = models.TextField(blank=True)

    origen = models.CharField(
        max_length=10, choices=Origen.choices, default=Origen.MANUAL)

    # --- Rastro de lo editado en pantalla ---
    # El Excel no pisa un campo que alguien corrigió acá sin preguntar. Se
    # guarda la lista de campos tocados (no solo un "sí/no") para que el aviso
    # de la carga pueda decir exactamente qué chocaría.
    campos_editados = models.JSONField(default=list, blank=True)
    editado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="gestiones_oct_editadas")
    fecha_edicion = models.DateTimeField(null=True, blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "gestión del tablero"
        verbose_name_plural = "gestiones del tablero"
        ordering = ["ambito", "-fecha_ingreso", "nombre"]
        indexes = [models.Index(fields=["anio", "ambito"])]

    def __str__(self):
        return f"{self.codigo or '—'} · {self.nombre}"

    # -- meses, que en el Excel eran una fórmula TEXT(fecha,"mmm-yy") --

    @property
    def mes_ingreso(self):
        return self.fecha_ingreso.month if self.fecha_ingreso else None

    @property
    def mes_resultado(self):
        return self.fecha_resultado.month if self.fecha_resultado else None

    # -- clasificación --

    @property
    def fue_presentada(self):
        return self.estado in ESTADOS_PRESENTADOS

    @property
    def es_exitosa(self):
        return self.estado == ESTADO_EXITOSO.get(self.ambito)

    @property
    def editada_en_sistema(self):
        return bool(self.campos_editados)

    def marcar_editada(self, campos, usuario=None):
        """Suma campos a la lista de lo tocado en pantalla, sin perder los
        anteriores: dos ediciones seguidas protegen ambas cosas."""
        tocados = set(self.campos_editados or []) | set(campos)
        self.campos_editados = sorted(tocados)
        self.editado_por = usuario if usuario and usuario.is_authenticated else None
        self.fecha_edicion = timezone.now()


class ProyeccionMensual(models.Model):
    """Hoja «Proyección financiera»: el ingreso que se espera por ámbito y mes.

    Es un dato de planificación que se escribe a mano —no sale del registro—,
    y es el denominador del cumplimiento financiero.
    """

    anio = models.PositiveSmallIntegerField("Año", default=2026)
    ambito = models.CharField("Ámbito", max_length=20, choices=Ambito.choices)
    mes = models.PositiveSmallIntegerField("Mes")
    monto = models.DecimalField(max_digits=14, decimal_places=0, default=0)

    class Meta:
        verbose_name = "proyección mensual"
        verbose_name_plural = "proyección financiera"
        ordering = ["anio", "ambito", "mes"]
        constraints = [
            models.UniqueConstraint(
                fields=["anio", "ambito", "mes"], name="oct_proyeccion_unica"),
        ]

    def __str__(self):
        return f"{self.get_ambito_display()} {self.mes:02d}/{self.anio}: {self.monto}"


class MetaAmbito(models.Model):
    """Columna «Meta anual de gestiones» del tablero de control."""

    anio = models.PositiveSmallIntegerField("Año", default=2026)
    ambito = models.CharField("Ámbito", max_length=20, choices=Ambito.choices)
    meta_gestiones = models.PositiveIntegerField("Meta anual de gestiones", default=0)

    class Meta:
        verbose_name = "meta anual"
        verbose_name_plural = "metas anuales"
        ordering = ["anio", "ambito"]
        constraints = [
            models.UniqueConstraint(
                fields=["anio", "ambito"], name="oct_meta_unica"),
        ]

    def __str__(self):
        return f"{self.get_ambito_display()} {self.anio}: {self.meta_gestiones}"

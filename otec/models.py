"""Modelo de datos de OTEC UPLA.

Sistematiza el "Tablero Maestro OTEC UPLA", donde cada fila de la hoja
``Registro Actividades`` era un curso y los datos comerciales y de decretación
se repetían a mano en todas las filas de una misma propuesta.

Aquí esa jerarquía queda explícita:

    Institucion ─< Propuesta ─< Actividad ─< ItemChecklist

y todo lo que en la planilla era fórmula (avance de checklist, alerta,
excedente, margen, pendientes de facturar y pagar, riesgo) pasa a ser
calculado, no un dato que alguien deba mantener.
"""

from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


# =========================
# CATÁLOGOS
# =========================

class Estado(models.TextChoices):
    """Estado de un ítem de checklist.

    La planilla usaba texto libre ("En revisión", "En validación operativa",
    "En ajuste", "Solicitado", "En curso"...). Todos esos matices se agrupan en
    EN_PROCESO y el texto original se conserva en ``ItemChecklist.detalle``.
    """

    PENDIENTE = "PENDIENTE", "Pendiente"
    EN_PROCESO = "EN_PROCESO", "En proceso"
    SI = "SI", "Sí"
    NO = "NO", "No"
    NO_APLICA = "NO_APLICA", "No aplica"


class Etapa(models.TextChoices):
    PROPUESTA = "PROPUESTA", "Propuesta técnica"
    RELATORIA = "RELATORIA", "Relatoría"
    PLATAFORMA = "PLATAFORMA", "Plataforma"
    COMUNICACION = "COMUNICACION", "Comunicación a participantes"
    EJECUCION = "EJECUCION", "Ejecución"
    CIERRE = "CIERRE", "Cierre"


# Etiquetas de alerta y riesgo, con la clase CSS del punto de color asociado.
# Se definen como constantes para que la vista, la plantilla y el cálculo no
# dependan de repetir el mismo literal.
ALERTA_AL_DIA = "Al día"
ALERTA_CRITICOS = "Pendientes críticos"
ALERTA_OPERATIVOS = "Pendientes operativos"
ALERTA_SIN_PROGRAMACION = "Sin programación"
ALERTA_COMERCIAL = "Seguimiento comercial"

RIESGO_SIN_ALERTA = "Sin alerta"
RIESGO_DECRETACION = "Decretación pendiente"
RIESGO_NOMINA = "Falta nómina"
RIESGO_FACTURAR = "Pendiente facturar"
RIESGO_PAGO = "Pendiente pago"

CLASES_ALERTA = {
    ALERTA_AL_DIA: "ok",
    ALERTA_CRITICOS: "danger",
    ALERTA_OPERATIVOS: "warn",
    ALERTA_SIN_PROGRAMACION: "warn",
    ALERTA_COMERCIAL: "info",
}

CLASES_RIESGO = {
    RIESGO_SIN_ALERTA: "ok",
    RIESGO_DECRETACION: "danger",
    RIESGO_NOMINA: "warn",
    RIESGO_FACTURAR: "warn",
    RIESGO_PAGO: "warn",
}

# Grupos del equipo OTEC. La carga laboral se reparte entre quienes están en
# ellos; los relatores no cuentan acá porque son quienes dictan el curso, no
# quienes lo gestionan.
GRUPO_ENCARGADO = "Encargado OTEC"
GRUPO_PROFESIONAL = "Profesional OTEC"
GRUPOS_OTEC = (GRUPO_ENCARGADO, GRUPO_PROFESIONAL)


def equipo_otec():
    """Usuarios que pertenecen a alguno de los grupos de OTEC."""
    return (
        User.objects
        .filter(groups__name__in=GRUPOS_OTEC, is_active=True)
        .distinct()
        .order_by("first_name", "last_name", "username")
    )


def rol_otec(usuario):
    """Etiqueta del rol de un usuario. Encargado manda sobre Profesional."""
    nombres = {g.name for g in usuario.groups.all()}
    if GRUPO_ENCARGADO in nombres:
        return "Encargado"
    if GRUPO_PROFESIONAL in nombres:
        return "Profesional"
    return ""


class Origen(models.TextChoices):
    """De dónde salió un registro.

    Importa porque el importador **poda** las actividades que ya no vienen en
    el Excel: sin esta marca, una actividad creada a mano desaparecería en la
    siguiente carga del archivo.
    """

    IMPORTADO = "IMPORTADO", "Importado del Excel"
    MANUAL = "MANUAL", "Creado en el sistema"


CLASES_ESTADO_ITEM = {
    Estado.SI: "ok",
    Estado.NO: "danger",
    Estado.PENDIENTE: "warn",
    Estado.EN_PROCESO: "info",
    Estado.NO_APLICA: "",
}


class Institucion(models.Model):
    class Tipo(models.TextChoices):
        PUBLICA = "PUBLICA", "Pública"
        PRIVADA = "PRIVADA", "Privada"
        INTERNA = "INTERNA", "Interna UPLA"
        PERSONA = "PERSONA", "Personas naturales"

    nombre = models.CharField(max_length=255, unique=True)
    sigla = models.CharField(max_length=50, blank=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.PUBLICA)
    rut = models.CharField(max_length=20, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "institución"
        verbose_name_plural = "instituciones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Contacto(models.Model):
    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.CASCADE,
        related_name="contactos",
    )
    nombre = models.CharField(max_length=255)
    cargo = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = "contacto"
        verbose_name_plural = "contactos"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["institucion", "nombre"],
                name="otec_contacto_unico_por_institucion",
            )
        ]

    def __str__(self):
        return f"{self.nombre} ({self.institucion.nombre})"


class Relator(models.Model):
    class Tipo(models.TextChoices):
        INTERNO = "INTERNO", "Interno"
        EXTERNO = "EXTERNO", "Externo"

    nombre = models.CharField(max_length=255, unique=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.EXTERNO)
    rut = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "relator/a"
        verbose_name_plural = "relatores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class PlantillaItem(models.Model):
    """Catálogo de ítems de checklist.

    Cada una de las ~36 columnas Sí/No/Pendiente de la planilla es una fila de
    esta tabla. Agregar o quitar un control ya no requiere una migración.
    """

    etapa = models.CharField(max_length=20, choices=Etapa.choices)
    nombre = models.CharField(max_length=255)
    orden = models.PositiveIntegerField(default=0)
    critico = models.BooleanField(
        default=False,
        help_text="Si está pendiente, la actividad se marca con alerta crítica.",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "ítem de checklist"
        verbose_name_plural = "plantilla de checklist"
        ordering = ["orden", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["etapa", "nombre"],
                name="otec_plantilla_item_unico",
            )
        ]

    def __str__(self):
        return f"{self.get_etapa_display()} · {self.nombre}"


# =========================
# PROPUESTA
# =========================

class Propuesta(models.Model):
    """Oferta a una institución. Agrupa uno o varios cursos.

    El convenio y la decretación viven acá porque son del expediente completo:
    en la planilla el memo 007/2026, el CR 10403 y el decreto 0570/2026 estaban
    copiados en las seis filas de la misma propuesta.
    """

    class Canal(models.TextChoices):
        CONVENIO = "CONVENIO", "Convenio / trato directo"
        LICITACION = "LICITACION", "Licitación"
        VENTA_DIRECTA = "VENTA_DIRECTA", "Venta directa / matrícula"
        INTERNA = "INTERNA", "Gestión interna"

    class EstadoComercial(models.TextChoices):
        EN_PREPARACION = "EN_PREPARACION", "En preparación"
        ENVIADA = "ENVIADA", "Enviada"
        EN_REVISION = "EN_REVISION", "En revisión"
        GANADA = "GANADA", "Ganada"
        PERDIDA = "PERDIDA", "Perdida"
        DESISTIDA = "DESISTIDA", "Desistida"

    class EstadoConvenio(models.TextChoices):
        NO_INICIADO = "NO_INICIADO", "No iniciado"
        EN_REVISION = "EN_REVISION", "En revisión"
        EN_TRAMITE = "EN_TRAMITE", "En trámite"
        FORMALIZADO = "FORMALIZADO", "Formalizado"

    class EstadoDecretacion(models.TextChoices):
        NO_INICIADO = "NO_INICIADO", "No iniciado"
        PENDIENTE_CONVENIO = "PENDIENTE_CONVENIO", "Pendiente recepción convenio firmado"
        PENDIENTE_INTERNA = "PENDIENTE_INTERNA", "Pendiente decretación interna"
        LISTO = "LISTO", "Listo"

    codigo = models.CharField(max_length=60, unique=True)
    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.PROTECT,
        related_name="propuestas",
    )
    contacto = models.ForeignKey(
        Contacto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="propuestas",
    )

    canal = models.CharField(max_length=20, choices=Canal.choices, default=Canal.CONVENIO)
    estado_comercial = models.CharField(
        max_length=20,
        choices=EstadoComercial.choices,
        default=EstadoComercial.EN_PREPARACION,
        db_index=True,
    )

    fecha_envio = models.DateField(null=True, blank=True)
    anio = models.PositiveIntegerField(db_index=True)

    # --- Convenio y decretación ---
    estado_convenio = models.CharField(
        max_length=20,
        choices=EstadoConvenio.choices,
        default=EstadoConvenio.NO_INICIADO,
    )
    observacion_convenio = models.CharField(max_length=500, blank=True)

    estado_decretacion = models.CharField(
        max_length=25,
        choices=EstadoDecretacion.choices,
        default=EstadoDecretacion.NO_INICIADO,
    )
    memo_decretacion = models.CharField(max_length=50, blank=True)
    fecha_memo = models.DateField(null=True, blank=True)
    cr = models.CharField(max_length=30, blank=True, verbose_name="CR")
    n_decreto = models.CharField(max_length=50, blank=True, verbose_name="N° decreto")
    fecha_resolucion = models.DateField(null=True, blank=True)

    origen = models.CharField(
        max_length=10, choices=Origen.choices, default=Origen.MANUAL, db_index=True
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "propuesta"
        verbose_name_plural = "propuestas"
        ordering = ["-anio", "codigo"]

    def __str__(self):
        return f"{self.codigo} — {self.institucion.nombre}"

    @property
    def tiempo_decreto_dias(self):
        """Días entre el memo y la resolución. Era la columna "Tiempo Decreto"."""
        if self.fecha_memo and self.fecha_resolucion:
            return (self.fecha_resolucion - self.fecha_memo).days
        return None

    @property
    def decretada(self):
        return self.estado_decretacion == self.EstadoDecretacion.LISTO

    @property
    def total_actividades(self):
        return self.actividades.count()

    @property
    def valor_ofertado_total(self):
        return self.actividades.aggregate(t=models.Sum("valor_ofertado"))["t"] or Decimal("0")

    @property
    def monto_adjudicado_total(self):
        return self.actividades.aggregate(t=models.Sum("monto_adjudicado"))["t"] or Decimal("0")


# =========================
# ACTIVIDAD
# =========================

class ActividadQuerySet(models.QuerySet):
    def del_anio(self, anio):
        return self.filter(propuesta__anio=anio)

    def ganadas(self):
        return self.filter(propuesta__estado_comercial=Propuesta.EstadoComercial.GANADA)

    def con_relaciones(self):
        return self.select_related("propuesta", "propuesta__institucion", "relator")


class Actividad(models.Model):
    """Un curso concreto dentro de una propuesta."""

    class Modalidad(models.TextChoices):
        ELEARNING = "ELEARNING", "E-learning"
        ELEARNING_ASINC = "ELEARNING_ASINC", "E-learning asincrónico"
        BLEARNING = "BLEARNING", "B-learning"
        PRESENCIAL = "PRESENCIAL", "Presencial"

    class TipoRelator(models.TextChoices):
        INTERNO = "INTERNO", "Interno"
        EXTERNO = "EXTERNO", "Externo"
        NO_DEFINIDO = "NO_DEFINIDO", "No definido"
        NO_APLICA = "NO_APLICA", "No aplica"

    class Prioridad(models.TextChoices):
        ALTA = "ALTA", "Alta"
        MEDIA = "MEDIA", "Media"
        BAJA = "BAJA", "Baja"

    class EstadoEjecucion(models.TextChoices):
        NO_PROGRAMADA = "NO_PROGRAMADA", "No programada"
        PROGRAMADA = "PROGRAMADA", "Programada"
        EN_EJECUCION = "EN_EJECUCION", "En ejecución"
        EJECUTADA = "EJECUTADA", "Ejecutada"
        SUSPENDIDA = "SUSPENDIDA", "Suspendida"

    propuesta = models.ForeignKey(
        Propuesta,
        on_delete=models.CASCADE,
        related_name="actividades",
    )
    nombre = models.CharField(max_length=500)
    modalidad = models.CharField(
        max_length=20,
        choices=Modalidad.choices,
        default=Modalidad.ELEARNING,
    )
    n_participantes = models.PositiveIntegerField(
        default=0,
        verbose_name="N° participantes comprometidos",
    )
    horas = models.PositiveIntegerField(
        default=0, verbose_name="Horas totales del curso"
    )
    # Parte de las horas totales, no horas aparte: un curso de 40 h con 16
    # asincrónicas dicta 24 h en vivo, no 56. Así lo declara el programa.
    horas_asincronicas = models.DecimalField(
        max_digits=5, decimal_places=1, default=0,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Horas asincrónicas",
        help_text="Cuántas de las horas del curso no se dictan en clase en vivo.",
    )
    # La prioridad es del curso, no del expediente: en SERPAT conviven cursos
    # de prioridad alta y media dentro de la misma propuesta.
    prioridad = models.CharField(
        max_length=10,
        choices=Prioridad.choices,
        default=Prioridad.MEDIA,
    )

    # --- Relatoría ---
    tipo_relator = models.CharField(
        max_length=20,
        choices=TipoRelator.choices,
        default=TipoRelator.NO_DEFINIDO,
    )
    relator = models.ForeignKey(
        Relator,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actividades",
    )
    fecha_confirmacion_relator = models.DateField(null=True, blank=True)

    # --- Programación ---
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_termino = models.DateField(null=True, blank=True)
    proxima_fecha_critica = models.DateField(null=True, blank=True)
    estado_ejecucion = models.CharField(
        max_length=20,
        choices=EstadoEjecucion.choices,
        default=EstadoEjecucion.NO_PROGRAMADA,
        db_index=True,
    )

    # --- Ejecución ---
    n_participantes_ejecucion = models.PositiveIntegerField(null=True, blank=True)
    n_becados = models.PositiveIntegerField(null=True, blank=True)
    n_aprobados = models.PositiveIntegerField(null=True, blank=True)

    # --- Financiero (CLP) ---
    valor_ofertado = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    # Los costos no viven acá sino en ``CostoActividad`` y ``GastoExtra``:
    # ``costo_relatoria`` y ``otros_gastos`` siguen existiendo como propiedades
    # calculadas desde ese desglose, que es la única fuente.
    monto_adjudicado = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )

    n_factura = models.CharField(max_length=50, blank=True, verbose_name="N° factura")
    fecha_factura = models.DateField(null=True, blank=True)
    monto_facturado = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    fecha_pago = models.DateField(null=True, blank=True)
    monto_pagado = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # --- Seguimiento ---
    observaciones = models.TextField(blank=True, verbose_name="Observaciones / próximo paso")
    responsables = models.ManyToManyField(
        User,
        blank=True,
        related_name="actividades_otec",
        verbose_name="Responsables OTEC",
        help_text="Quiénes del equipo OTEC llevan esta actividad.",
    )
    # Lo que viene escrito en la planilla, que a veces nombra unidades y no
    # personas ("Jurídica"). Se conserva como respaldo del dato original.
    responsable_seguimiento = models.CharField(
        max_length=255, blank=True, verbose_name="Responsable según la planilla"
    )
    actualizado_al = models.DateField(null=True, blank=True)

    origen = models.CharField(
        max_length=10, choices=Origen.choices, default=Origen.MANUAL, db_index=True
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    objects = ActividadQuerySet.as_manager()

    class Meta:
        verbose_name = "actividad"
        verbose_name_plural = "actividades"
        ordering = ["propuesta__codigo", "nombre"]

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()
        asincronicas = self.horas_asincronicas or Decimal("0")
        if asincronicas > self.horas:
            raise ValidationError({
                "horas_asincronicas": (
                    f"El curso dura {self.horas} h en total, así que no puede "
                    f"tener {asincronicas:g} h asincrónicas. Suba las horas del "
                    f"curso o baje las asincrónicas."
                )
            })

    # ---- Horas ----

    @property
    def horas_sincronicas(self):
        """Las horas del curso que sí se dictan en vivo."""
        return Decimal(self.horas) - (self.horas_asincronicas or Decimal("0"))

    def horas_programadas_por_grupo(self):
        """{grupo: horas} que suman las clases cargadas."""
        totales = {}
        for sesion in self.sesiones.all():
            totales[sesion.grupo] = (
                totales.get(sesion.grupo, Decimal("0")) + sesion.duracion_horas
            )
        return totales

    @property
    def horas_programadas(self):
        """Horas en vivo que suman las clases cargadas.

        Cuando el curso dicta dos grupos en paralelo, cada grupo repite las
        mismas horas: se toma el grupo mayor y no la suma, porque el curso
        sigue durando lo mismo.
        """
        por_grupo = self.horas_programadas_por_grupo()
        return max(por_grupo.values()) if por_grupo else Decimal("0")

    @property
    def cuadran_las_horas(self):
        """¿Las clases cargadas suman las horas en vivo comprometidas?

        None cuando todavía no se puede saber: sin horas del curso o sin
        ninguna clase cargada no hay nada contra qué comparar.
        """
        por_grupo = self.horas_programadas_por_grupo()
        if not self.horas or not por_grupo:
            return None
        return all(
            abs(horas - self.horas_sincronicas) < Decimal("0.5")
            for horas in por_grupo.values()
        )

    @property
    def horas_por_programar(self):
        """Horas en vivo que faltan por cargar. Negativo si se pasa."""
        return self.horas_sincronicas - self.horas_programadas

    @property
    def horas_asincronicas_en_gantt(self):
        """Lo marcado día a día en la carta Gantt, para contrastar."""
        return sum(
            (d.horas_asincronicas for d in self.dias.all() if d.horas_asincronicas),
            Decimal("0"),
        )

    # ---- Cálculos que en la planilla eran fórmulas ----

    @property
    def costo_relatoria(self):
        """Honorarios de relatoría. En la planilla era una columna suelta."""
        costos = getattr(self, "costos", None)
        return costos.relatoria if costos else Decimal("0")

    @property
    def otros_gastos(self):
        """Todo lo que no es relatoría, incluidos los gastos extras.

        La planilla lo traía como un total sin detalle; acá es la suma de las
        categorías del desglose más las líneas libres.
        """
        costos = getattr(self, "costos", None)
        base = costos.total_sin_relatoria if costos else Decimal("0")
        return base + self.total_gastos_extra

    @property
    def total_gastos_extra(self):
        return sum((g.monto for g in self.gastos_extra.all()), Decimal("0"))

    @property
    def costo_total(self):
        return self.costo_relatoria + self.otros_gastos

    def desglose_costos(self):
        """[(etiqueta, monto)] con las categorías que tienen monto y los extras.

        Para mostrar el desglose sin repetir en el template la lista de
        categorías ni el orden.
        """
        costos = getattr(self, "costos", None)
        lineas = costos.por_categoria() if costos else []
        lineas += [
            {"campo": "extra", "label": g.descripcion or "Gasto extra", "monto": g.monto}
            for g in self.gastos_extra.all()
        ]
        return lineas

    @property
    def excedente_estimado(self):
        return self.valor_ofertado - self.costo_total

    @property
    def margen_estimado(self):
        """Excedente sobre el valor ofertado, en fracción (0–1)."""
        if not self.valor_ofertado:
            return None
        return self.excedente_estimado / self.valor_ofertado

    @property
    def margen_estimado_pct(self):
        margen = self.margen_estimado
        return None if margen is None else round(margen * 100)

    @property
    def pendiente_facturar(self):
        return self.monto_adjudicado - self.monto_facturado

    @property
    def pendiente_pago(self):
        return self.monto_facturado - self.monto_pagado

    @property
    def facturado(self):
        return self.monto_facturado > 0

    @property
    def pagado(self):
        return self.monto_pagado > 0 and self.pendiente_pago <= 0

    @property
    def duracion_dias(self):
        if self.fecha_inicio and self.fecha_termino:
            return (self.fecha_termino - self.fecha_inicio).days
        return None

    # ---- Checklist ----

    def _items_evaluables(self):
        """Ítems que cuentan para el avance: los que no son "No aplica"."""
        return [i for i in self.items.all() if i.estado != Estado.NO_APLICA]

    @property
    def avance_checklist(self):
        """Fracción 0–1 de ítems completados sobre los que aplican.

        La planilla devolvía #DIV/0! cuando no aplicaba ninguno; acá es None.
        """
        evaluables = self._items_evaluables()
        if not evaluables:
            return None
        completados = sum(1 for i in evaluables if i.estado == Estado.SI)
        return completados / len(evaluables)

    @property
    def avance_checklist_pct(self):
        avance = self.avance_checklist
        return None if avance is None else round(avance * 100)

    def avance_por_etapa(self):
        """[(etapa, label, completados, total, pct), ...] para la vista de detalle."""
        resumen = []
        for etapa, label in Etapa.choices:
            evaluables = [
                i for i in self.items.all()
                if i.plantilla.etapa == etapa and i.estado != Estado.NO_APLICA
            ]
            if not evaluables:
                continue
            completados = sum(1 for i in evaluables if i.estado == Estado.SI)
            resumen.append({
                "etapa": etapa,
                "label": label,
                "completados": completados,
                "total": len(evaluables),
                "pct": round(completados * 100 / len(evaluables)),
            })
        return resumen

    @property
    def pendientes_criticos(self):
        return [
            i for i in self.items.all()
            if i.plantilla.critico and i.estado in (Estado.PENDIENTE, Estado.NO, Estado.EN_PROCESO)
        ]

    @property
    def alerta_checklist(self):
        """Reemplaza la columna "Alerta checklist" de la planilla."""
        if self.propuesta.estado_comercial != Propuesta.EstadoComercial.GANADA:
            return ALERTA_COMERCIAL
        if not self.fecha_inicio:
            return ALERTA_SIN_PROGRAMACION
        if self.pendientes_criticos:
            return ALERTA_CRITICOS
        if any(i.estado != Estado.SI for i in self._items_evaluables()):
            return ALERTA_OPERATIVOS
        return ALERTA_AL_DIA

    @property
    def alerta_clase(self):
        return CLASES_ALERTA.get(self.alerta_checklist, "")

    @property
    def riesgo_ejecutivo(self):
        """Reemplaza la columna "Riesgo Ejecutivo" de la planilla.

        Mientras la propuesta no está ganada no hay nada que decretar ni
        facturar, así que no se reporta riesgo operativo: el seguimiento que
        corresponde es comercial y lo indica ``alerta_checklist``.
        """
        if self.propuesta.estado_comercial != Propuesta.EstadoComercial.GANADA:
            return RIESGO_SIN_ALERTA
        if not self.propuesta.decretada:
            return RIESGO_DECRETACION
        nomina = next(
            (i for i in self.items.all() if i.plantilla.nombre.startswith("Recepción nómina")),
            None,
        )
        if nomina is not None and nomina.estado not in (Estado.SI, Estado.NO_APLICA):
            return RIESGO_NOMINA
        if self.monto_adjudicado > 0 and self.pendiente_facturar > 0:
            return RIESGO_FACTURAR
        if self.pendiente_pago > 0:
            return RIESGO_PAGO
        return RIESGO_SIN_ALERTA

    @property
    def riesgo_clase(self):
        return CLASES_RIESGO.get(self.riesgo_ejecutivo, "")

    def sincronizar_checklist(self):
        """Crea los ítems que falten según la plantilla activa.

        Se llama al crear la actividad y es idempotente, así que también sirve
        cuando se agrega un control nuevo al catálogo.
        """
        existentes = set(self.items.values_list("plantilla_id", flat=True))
        nuevos = [
            ItemChecklist(actividad=self, plantilla=p)
            for p in PlantillaItem.objects.filter(activo=True).exclude(id__in=existentes)
        ]
        if nuevos:
            ItemChecklist.objects.bulk_create(nuevos)
        return len(nuevos)


class CostoActividad(models.Model):
    """Desglose de los costos de un curso, por categoría.

    Reemplaza los dos casilleros que traía la planilla — "Costo Relatoría" y
    "Otros gastos" —, que eran totales sin detalle: no se podía saber cuánto de
    "otros gastos" era material y cuánto traslado. Las categorías son las
    mismas de ``CostoDirecto``, para que un costo signifique lo mismo acá y en
    el flujo de caja.
    """

    CATEGORIAS = [
        ("relatoria", "Honorarios de relatoría"),
        ("materiales", "Materiales e insumos"),
        ("plataformas", "Plataformas o licencias"),
        ("certificaciones", "Certificaciones"),
        ("traslados", "Traslados y viáticos"),
        ("alimentacion", "Alimentación"),
        ("arriendo", "Arriendo o equipamiento"),
        ("otros", "Otros costos"),
    ]

    actividad = models.OneToOneField(
        Actividad, on_delete=models.CASCADE, related_name="costos"
    )
    relatoria = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    materiales = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    plataformas = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    certificaciones = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    traslados = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    alimentacion = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    arriendo = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    otros = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    editado_en_sistema = models.BooleanField(
        default=False,
        help_text=(
            "Marcado cuando alguien detalló los costos desde la aplicación. "
            "La importación del Excel respeta ese desglose salvo que se pida "
            "sobrescribirlo: la planilla solo trae dos totales y volcarlos "
            "encima borraría el detalle."
        ),
    )

    class Meta:
        verbose_name = "costos de la actividad"
        verbose_name_plural = "costos de las actividades"

    def __str__(self):
        return f"Costos de {self.actividad.nombre[:40]}"

    @property
    def total(self):
        return sum((getattr(self, campo) for campo, _ in self.CATEGORIAS), Decimal("0"))

    @property
    def total_sin_relatoria(self):
        return self.total - self.relatoria

    def por_categoria(self):
        return [
            {"campo": campo, "label": label, "monto": getattr(self, campo)}
            for campo, label in self.CATEGORIAS
            if getattr(self, campo)
        ]


class GastoExtra(models.Model):
    """Un gasto del curso que no calza en ninguna categoría fija.

    Existe para no obligar a meter en "Otros costos" cosas que sí tienen
    nombre: cada línea lleva su glosa, así que el total se puede explicar.
    """

    actividad = models.ForeignKey(
        Actividad, on_delete=models.CASCADE, related_name="gastos_extra"
    )
    descripcion = models.CharField(max_length=200, verbose_name="Glosa del gasto")
    monto = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        verbose_name = "gasto extra"
        verbose_name_plural = "gastos extras"
        ordering = ["id"]

    def __str__(self):
        return f"{self.descripcion} — ${self.monto:,.0f}"


class MetaAnual(models.Model):
    """Meta financiera del año. En la planilla vivía suelta en el Dashboard."""

    anio = models.PositiveIntegerField(unique=True)
    monto = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        verbose_name = "meta anual"
        verbose_name_plural = "metas anuales"
        ordering = ["-anio"]

    def __str__(self):
        return f"Meta {self.anio}: ${self.monto:,.0f}"


class SupuestosFinancieros(models.Model):
    """Parámetros del modelo de flujo de caja de un año.

    Vienen de la hoja ``Parámetros`` del flujo. Al estar acá, el sistema puede
    **recalcular** el flujo en vez de copiar los números ya calculados.
    """

    anio = models.PositiveIntegerField(unique=True)
    saldo_inicial = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    fecha_corte = models.DateField(
        null=True, blank=True,
        help_text="Desde este mes se proyecta la caja; antes solo se registra lo ocurrido.",
    )
    valor_hora_relatoria = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    pct_upla = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0.15"),
        verbose_name="% de distribución UPLA",
    )
    pct_otec = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0.15"),
        verbose_name="% de distribución OTEC",
    )
    pct_autoaprendizaje = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0.50"),
        help_text="Los cursos de autoaprendizaje se reparten mitad y mitad.",
    )

    plazo_pago_costos_dias = models.PositiveIntegerField(default=40)
    saldo_minimo = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        verbose_name = "supuestos financieros"
        verbose_name_plural = "supuestos financieros"
        ordering = ["-anio"]

    def __str__(self):
        return f"Supuestos {self.anio}"


class LineaFinanciera(models.Model):
    """Una línea de ingreso del flujo de caja.

    No es lo mismo que una ``Actividad``: el flujo desagrega por mes de
    facturación (ocho líneas de autoaprendizaje para un solo curso) e incluye
    **cartera proyectada** que todavía no es un curso — licitaciones que se
    espera adjudicar, ventas por franquicia tributaria. Por eso vive aparte y
    se enlaza a la actividad solo cuando corresponde.
    """

    class Certeza(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        CONFIRMADO = "CONFIRMADO", "Confirmado"
        PROBABLE = "PROBABLE", "Probable"
        PROYECTADO = "PROYECTADO", "Proyectado"

    class EstadoLinea(models.TextChoices):
        EJECUTADA = "EJECUTADA", "Ejecutada"
        CONTRATADA = "CONTRATADA", "Contratada"
        ADJUDICADA = "ADJUDICADA", "Adjudicada"
        EN_NEGOCIACION = "EN_NEGOCIACION", "En negociación"
        PROYECTADA = "PROYECTADA", "Proyectada"

    codigo = models.CharField(max_length=40, unique=True)
    institucion = models.ForeignKey(
        Institucion, on_delete=models.PROTECT, related_name="lineas_financieras"
    )
    actividad = models.ForeignKey(
        Actividad,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="lineas_financieras",
        help_text="Vacío en la cartera proyectada, que aún no es un curso.",
    )
    descripcion = models.CharField(max_length=300, verbose_name="Curso o servicio")

    estado = models.CharField(
        max_length=20, choices=EstadoLinea.choices, default=EstadoLinea.PROYECTADA
    )
    certeza = models.CharField(
        max_length=15, choices=Certeza.choices, default=Certeza.PROYECTADO, db_index=True
    )
    autoaprendizaje = models.BooleanField(
        default=False,
        help_text="Cambia el reparto a mitad y mitad en vez de 15/15.",
    )

    participantes = models.PositiveIntegerField(default=0)
    horas = models.PositiveIntegerField(default=0)

    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_termino = models.DateField(null=True, blank=True)
    fecha_facturacion = models.DateField(null=True, blank=True)
    fecha_pago_estimada = models.DateField(null=True, blank=True)
    fecha_pago_efectiva = models.DateField(null=True, blank=True)

    valor_ofertado = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    monto_contratado = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    monto_facturado = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    monto_pagado = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    origen = models.CharField(max_length=200, blank=True)
    observacion = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = "línea financiera"
        verbose_name_plural = "líneas financieras"
        ordering = ["fecha_pago_estimada", "codigo"]

    def __str__(self):
        return f"{self.codigo} — {self.descripcion[:40]}"

    @property
    def es_proyeccion(self):
        return self.certeza in (self.Certeza.PROBABLE, self.Certeza.PROYECTADO)

    @property
    def ingreso_considerado(self):
        """Lo que el flujo cuenta como ingreso de esta línea."""
        return self.monto_contratado or self.valor_ofertado

    @property
    def fecha_ingreso(self):
        """Cuándo entra la plata: el pago efectivo manda sobre el estimado."""
        return self.fecha_pago_efectiva or self.fecha_pago_estimada


class CostoDirecto(models.Model):
    """Costos atribuibles a una línea, en las ocho categorías de la planilla."""

    linea = models.OneToOneField(
        LineaFinanciera, on_delete=models.CASCADE, related_name="costo"
    )
    relatoria = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    materiales = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    plataformas = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    certificaciones = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    traslados = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    alimentacion = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    arriendo = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    otros = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    fecha_pago_estimada = models.DateField(null=True, blank=True)
    fecha_pago_efectiva = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=40, blank=True)
    observacion = models.CharField(max_length=500, blank=True)

    CATEGORIAS = [
        ("relatoria", "Relatoría"),
        ("materiales", "Materiales e insumos"),
        ("plataformas", "Plataformas o licencias"),
        ("certificaciones", "Certificaciones"),
        ("traslados", "Traslados y viáticos"),
        ("alimentacion", "Alimentación"),
        ("arriendo", "Arriendo o equipamiento"),
        ("otros", "Otros costos directos"),
    ]

    class Meta:
        verbose_name = "costo directo"
        verbose_name_plural = "costos directos"

    def __str__(self):
        return f"Costos de {self.linea.codigo}"

    @property
    def total(self):
        return sum(getattr(self, campo) for campo, _ in self.CATEGORIAS)

    @property
    def fecha_egreso(self):
        return self.fecha_pago_efectiva or self.fecha_pago_estimada

    def por_categoria(self):
        return [
            {"campo": campo, "label": label, "monto": getattr(self, campo)}
            for campo, label in self.CATEGORIAS
            if getattr(self, campo)
        ]


class CostoTransversal(models.Model):
    """Costo que no es de una actividad concreta: personal, auditoría, gastos."""

    codigo = models.CharField(max_length=40, unique=True)
    tipo = models.CharField(max_length=60, blank=True)
    descripcion = models.CharField(max_length=300)
    area = models.CharField(max_length=120, blank=True)
    monto = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    fecha_pago = models.DateField(null=True, blank=True)
    criterio = models.CharField(max_length=120, blank=True)
    incluir_en_flujo = models.BooleanField(default=True)
    fuente_financiamiento = models.CharField(max_length=120, blank=True)
    observacion = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = "costo transversal"
        verbose_name_plural = "costos transversales"
        ordering = ["fecha_pago", "codigo"]

    def __str__(self):
        return f"{self.codigo} — {self.descripcion[:40]}"


class DiaActividad(models.Model):
    """Un día marcado de una actividad en la carta Gantt.

    Reemplaza la grilla de la hoja ``Carta Gantt``, donde cada columna era un
    día hábil y la celda llevaba "E" (ejecución) o "C" (cierre administrativo).
    """

    class Tipo(models.TextChoices):
        EJECUCION = "E", "Ejecución"
        CIERRE = "C", "Cierre administrativo"

    actividad = models.ForeignKey(
        Actividad,
        on_delete=models.CASCADE,
        related_name="dias",
    )
    fecha = models.DateField(db_index=True)
    tipo = models.CharField(max_length=1, choices=Tipo.choices, default=Tipo.EJECUCION)
    horas_asincronicas = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Horas asincrónicas del día, si las hubo.",
    )

    class Meta:
        verbose_name = "día de actividad"
        verbose_name_plural = "días de actividad (Gantt)"
        ordering = ["fecha"]
        constraints = [
            models.UniqueConstraint(
                fields=["actividad", "fecha"],
                name="otec_dia_unico_por_actividad",
            )
        ]

    def __str__(self):
        return f"{self.actividad.nombre[:40]} · {self.fecha} ({self.get_tipo_display()})"


class SalaZoom(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    orden = models.PositiveIntegerField(default=0)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "sala Zoom"
        verbose_name_plural = "salas Zoom"
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class Feriado(models.Model):
    """Día sin actividad. En la planilla se marcaba "FESTIVO" en la grilla."""

    fecha = models.DateField(unique=True)
    nombre = models.CharField(max_length=120, blank=True)

    class Meta:
        verbose_name = "feriado"
        verbose_name_plural = "feriados"
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.fecha} {self.nombre}".strip()


class SesionClase(models.Model):
    """Una clase en vivo, con la fecha y la hora que de verdad tiene.

    Antes esto era una **regla semanal** ("martes 13:30, 3 h") y las sesiones
    se calculaban al dibujar. No servía: las fechas las pone el relator y casi
    nunca caen todas el mismo día de la semana — "este lunes 10 a las 14:00,
    martes 11 a las 13:00, lunes 17 a las 20:00". Con una regla, un curso así
    o quedaba mal programado o directamente no se podía cargar.

    Guardar cada clase tiene dos consecuencias que la regla no daba: el día
    queda marcado solo en la carta Gantt, y el choque de sala se puede detectar
    contra una fecha concreta y no contra un patrón.
    """

    actividad = models.ForeignKey(
        Actividad, on_delete=models.CASCADE, related_name="sesiones"
    )
    fecha = models.DateField(db_index=True)
    hora_inicio = models.TimeField()
    duracion_horas = models.DecimalField(
        max_digits=4, decimal_places=1, default=Decimal("2.0"),
        validators=[MinValueValidator(Decimal("0.5"))],
        verbose_name="Duración (horas)",
    )
    sala = models.ForeignKey(
        SalaZoom,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="sesiones",
        help_text="Vacío si la clase no ocupa una sala Zoom.",
    )
    grupo = models.CharField(
        max_length=40, blank=True,
        help_text="Solo si el curso dicta más de un grupo en paralelo, p. ej. «AP».",
    )

    class Meta:
        verbose_name = "sesión de clases"
        verbose_name_plural = "sesiones de clases"
        ordering = ["fecha", "hora_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["actividad", "fecha", "hora_inicio", "grupo"],
                name="otec_sesion_unica_por_actividad",
            )
        ]

    def __str__(self):
        return f"{self.fecha} {self.hora_inicio:%H:%M}–{self.hora_fin:%H:%M}"

    # ---- horas ----

    @property
    def hora_fin(self):
        minutos = (
            self.hora_inicio.hour * 60
            + self.hora_inicio.minute
            + int(self.duracion_horas * 60)
        )
        return time(min(minutos // 60, 23), minutos % 60)

    # ---- choques de sala ----

    def choca_con(self, otra):
        """¿Ocupan la misma sala, el mismo día, en horas que se pisan?"""
        if not self.sala_id or self.sala_id != otra.sala_id:
            return False
        if self.fecha != otra.fecha:
            return False
        return self._se_pisa_con(otra.hora_inicio, otra.hora_fin)

    def _se_pisa_con(self, inicio, fin):
        if not (inicio and fin):
            return False
        return self.hora_inicio < fin and inicio < self.hora_fin

    def choques(self):
        """Lo que ya ocupa esta sala en esa franja.

        Mira las **dos** fuentes que llenan una sala: las clases cargadas acá y
        las reservas que trajo el Tablero. Con solo las primeras el aviso no
        servía de nada — casi toda la ocupación real de las salas viene de las
        reservas, no de las clases del sistema.

        Devuelve dicts y no objetos porque las dos fuentes son modelos
        distintos y a quien pregunta solo le interesa quién ocupa y hasta qué
        hora.
        """
        if not (self.sala_id and self.hora_inicio):
            return []

        ocupantes = []
        clases = (
            SesionClase.objects
            .filter(fecha=self.fecha, sala_id=self.sala_id)
            .exclude(pk=self.pk)
            .select_related("actividad")
        )
        for otra in clases:
            if self._se_pisa_con(otra.hora_inicio, otra.hora_fin):
                ocupantes.append({
                    "nombre": otra.actividad.nombre,
                    "hora_inicio": otra.hora_inicio,
                    "hora_fin": otra.hora_fin,
                    "es_reserva": False,
                })

        reservas = (
            ReservaZoom.objects
            .filter(fecha=self.fecha, sala_id=self.sala_id)
            .exclude(hora_inicio=None)
            .select_related("actividad")
        )
        for reserva in reservas:
            # La reserva del propio curso no es un choque consigo mismo: suele
            # ser esta misma clase, tal como venía en el Tablero.
            if reserva.actividad_id and reserva.actividad_id == self.actividad_id:
                continue
            if self._se_pisa_con(reserva.hora_inicio, reserva.hora_fin):
                ocupantes.append({
                    "nombre": (
                        reserva.actividad.nombre if reserva.actividad
                        else reserva.etiqueta
                    ),
                    "hora_inicio": reserva.hora_inicio,
                    "hora_fin": reserva.hora_fin,
                    "es_reserva": True,
                })
        return ocupantes

    def clean(self):
        super().clean()
        ocupantes = self.choques()
        if ocupantes:
            otro = ocupantes[0]
            origen = "reservada en el Tablero para" if otro["es_reserva"] else "la tiene"
            raise ValidationError({
                "sala": (
                    f"{self.sala.nombre} está {origen} «{otro['nombre'][:60]}» "
                    f"de {otro['hora_inicio']:%H:%M} a {otro['hora_fin']:%H:%M} "
                    f"ese día. Cambie la sala o la hora."
                )
            })

    # ---- carta Gantt ----
    #
    # La clase es el hecho y el día de la Gantt su consecuencia, así que se
    # marca sola. Antes había que anotar el día por separado y las dos
    # pantallas terminaban contando cosas distintas.

    @classmethod
    def from_db(cls, db, field_names, values):
        # Se recuerda con qué fecha venía para poder soltar ese día de la Gantt
        # si la clase se mueve a otro.
        instancia = super().from_db(db, field_names, values)
        instancia._fecha_anterior = instancia.fecha
        return instancia

    def save(self, *args, **kwargs):
        anterior = getattr(self, "_fecha_anterior", None)
        super().save(*args, **kwargs)
        DiaActividad.objects.get_or_create(
            actividad_id=self.actividad_id,
            fecha=self.fecha,
            defaults={"tipo": DiaActividad.Tipo.EJECUCION},
        )
        if anterior and anterior != self.fecha:
            limpiar_dia_sin_clases(self.actividad_id, anterior)
        self._fecha_anterior = self.fecha

    def delete(self, *args, **kwargs):
        actividad_id, fecha = self.actividad_id, self.fecha
        resultado = super().delete(*args, **kwargs)
        limpiar_dia_sin_clases(actividad_id, fecha)
        return resultado


def limpiar_dia_sin_clases(actividad_id, fecha):
    """Borra el día de la Gantt si ya no queda nada que lo justifique.

    Solo se lleva los días que quedaron vacíos: si alguien anotó horas
    asincrónicas o lo marcó como cierre administrativo, el día tiene sentido
    propio y se queda.
    """
    if SesionClase.objects.filter(actividad_id=actividad_id, fecha=fecha).exists():
        return
    (
        DiaActividad.objects
        .filter(
            actividad_id=actividad_id,
            fecha=fecha,
            tipo=DiaActividad.Tipo.EJECUCION,
            horas_asincronicas__isnull=True,
        )
        .delete()
    )


class ReservaZoom(models.Model):
    """Bloque de una sala Zoom tomado por una actividad.

    En la planilla cada media hora era una celda; acá los bloques contiguos de
    una misma actividad se guardan como una sola reserva (09:30–12:30 en vez de
    seis filas).
    """

    sala = models.ForeignKey(
        SalaZoom,
        on_delete=models.CASCADE,
        related_name="reservas",
    )
    fecha = models.DateField(db_index=True)
    hora_inicio = models.TimeField(null=True, blank=True)
    hora_fin = models.TimeField(null=True, blank=True)

    actividad = models.ForeignKey(
        Actividad,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reservas_zoom",
        help_text="Vacío para usos que no corresponden a un curso del registro.",
    )
    etiqueta = models.CharField(
        max_length=120,
        help_text="Código tal como aparecía en la planilla, p. ej. \"FORM (S.AP)\".",
    )
    soporte = models.CharField(
        max_length=60,
        blank=True,
        help_text="Iniciales de quien da soporte, del paréntesis del código.",
    )
    observacion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "reserva de Zoom"
        verbose_name_plural = "reservas de Zoom"
        ordering = ["fecha", "hora_inicio", "sala__orden"]
        constraints = [
            models.UniqueConstraint(
                fields=["sala", "fecha", "hora_inicio"],
                name="otec_reserva_unica_por_bloque",
            )
        ]

    def __str__(self):
        if self.hora_inicio and self.hora_fin:
            return f"{self.sala.nombre} {self.fecha} {self.hora_inicio:%H:%M}-{self.hora_fin:%H:%M}"
        return f"{self.sala.nombre} {self.fecha} (sin bloque)"

    @property
    def duracion_horas(self):
        if not (self.hora_inicio and self.hora_fin):
            return None
        inicio = self.hora_inicio.hour * 60 + self.hora_inicio.minute
        fin = self.hora_fin.hour * 60 + self.hora_fin.minute
        return (fin - inicio) / 60


class ItemChecklist(models.Model):
    """Estado de un control de la plantilla para una actividad concreta."""

    actividad = models.ForeignKey(
        Actividad,
        on_delete=models.CASCADE,
        related_name="items",
    )
    plantilla = models.ForeignKey(
        PlantillaItem,
        on_delete=models.CASCADE,
        related_name="items",
    )
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )
    detalle = models.CharField(
        max_length=255,
        blank=True,
        help_text="Matiz del estado, p. ej. \"En validación operativa\".",
    )
    fecha = models.DateField(null=True, blank=True)
    editado_en_sistema = models.BooleanField(
        default=False,
        help_text=(
            "Marcado cuando alguien cambió el estado desde la aplicación. "
            "La importación del Excel respeta estos ítems salvo que se pida "
            "sobrescribirlos."
        ),
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ítem de actividad"
        verbose_name_plural = "ítems de actividad"
        ordering = ["plantilla__orden", "plantilla__id"]
        constraints = [
            models.UniqueConstraint(
                fields=["actividad", "plantilla"],
                name="otec_item_unico_por_actividad",
            )
        ]

    def __str__(self):
        return f"{self.plantilla.nombre}: {self.get_estado_display()}"

    @property
    def completado(self):
        return self.estado == Estado.SI

    @property
    def clase(self):
        return CLASES_ESTADO_ITEM.get(self.estado, "")

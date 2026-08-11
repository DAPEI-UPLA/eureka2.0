from django.contrib import admin

from .models import (
    Actividad,
    Contacto,
    CostoActividad,
    CostoDirecto,
    CostoTransversal,
    DiaActividad,
    Feriado,
    GastoExtra,
    LineaFinanciera,
    SupuestosFinancieros,
    Institucion,
    ItemChecklist,
    MetaAnual,
    PlantillaItem,
    Propuesta,
    Relator,
    ReservaZoom,
    SalaZoom,
    SesionClase,
)


class ContactoInline(admin.TabularInline):
    model = Contacto
    extra = 0


@admin.register(Institucion)
class InstitucionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "sigla", "tipo", "activa")
    list_filter = ("tipo", "activa")
    search_fields = ("nombre", "sigla", "rut")
    inlines = [ContactoInline]


@admin.register(Relator)
class RelatorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "email", "activo")
    list_filter = ("tipo", "activo")
    search_fields = ("nombre", "rut", "email")


@admin.register(PlantillaItem)
class PlantillaItemAdmin(admin.ModelAdmin):
    list_display = ("orden", "etapa", "nombre", "critico", "activo")
    list_filter = ("etapa", "critico", "activo")
    search_fields = ("nombre",)
    ordering = ("orden",)


class ActividadInline(admin.TabularInline):
    model = Actividad
    extra = 0
    fields = ("nombre", "modalidad", "horas", "n_participantes", "estado_ejecucion", "valor_ofertado")
    show_change_link = True


@admin.register(Propuesta)
class PropuestaAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "institucion",
        "estado_comercial",
        "estado_decretacion",
        "anio",
        "fecha_envio",
    )
    list_filter = ("estado_comercial", "estado_decretacion", "canal", "anio")
    search_fields = ("codigo", "institucion__nombre", "memo_decretacion", "n_decreto")
    autocomplete_fields = ("institucion",)
    inlines = [ActividadInline]


class SesionClaseInline(admin.TabularInline):
    model = SesionClase
    extra = 0


class ItemChecklistInline(admin.TabularInline):
    model = ItemChecklist
    extra = 0
    fields = ("plantilla", "estado", "detalle", "fecha")
    readonly_fields = ("plantilla",)
    can_delete = False


class CostoActividadInline(admin.StackedInline):
    model = CostoActividad
    extra = 0


class GastoExtraInline(admin.TabularInline):
    model = GastoExtra
    extra = 0


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    search_fields = ("nombre", "propuesta__codigo", "propuesta__institucion__nombre")
    list_display = (
        "nombre",
        "propuesta",
        "modalidad",
        "estado_ejecucion",
        "fecha_inicio",
        "relator",
        "horas",
        "valor_ofertado",
    )
    list_filter = (
        "estado_ejecucion", "modalidad", "prioridad", "tipo_relator",
        "propuesta__estado_comercial",
    )
    search_fields = ("nombre", "propuesta__codigo", "propuesta__institucion__nombre")
    autocomplete_fields = ("propuesta", "relator")
    filter_horizontal = ("responsables",)
    date_hierarchy = "fecha_inicio"
    inlines = [SesionClaseInline, CostoActividadInline, GastoExtraInline, ItemChecklistInline]


@admin.register(SupuestosFinancieros)
class SupuestosFinancierosAdmin(admin.ModelAdmin):
    list_display = ("anio", "saldo_inicial", "fecha_corte", "pct_upla",
                    "pct_otec", "pct_autoaprendizaje", "saldo_minimo")


class CostoDirectoInline(admin.StackedInline):
    model = CostoDirecto
    extra = 0


@admin.register(LineaFinanciera)
class LineaFinancieraAdmin(admin.ModelAdmin):
    list_display = ("codigo", "institucion", "descripcion", "certeza", "estado",
                    "monto_contratado", "fecha_pago_estimada", "actividad")
    list_filter = ("certeza", "estado", "autoaprendizaje", "institucion")
    search_fields = ("codigo", "descripcion", "institucion__nombre")
    autocomplete_fields = ("institucion", "actividad")
    inlines = [CostoDirectoInline]
    date_hierarchy = "fecha_pago_estimada"


@admin.register(CostoTransversal)
class CostoTransversalAdmin(admin.ModelAdmin):
    list_display = ("codigo", "tipo", "descripcion", "monto", "fecha_pago", "incluir_en_flujo")
    list_filter = ("tipo", "incluir_en_flujo")
    search_fields = ("codigo", "descripcion")
    date_hierarchy = "fecha_pago"


@admin.register(MetaAnual)
class MetaAnualAdmin(admin.ModelAdmin):
    list_display = ("anio", "monto")
    ordering = ("-anio",)


@admin.register(SalaZoom)
class SalaZoomAdmin(admin.ModelAdmin):
    list_display = ("nombre", "orden", "activa")
    list_editable = ("orden", "activa")
    search_fields = ("nombre",)


@admin.register(Feriado)
class FeriadoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "nombre")
    search_fields = ("nombre",)
    ordering = ("fecha",)


@admin.register(DiaActividad)
class DiaActividadAdmin(admin.ModelAdmin):
    list_display = ("fecha", "actividad", "tipo", "horas_asincronicas")
    list_filter = ("tipo", "fecha")
    search_fields = ("actividad__nombre",)
    autocomplete_fields = ("actividad",)
    date_hierarchy = "fecha"


@admin.register(ReservaZoom)
class ReservaZoomAdmin(admin.ModelAdmin):
    list_display = ("fecha", "sala", "hora_inicio", "hora_fin", "etiqueta", "actividad", "soporte")
    list_filter = ("sala", "fecha")
    search_fields = ("etiqueta", "actividad__nombre", "soporte")
    autocomplete_fields = ("actividad", "sala")
    date_hierarchy = "fecha"

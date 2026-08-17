from django.contrib import admin
from .models import (
    Actividad,
    Egreso,
    Gasto,
    GastoElegible,
    PlanDeGasto,
    PresupuestoAnual,
    Proyecto,
    TipoGasto,
    Transferencia,
    Unidad,
)


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):

    list_display = (
        'nombre',
        'tipo',
        'estado',
        'prioridad',
        'responsable',
        'presupuesto_total',
        'presupuesto_disponible_real',
        'eliminado',
        'fecha_creacion',
    )

    list_filter = (
        'tipo',
        'estado',
        'prioridad',
        'eliminado',
        'fecha_creacion',
    )

    search_fields = (
        'nombre',
        'codigo',
        'descripcion',
    )

    ordering = ('-fecha_creacion',)

    autocomplete_fields = ('responsable', 'creado_por')

    readonly_fields = (
        'fecha_creacion',
        'actualizado_en',
        'presupuesto_disponible_real',
        'creado_por',
        'actualizado_por',
    )

    fieldsets = (
        ("Información General", {
            "fields": ('nombre', 'codigo', 'descripcion', 'tipo'),
        }),
        ("Gestión", {
            "fields": (
                'responsable',
                'creado_por',
                'actualizado_por',
                'duracion_meses',
                'estado',
                'prioridad',
                'eliminado',
            ),
        }),
        ("Fechas", {
            "fields": ('fecha_inicio', 'fecha_fin', 'fecha_creacion', 'actualizado_en'),
        }),
        ("Presupuesto (CLP)", {
            "fields": ('presupuesto_total', 'presupuesto_disponible_real'),
        }),
    )

    def get_queryset(self, request):
        return Proyecto.all_objects.all()

    def save_model(self, request, obj, form, change):
        if not obj.creado_por:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)



# =========================
# INLINE GASTO ELEGIBLE
# =========================
class GastoElegibleInline(admin.TabularInline):
    model = GastoElegible
    extra = 1


# =========================
# INLINE GASTO
# =========================
class GastoInline(admin.TabularInline):
    model = Gasto
    extra = 1


# =========================
# INLINE TIPO GASTO
# =========================
class TipoGastoInline(admin.TabularInline):
    model = TipoGasto
    extra = 1


# =========================
# TRANSFERENCIA
# =========================
@admin.register(Transferencia)
class TransferenciaAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "naturaleza", "creado_por", "creado_en")
    list_filter = ("naturaleza",)
    search_fields = ("nombre",)

    inlines = [TipoGastoInline]


# =========================
# TIPO GASTO
# =========================
@admin.register(TipoGasto)
class TipoGastoAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "transferencia")
    list_filter = ("transferencia",)
    search_fields = ("nombre",)

    inlines = [GastoInline]


# =========================
# GASTO
# =========================
@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "tipo_gasto")
    list_filter = ("tipo_gasto",)
    search_fields = ("nombre",)

    inlines = [GastoElegibleInline]


# =========================
# GASTO ELEGIBLE
# =========================
@admin.register(GastoElegible)
class GastoElegibleAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "gasto")
    list_filter = ("gasto",)
    search_fields = ("nombre",)


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "resultado", "presupuesto", "fecha_limite")
    search_fields = ("nombre", "resultado__descripcion")
    list_filter = ("resultado__objetivo__proyecto",)


@admin.register(Unidad)
class UnidadAdmin(admin.ModelAdmin):
    list_display = ("id", "codigo", "nombre")
    search_fields = ("nombre", "codigo")
    ordering = ("nombre",)


@admin.register(PlanDeGasto)
class PlanDeGastoAdmin(admin.ModelAdmin):
    list_display = (
        "id", "anio", "actividad", "gasto_elegible",
        "unidad_responsable", "monto", "creado_en",
    )
    list_filter = ("anio", "unidad_responsable")
    search_fields = (
        "actividad__nombre",
        "gasto_elegible__nombre",
        "unidad_responsable__nombre",
    )
    autocomplete_fields = ("actividad", "gasto_elegible", "unidad_responsable")
    readonly_fields = ("creado_en",)


@admin.register(Egreso)
class EgresoAdmin(admin.ModelAdmin):
    list_display = (
        "id", "proyecto", "estado", "tipo", "subtipo_compra",
        "centro_responsabilidad", "gasto_elegible",
        "solicitud_compra", "orden_compra", "factura",
        "cantidad", "valor_sin_iva", "total_sin_iva", "fecha",
    )
    list_filter = ("estado", "tipo", "subtipo_compra", "proyecto", "fecha", "eliminado")
    search_fields = (
        "proyecto__nombre",
        "centro_responsabilidad",
        "gasto__nombre",
        "gasto_elegible__nombre",
        "solicitud_compra",
        "orden_compra",
        "factura",
    )
    autocomplete_fields = ("proyecto",)
    readonly_fields = ("creado_en", "actualizado_en", "creado_por", "actualizado_por")

    def get_queryset(self, request):
        return Egreso.all_objects.all()

    def save_model(self, request, obj, form, change):
        if not obj.creado_por:
            obj.creado_por = request.user
        obj.actualizado_por = request.user
        super().save_model(request, obj, form, change)

@admin.register(PresupuestoAnual)
class PresupuestoAnualAdmin(admin.ModelAdmin):
    list_display = (
        "proyecto", "numero_anio", "anio_calendario",
        "presupuesto_corriente", "presupuesto_capital",
    )
    list_filter = ("anio_calendario", "proyecto")
    search_fields = ("proyecto__nombre", "proyecto__codigo")
    ordering = ("proyecto", "numero_anio")

from django.contrib import admin
from .models import Proyecto, Transferencia, TipoGasto, Gasto, GastoElegible


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):

    list_display = (
        'nombre',
        'tipo',
        'estado',
        'prioridad',
        'responsable',
        'presupuesto_total',
        'presupuesto_disponible',
        'fecha_creacion',
    )

    list_filter = (
        'tipo',
        'estado',
        'prioridad',
        'fecha_creacion',
    )

    search_fields = (
        'nombre',
        'descripcion',
    )

    ordering = ('-fecha_creacion',)

    autocomplete_fields = ('responsable', 'creado_por')

    readonly_fields = (
        'fecha_creacion',
        'presupuesto_disponible',
        'creado_por',
    )

    fieldsets = (
        ("Información General", {
            "fields": (
                'nombre',
                'descripcion',
                'tipo',
            )
        }),
        ("Gestión", {
            "fields": (
                'responsable',
                'creado_por',
                'duracion_meses',
                'estado',
                'prioridad',
                'cumplimiento',
            )
        }),
        ("Presupuesto (CLP)", {
            "fields": (
                'presupuesto_total',
                'presupuesto_disponible',
            )
        }),
        ("Fechas", {
            "fields": (
                'fecha_creacion',
            )
        }),
    )

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
    list_display = ("id", "nombre", "creado_por", "creado_en")
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
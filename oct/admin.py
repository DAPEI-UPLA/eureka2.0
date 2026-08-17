from django.contrib import admin
from .models import (
    Formulacion,
    Gestion,
    Iniciativa,
    MetaAmbito,
    ProyeccionMensual,
)


# =========================
# FORMULACION INLINE
# =========================

class FormulacionInline(admin.StackedInline):
    model = Formulacion
    extra = 0
    readonly_fields = ("fecha_creacion",)


# =========================
# INICIATIVAS
# =========================

@admin.register(Iniciativa)
class IniciativaAdmin(admin.ModelAdmin):

    list_display = (
        "nombre",
        "unidad",
        "responsable",
        "funcion_institucional",
        "estado",
        "fecha_creacion",
    )

    list_filter = (
        "estado",
        "funcion_institucional",
        "unidad",
    )

    search_fields = (
        "nombre",
        "descripcion",
        "unidad",
        "responsable__username",
    )

    readonly_fields = (
        "fecha_creacion",
        "fecha_actualizacion",
    )

    ordering = ("-fecha_creacion",)

    inlines = [FormulacionInline]


# =========================
# FORMULACIONES
# =========================

@admin.register(Formulacion)
class FormulacionAdmin(admin.ModelAdmin):

    list_display = (
        "iniciativa",
        "nombre_fondo",
        "estado",
        "fecha_creacion",
    )

    list_filter = (
        "estado",
    )

    search_fields = (
        "iniciativa__nombre",
        "nombre_fondo",
    )

    readonly_fields = (
        "fecha_creacion",
    )

    ordering = ("-fecha_creacion",)


# =========================
# TABLERO MAESTRO
# =========================

@admin.register(Gestion)
class GestionAdmin(admin.ModelAdmin):

    list_display = (
        "codigo",
        "nombre",
        "ambito",
        "estado",
        "institucion",
        "fecha_ingreso",
        "monto_postulado",
        "origen",
    )

    list_filter = ("anio", "ambito", "estado", "origen")

    search_fields = ("codigo", "nombre", "institucion", "responsable")

    # Se muestra el rastro de las ediciones, pero no se edita a mano: lo
    # escriben la pantalla de edición y el importador.
    readonly_fields = ("campos_editados", "editado_por", "fecha_edicion",
                       "creado", "actualizado")


@admin.register(ProyeccionMensual)
class ProyeccionMensualAdmin(admin.ModelAdmin):
    list_display = ("anio", "ambito", "mes", "monto")
    list_filter = ("anio", "ambito")


@admin.register(MetaAmbito)
class MetaAmbitoAdmin(admin.ModelAdmin):
    list_display = ("anio", "ambito", "meta_gestiones")
    list_filter = ("anio",)
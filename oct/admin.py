from django.contrib import admin
from .models import Iniciativa, Formulacion


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
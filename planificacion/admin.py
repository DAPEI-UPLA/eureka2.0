from django.contrib import admin
from .models import TipoIndicador, Indicador, Programa, Objetivo, ProgramaIndicador


@admin.register(Programa)
class ProgramaAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "fecha_creacion", "creado_por")
    search_fields = ("nombre",)
    list_filter = ("fecha_creacion",)
    ordering = ("-fecha_creacion",)


@admin.register(Objetivo)
class ObjetivoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nombre",
        "tipo",
        "mostrar_programas",
        "fecha_creacion",
        "creado_por",
    )

    search_fields = ("nombre", "descripcion")
    list_filter = ("tipo", "fecha_creacion")
    ordering = ("-fecha_creacion",)

    autocomplete_fields = ("creado_por",)

    readonly_fields = ("fecha_creacion",)

    fieldsets = (
        ("Información General", {
            "fields": ("nombre", "descripcion", "tipo")
        }),
        ("Control", {
            "fields": ("creado_por", "fecha_creacion")
        }),
    )

    def mostrar_programas(self, obj):
        return ", ".join(
            [p.nombre for p in obj.programas_asociados.all()]
        )

    mostrar_programas.short_description = "Programas"


@admin.register(ProgramaIndicador)
class ProgramaIndicadorAdmin(admin.ModelAdmin):
    list_display = (
        "programa",
        "indicador",
        "meta",
        "anio_meta",
        "linea_base_valor",
    )

    list_filter = (
        "programa",
        "indicador",
    )

    search_fields = (
        "programa__nombre",
        "indicador__nombre",
    )
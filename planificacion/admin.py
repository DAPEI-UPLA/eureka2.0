from django.contrib import admin
from .models import (
    TipoIndicador,
    Indicador,
    Programa,
    Objetivo,
    Estrategia,
    ProgramaIndicador,
    MetaIndicador,
    SeguimientoIndicador,
    CierreAnual,
)


@admin.register(TipoIndicador)
class TipoIndicadorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "descripcion")
    search_fields = ("nombre",)


@admin.register(Programa)
class ProgramaAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "tipo", "estado", "eliminado", "fecha_creacion", "creado_por")
    list_filter = ("tipo", "estado", "eliminado")
    search_fields = ("nombre",)
    ordering = ("-fecha_creacion",)


@admin.register(Objetivo)
class ObjetivoAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "tipo", "eliminado", "fecha_creacion", "creado_por")
    search_fields = ("nombre", "descripcion")
    list_filter = ("tipo", "eliminado")
    ordering = ("-fecha_creacion",)
    autocomplete_fields = ("creado_por",)


@admin.register(Indicador)
class IndicadorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "objetivo", "unidad_medida", "frecuencia", "calculo_invertido", "acumulativo")
    list_filter = ("unidad_medida", "frecuencia", "calculo_invertido", "acumulativo")
    search_fields = ("nombre",)


@admin.register(Estrategia)
class EstrategiaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "plazo", "fecha_creacion")
    list_filter = ("plazo",)
    search_fields = ("nombre",)
    filter_horizontal = ("indicadores",)


class MetaIndicadorInline(admin.TabularInline):
    model = MetaIndicador
    extra = 0


@admin.register(ProgramaIndicador)
class ProgramaIndicadorAdmin(admin.ModelAdmin):
    list_display = ("programa", "indicador", "meta", "linea_base_valor", "peso")
    list_filter = ("programa",)
    search_fields = ("programa__nombre", "indicador__nombre")
    inlines = [MetaIndicadorInline]


@admin.register(MetaIndicador)
class MetaIndicadorAdmin(admin.ModelAdmin):
    list_display = ("programa_indicador", "anio", "valor")
    list_filter = ("anio",)


@admin.register(SeguimientoIndicador)
class SeguimientoIndicadorAdmin(admin.ModelAdmin):
    list_display = ("programa_indicador", "anio", "semestre", "valor", "creado_por", "fecha_registro")
    list_filter = ("anio", "semestre")
    search_fields = ("programa_indicador__indicador__nombre",)


@admin.register(CierreAnual)
class CierreAnualAdmin(admin.ModelAdmin):
    list_display = ("programa", "anio", "cerrado_por", "fecha_cierre")
    list_filter = ("anio",)

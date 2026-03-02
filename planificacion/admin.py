from django.contrib import admin
from .models import TipoIndicador, Indicador, Programa


@admin.register(TipoIndicador)
class TipoIndicadorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre',)


@admin.register(Programa)
class ProgramaAdmin(admin.ModelAdmin):
    list_display = ("nombre",)



@admin.register(Indicador)
class IndicadorAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "programa",
        "tipo",
        "aplica_linea_base",
        "acumulativo",
        "calculo_invertido",
    )
    list_filter = ("programa", "tipo")
    search_fields = ("nombre",)

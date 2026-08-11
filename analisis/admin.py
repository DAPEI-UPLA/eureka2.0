from django.contrib import admin
from .models import Informe, MovimientoInforme


@admin.register(Informe)
class InformeAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "estado",
        "fecha_estimada_termino",
        "responsable",
        "fecha_creacion",
    )
    list_filter = ("estado",)
    search_fields = ("nombre", "descripcion", "responsable__username")
    readonly_fields = ("fecha_creacion", "fecha_actualizacion")
    ordering = ("-fecha_creacion",)


@admin.register(MovimientoInforme)
class MovimientoInformeAdmin(admin.ModelAdmin):
    list_display = ("informe", "tipo", "usuario", "estado_anterior", "estado_nuevo", "fecha")
    list_filter = ("tipo",)
    search_fields = ("informe__nombre", "usuario__username", "detalle")
    readonly_fields = ("fecha",)
    ordering = ("-fecha",)

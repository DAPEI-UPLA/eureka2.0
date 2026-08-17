from django.contrib import admin

from .models import NivelRequerido


@admin.register(NivelRequerido)
class NivelRequeridoAdmin(admin.ModelAdmin):
    list_display = ("ruta", "clave", "nivel", "actualizado")
    list_filter = ("nivel",)
    search_fields = ("ruta", "clave")

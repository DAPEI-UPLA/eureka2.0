from django.contrib import admin
from .models import Proyecto


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

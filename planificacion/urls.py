from django.urls import path
from . import views

app_name = "planificacion"

urlpatterns = [
    # HOME
    path("", views.planificacion_home, name="home"),
    path("buscar/", views.busqueda_global, name="busqueda_global"),

    # INDICADORES
    path("indicadores/", views.lista_indicadores, name="indicadores"),
    path("indicadores/<int:pk>/editar/", views.editar_indicador, name="editar_indicador"),
    path("indicadores/<int:pk>/eliminar/", views.eliminar_indicador, name="eliminar_indicador"),

    # OBJETIVOS
    path("objetivos/", views.lista_objetivos, name="lista_objetivos"),
    path("objetivos/<int:pk>/editar/", views.editar_objetivo, name="editar_objetivo"),
    path("objetivos/<int:pk>/eliminar/", views.eliminar_objetivo, name="eliminar_objetivo"),

    # ESTRATEGIAS
    path("estrategias/", views.lista_estrategias, name="estrategias"),
    path("estrategias/<int:pk>/editar/", views.editar_estrategia, name="editar_estrategia"),
    path("estrategias/<int:pk>/eliminar/", views.eliminar_estrategia, name="eliminar_estrategia"),

    # PROGRAMAS
    path("programas/", views.lista_programas, name="lista_programas"),
    path("programas/crear/", views.crear_programa, name="crear_programa"),

    path("programas/<int:pk>/seguimiento/", views.seguimiento_programa, name="seguimiento_programa"),
    path("programas/<int:pk>/publico/", views.seguimiento_programa_publico, name="seguimiento_publico"),
    path("programas/<int:pk>/heatmap/", views.heatmap_programa, name="heatmap"),

    path("programas/comparar/", views.comparar_programas, name="comparar"),

    # ACCIONES SOBRE PROGRAMA (separadas)
    path("programas/<int:id>/editar/", views.editar_programa, name="editar_programa"),
    path("programas/<int:pk>/eliminar/", views.eliminar_programa, name="eliminar_programa"),
    path("programas/<int:pk>/estado/", views.cambiar_estado_programa, name="cambiar_estado"),

    path("programas/<int:pk>/objetivos/agregar/", views.agregar_objetivo, name="agregar_objetivo"),
    path("programas/<int:pk>/objetivos/quitar/", views.quitar_objetivo, name="quitar_objetivo"),
    path("programas/<int:pk>/indicadores/agregar/", views.agregar_indicador, name="agregar_indicador"),
    path("programas/<int:pk>/indicadores/quitar/", views.quitar_indicador, name="quitar_indicador"),

    path("pi/<int:pi_id>/valor/", views.registrar_valor, name="registrar_valor"),
    path("pi/<int:pi_id>/meta/", views.guardar_meta, name="guardar_meta"),
    path("pi/<int:pi_id>/guardar/", views.guardar_meta_y_valor, name="guardar_meta_y_valor"),

    # CIERRE / REAPERTURA
    path("programas/<int:pk>/cerrar/", views.cerrar_anio, name="cerrar_anio"),
    path("programas/<int:pk>/reabrir/", views.reabrir_anio, name="reabrir_anio"),

    # API
    path("api/programa/<int:pk>/series/", views.api_series_programa, name="api_series"),

    # EXCEL
    path("programas/<int:pk>/excel/plantilla/", views.descargar_plantilla_excel, name="excel_plantilla"),
    path("programas/<int:pk>/excel/importar/", views.importar_excel, name="excel_importar"),
    path("programas/<int:pk>/excel/exportar/", views.exportar_excel, name="excel_exportar"),

    # PROGRAMAS por tipo (debe ir AL FINAL para no capturar 'crear', 'comparar', etc.)
    path("programas/<str:tipo>/", views.lista_programas_tipo, name="lista_programas_tipo"),
]

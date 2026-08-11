from django.urls import path
from . import views

app_name = 'otec'

urlpatterns = [
    path('', views.otec_home, name='home'),
    path('gestion/', views.panel_gestion, name='panel_gestion'),

    # Registro de actividades
    path('actividades/', views.lista_actividades, name='lista_actividades'),
    path('actividades/<int:pk>/', views.detalle_actividad, name='detalle_actividad'),
    path('checklist/<int:pk>/actualizar/', views.actualizar_item, name='actualizar_item'),

    # Carga de datos
    path('importar/', views.importar_tablero, name='importar'),

    # Indicadores y gráficos
    path('indicadores/', views.indicadores, name='indicadores'),
    path('graficos/', views.graficos_otec, name='graficos'),
    path('flujo/', views.flujo_caja, name='flujo_caja'),

    # Edición de lo que alimenta el flujo
    path('flujo/<int:anio>/supuestos/', views.editar_supuestos, name='editar_supuestos'),
    path('flujo/<int:anio>/meta/', views.editar_meta, name='editar_meta'),
    path('flujo/lineas/<int:pk>/editar/', views.editar_linea, name='editar_linea'),
    path('flujo/transversales/<int:pk>/editar/',
         views.editar_costo_transversal, name='editar_costo_transversal'),

    # Calendario
    path('gantt/', views.carta_gantt, name='carta_gantt'),
    path('zoom/', views.calendario_zoom, name='calendario_zoom'),

    # Propuestas
    path('propuestas/', views.lista_propuestas, name='lista_propuestas'),
    path('propuestas/nueva/', views.crear_propuesta, name='crear_propuesta'),
    path('propuestas/<int:pk>/', views.detalle_propuesta, name='detalle_propuesta'),
    path('propuestas/<int:pk>/editar/', views.editar_propuesta, name='editar_propuesta'),
    path('propuestas/<int:pk>/eliminar/', views.eliminar_propuesta, name='eliminar_propuesta'),

    # Alta y edición de actividades
    path('actividades/nueva/', views.crear_actividad, name='crear_actividad'),
    path('propuestas/<int:propuesta_pk>/actividades/nueva/',
         views.crear_actividad, name='crear_actividad_en_propuesta'),
    path('actividades/<int:pk>/editar/', views.editar_actividad, name='editar_actividad'),
    path('actividades/<int:pk>/eliminar/', views.eliminar_actividad, name='eliminar_actividad'),

    # Calendario de clases del curso
    path('actividades/<int:pk>/calendario/', views.calendario_curso, name='calendario_curso'),
    path('sesiones/<int:pk>/eliminar/', views.eliminar_sesion, name='eliminar_sesion'),

    # Apoyo de formularios
    path('contactos/opciones/', views.contactos_de_institucion, name='contactos_opciones'),
]

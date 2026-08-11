from django.urls import path
from . import views

app_name = "analisis"

urlpatterns = [
    path("", views.analisis_home, name="home"),
    path("informes/", views.panel_informes, name="panel_informes"),
    path("informes/graficos/", views.graficos_informes, name="graficos_informes"),
    path("informes/crear/", views.crear_informe, name="crear_informe"),
    path("informes/<int:pk>/editar/", views.editar_informe, name="editar_informe"),
    path("informes/<int:pk>/eliminar/", views.eliminar_informe, name="eliminar_informe"),
    path("informes/<int:pk>/enviar-revision/", views.enviar_a_revision, name="enviar_a_revision"),
    path("informes/<int:pk>/aprobar/", views.aprobar_informe, name="aprobar_informe"),
    path("informes/<int:pk>/rechazar/", views.rechazar_informe, name="rechazar_informe"),
    path("informes/<int:pk>/trazabilidad/", views.trazabilidad_informe, name="trazabilidad_informe"),
]

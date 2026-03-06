from django.urls import path
from . import views

app_name = 'planificacion'

urlpatterns = [
    path('', views.planificacion_home, name='home'),
    path('indicadores/', views.lista_indicadores, name='indicadores'),
    path('indicadores/<int:pk>/editar/', views.editar_indicador, name='editar_indicador'),
    path('indicadores/<int:pk>/eliminar/', views.eliminar_indicador, name='eliminar_indicador'),
    path('programas/crear/', views.crear_programa, name='crear_programa'),
    path('programa/<int:id>/editar/', views.editar_programa, name='editar_programa'),
    path("programa/<int:pk>/eliminar/", views.eliminar_programa, name="eliminar_programa"),
    path("objetivos/", views.lista_objetivos, name="lista_objetivos"),
    path("estrategias/", views.lista_estrategias, name="estrategias"),
    path("estrategias/<int:pk>/editar/", views.editar_estrategia, name="editar_estrategia"),
    path("estrategias/<int:pk>/eliminar/", views.eliminar_estrategia, name="eliminar_estrategia"),
    path("programas/", views.lista_programas, name="lista_programas"),
    path("programas/<int:pk>/seguimiento/", views.seguimiento_programa, name="seguimiento_programa"),
    path("programas/<int:pk>/agregar-indicador/", views.agregar_indicador_programa, name="agregar_indicador_programa",),
]

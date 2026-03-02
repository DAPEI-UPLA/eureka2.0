from django.urls import path
from . import views

app_name = 'planificacion'

urlpatterns = [
    path('', views.planificacion_home, name='home'),
    path('indicadores/', views.lista_indicadores, name='indicadores'),
    path('indicadores/crear/', views.crear_indicador, name='crear_indicador'),
    path('indicadores/<int:id>/editar/', views.editar_indicador, name='editar_indicador'),
    path('indicadores/<int:id>/eliminar/', views.eliminar_indicador, name='eliminar_indicador'),
    path('desafios/', views.desafios, name='desafios'),
    path('programas/crear/', views.crear_programa, name='crear_programa'),
    path('programa/<int:id>/editar/', views.editar_programa, name='editar_programa'),
    path("programa/<int:pk>/eliminar/", views.eliminar_programa, name="eliminar_programa"),
]

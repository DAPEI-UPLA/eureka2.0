from django.urls import path

from . import views

app_name = 'evaluaciones'

urlpatterns = [
    path('', views.home, name='home'),

    # Navegación del organigrama: la misma URL sirve ramas y fichas de cargo.
    path('unidad/<path:ruta>/', views.nodo, name='nodo'),

    # Instrumento genérico, armado desde el texto del perfil del cargo
    path('evaluar/<path:ruta>/', views.evaluar_cargo, name='evaluar_cargo'),

    # Instrumento oficial (T2 de Tesorería) e informe para imprimir o guardar como PDF
    path('instrumento/', views.instrumento, name='instrumento'),
    path('instrumento/informe/', views.informe_instrumento, name='informe'),
]

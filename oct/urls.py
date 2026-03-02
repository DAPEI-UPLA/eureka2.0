from django.urls import path
from . import views

app_name = 'oct'

urlpatterns = [
    path('', views.oct_home, name='home'),
    path('iniciativas/', views.iniciativas_home, name='iniciativas_home'),
    path('iniciativas/registrar/', views.registrar_iniciativa, name='registrar_iniciativa'),
    path('iniciativas/mis/', views.mis_iniciativas, name='mis_iniciativas'),
    path('iniciativas/revision/', views.panel_aprobacion, name='panel_aprobacion'),
    path('iniciativas/revision/<int:pk>/', views.detalle_iniciativa_aprobador, name='detalle_aprobador'),
    path('iniciativas/editar/<int:pk>/', views.editar_iniciativa, name='editar_iniciativa'),
]
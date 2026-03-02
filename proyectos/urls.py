from django.urls import path
from . import views

app_name = 'proyectos'


urlpatterns = [
    path('', views.lista_proyectos, name='lista_proyectos'),
    path('proyectos/<int:pk>/', views.detalle_proyecto, name="detalle_proyecto"),
    path("proyectos/<int:pk>/crear-objetivo/", views.crear_objetivo, name="crear_objetivo"),
    path("objetivo/<int:pk>/editar/", views.editar_objetivo_form, name="editar_objetivo"),
    path("objetivo/<int:pk>/guardar/", views.guardar_objetivo, name="guardar_objetivo"),
    path('objetivo/<int:pk>/crear-resultado/', views.crear_resultado, name='crear_resultado'),
]

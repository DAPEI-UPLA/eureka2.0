from django.urls import path
from . import views

app_name = 'proyectos'


urlpatterns = [
    # URLS dedicadas a las vistas de proyectos
    path('', views.lista_proyectos, name='lista_proyectos'),
    path('proyectos/<int:pk>/', views.detalle_proyecto, name="detalle_proyecto"),
    
    # URLS para las vistas de objetivos
    path("proyectos/<int:pk>/crear-objetivo/", views.crear_objetivo, name="crear_objetivo"),
    path("objetivo/<int:pk>/editar/", views.editar_objetivo_form, name="editar_objetivo_form"),
    path("objetivo/<int:pk>/guardar/", views.guardar_objetivo, name="guardar_objetivo"),

    # URLS para las vistas de resultados
    path('objetivo/<int:pk>/crear-resultado/', views.crear_resultado, name='crear_resultado'),
    path('resultado/<int:pk>/editar/', views.editar_resultado_form, name='editar_resultado_form'),
    path('resultado/<int:pk>/guardar/', views.guardar_resultado, name='guardar_resultado'),
    path('resultado/<int:pk>/eliminar/', views.eliminar_resultado, name='eliminar_resultado'),
    path("resultado/<int:pk>/presupuesto/", views.detalle_presupuesto_resultado, name="detalle_presupuesto_resultado")
]

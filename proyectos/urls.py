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
    path("resultado/<int:pk>/presupuesto/", views.detalle_presupuesto_resultado, name="detalle_presupuesto_resultado"),
    
    # URLS para asignación de presupuesto
    path("resultado/<int:pk>/presupuesto/form/", views.form_asignar_presupuesto, name="form_asignar_presupuesto"),
    path("resultado/<int:pk>/presupuesto/guardar/", views.guardar_presupuesto, name="guardar_presupuesto"),

    # URLS para Gastos
    path('gastos/crear/<int:resultado_id>/', views.crear_gasto, name='crear_gasto'),
    path('gastos/guardar/<int:resultado_id>/', views.guardar_gasto, name='guardar_gasto'),

    # URLS para plan de gasto
    path("plan-gasto/<int:proyecto_id>/form/", views.crear_plan_gasto_form, name="crear_plan_gasto_form"),
    path("plan-gasto/<int:proyecto_id>/crear/", views.crear_plan_gasto, name="crear_plan_gasto"),
    path("cargar-resultados/", views.cargar_resultados, name="cargar_resultados"),

    # URLS para Actividades
    path("resultado/<int:resultado_id>/actividades/", views.listar_actividades, name="listar_actividades"),
    path("resultado/<int:resultado_id>/actividad/form/", views.crear_actividad_form, name="crear_actividad_form"),
    path("resultado/<int:resultado_id>/actividad/crear/", views.crear_actividad, name="crear_actividad"),

]







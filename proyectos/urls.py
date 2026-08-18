from django.urls import path
from . import views

app_name = 'proyectos'

urlpatterns = [
    # PROYECTOS
    path('', views.lista_proyectos, name='lista_proyectos'),
    path('graficos/', views.graficos_proyectos, name='graficos_proyectos'),
    path('exportar/cartera/', views.exportar_cartera_excel, name='exportar_cartera_excel'),
    path('proyectos/<int:pk>/', views.detalle_proyecto, name="detalle_proyecto"),
    path('proyectos/<int:pk>/graficos/', views.graficos_proyecto, name="graficos_proyecto"),
    path('proyectos/<int:pk>/exportar/', views.exportar_proyecto_excel, name="exportar_proyecto_excel"),
    path('proyectos/<int:pk>/informe/', views.informe_proyecto, name="informe_proyecto"),
    path('proyectos/<int:pk>/editar/', views.editar_proyecto, name="editar_proyecto"),

    # PRESUPUESTO ANUAL
    path('proyectos/<int:pk>/anios/', views.listar_presupuesto_anual, name="listar_presupuesto_anual"),
    path('proyectos/<int:pk>/anios/crear/', views.crear_anio, name="crear_anio"),
    path('anio/<int:pk>/guardar/', views.guardar_anio, name="guardar_anio"),
    path('anio/<int:pk>/eliminar/', views.eliminar_anio, name="eliminar_anio"),
    path('proyectos/<int:pk>/eliminar/', views.eliminar_proyecto, name="eliminar_proyecto"),
    path('proyectos/<int:pk>/dashboard/', views.dashboard_proyecto, name="dashboard_proyecto"),

    # OBJETIVOS
    path("proyectos/<int:pk>/objetivos/", views.listar_objetivos, name="listar_objetivos"),
    path("proyectos/<int:pk>/crear-objetivo/", views.crear_objetivo, name="crear_objetivo"),
    path("objetivo/<int:pk>/editar/", views.editar_objetivo_form, name="editar_objetivo_form"),
    path("objetivo/<int:pk>/guardar/", views.guardar_objetivo, name="guardar_objetivo"),
    path("objetivo/<int:pk>/meta/", views.meta_objetivo, name="meta_objetivo"),
    path("objetivo/<int:pk>/presupuesto/", views.editar_presupuesto_objetivo, name="editar_presupuesto_objetivo"),
    path("objetivo/<int:pk>/presupuesto/anual/", views.presupuesto_objetivo_anual, name="presupuesto_objetivo_anual"),
    path("objetivo/<int:pk>/presupuesto/anual/guardar/", views.guardar_presupuesto_objetivo_anual, name="guardar_presupuesto_objetivo_anual"),
    path("objetivo/<int:pk>/eliminar/", views.eliminar_objetivo, name="eliminar_objetivo"),
    path("objetivo/<int:pk>/mover/<str:direccion>/", views.mover_objetivo, name="mover_objetivo"),

    # RESULTADOS
    path('objetivo/<int:pk>/resultados/', views.listar_resultados, name='listar_resultados'),
    path('objetivo/<int:pk>/crear-resultado/', views.crear_resultado, name='crear_resultado'),
    path('resultado/<int:pk>/editar/', views.editar_resultado_form, name='editar_resultado_form'),
    path('resultado/<int:pk>/fila/', views.fila_resultado, name='fila_resultado'),
    path('resultado/<int:pk>/guardar/', views.guardar_resultado, name='guardar_resultado'),
    path('resultado/<int:pk>/eliminar/', views.eliminar_resultado, name='eliminar_resultado'),
    path('resultado/<int:pk>/mover/<str:direccion>/', views.mover_resultado, name='mover_resultado'),
    path("resultado/<int:pk>/presupuesto/", views.detalle_presupuesto_resultado, name="detalle_presupuesto_resultado"),

    # PRESUPUESTO
    path("resultado/<int:pk>/presupuesto/form/", views.form_asignar_presupuesto, name="form_asignar_presupuesto"),
    path("resultado/<int:pk>/presupuesto/guardar/", views.guardar_presupuesto, name="guardar_presupuesto"),
    path("resultado/<int:pk>/presupuesto/anual/", views.presupuesto_resultado_anual, name="presupuesto_resultado_anual"),
    path("resultado/<int:pk>/presupuesto/anual/guardar/", views.guardar_presupuesto_resultado_anual, name="guardar_presupuesto_resultado_anual"),

    # PLAN DE GASTO
    path("plan-gasto/<int:proyecto_id>/form/", views.crear_plan_gasto_form, name="crear_plan_gasto_form"),
    path("plan-gasto/<int:proyecto_id>/crear/", views.crear_plan_gasto, name="crear_plan_gasto"),
    path("plan-gasto/<int:proyecto_id>/lista/", views.listar_planes_gasto, name="listar_planes_gasto"),
    path("plan-gasto/actividad/<int:actividad_id>/", views.listar_planes_actividad, name="listar_planes_actividad"),
    path("plan-gasto/<int:pk>/editar/", views.editar_plan_gasto_form, name="editar_plan_gasto_form"),
    path("plan-gasto/<int:pk>/guardar/", views.editar_plan_gasto, name="editar_plan_gasto"),
    path("plan-gasto/<int:pk>/eliminar/", views.eliminar_plan_gasto, name="eliminar_plan_gasto"),
    path("cargar-resultados/", views.cargar_resultados, name="cargar_resultados"),
    path("cargar-actividades/", views.cargar_actividades, name="cargar_actividades"),
    path("cargar-tipos-gasto/", views.cargar_tipos_gasto, name="cargar_tipos_gasto"),
    path("cargar-gastos/", views.cargar_gastos, name="cargar_gastos"),
    path("cargar-gastos-elegibles/", views.cargar_gastos_elegibles, name="cargar_gastos_elegibles"),

    # EGRESOS (Compras / Honorarios / Viáticos)
    path("egreso/<int:proyecto_id>/form/", views.crear_egreso_form, name="crear_egreso_form"),
    path("egreso/<int:proyecto_id>/crear/", views.crear_egreso, name="crear_egreso"),
    path("egreso/<int:proyecto_id>/lista/", views.listar_egresos, name="listar_egresos"),
    path("egreso/<int:proyecto_id>/elegibles-por-subtipo/", views.elegibles_por_subtipo, name="egreso_elegibles_por_subtipo"),
    path("egreso/<int:proyecto_id>/planes-por-elegible/", views.planes_por_elegible, name="egreso_planes_por_elegible"),
    path("egreso/<int:pk>/editar/", views.editar_egreso_form, name="editar_egreso_form"),
    path("egreso/<int:pk>/guardar/", views.editar_egreso, name="editar_egreso"),
    path("egreso/<int:pk>/eliminar/", views.eliminar_egreso, name="eliminar_egreso"),
    path("egreso/<int:pk>/pagar-cuota/", views.pagar_cuota, name="egreso_pagar_cuota"),
    path("egreso/<int:pk>/pagar-impuesto/", views.pagar_impuesto, name="egreso_pagar_impuesto"),
    path("egreso/plan-detalle/", views.plan_detalle, name="egreso_plan_detalle"),

    # ACTIVIDADES
    path("resultado/<int:resultado_id>/actividades/", views.listar_actividades, name="listar_actividades"),
    path("resultado/<int:resultado_id>/actividad/form/", views.crear_actividad_form, name="crear_actividad_form"),
    path("resultado/<int:resultado_id>/actividad/crear/", views.crear_actividad, name="crear_actividad"),
    path("actividad/<int:actividad_id>/editar/form/", views.editar_actividad_form, name="editar_actividad_form"),
    path("actividad/<int:actividad_id>/editar/", views.editar_actividad, name="editar_actividad"),
    path("actividad/<int:actividad_id>/eliminar/", views.eliminar_actividad, name="eliminar_actividad"),
    path("actividad/<int:actividad_id>/guardar/", views.guardar_actividad, name="guardar_actividad"),
    path("actividad/<int:pk>/mover/<str:direccion>/", views.mover_actividad, name="mover_actividad"),
]
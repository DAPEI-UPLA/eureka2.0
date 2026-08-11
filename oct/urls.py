from django.urls import path
from . import views

app_name = 'oct'

urlpatterns = [
    path('', views.oct_home, name='home'),
    path('iniciativas/', views.iniciativas_home, name='iniciativas_home'),
    path('iniciativas/registrar/', views.registrar_iniciativa, name='registrar_iniciativa'),
    path('iniciativas/mis/', views.mis_iniciativas, name='mis_iniciativas'),

    # Detalle unificado (responsable o aprobador)
    path('iniciativas/<int:pk>/', views.detalle_iniciativa, name='detalle_iniciativa'),

    # Ciclo de vida (responsable)
    path('iniciativas/editar/<int:pk>/', views.editar_iniciativa, name='editar_iniciativa'),
    path('iniciativas/<int:pk>/adjudicada/', views.marcar_adjudicada, name='marcar_adjudicada'),
    path('iniciativas/<int:pk>/no-adjudicada/', views.marcar_no_adjudicada, name='marcar_no_adjudicada'),

    # Documentos de la iniciativa
    path('iniciativas/<int:pk>/documentos/subir/', views.subir_documento_iniciativa, name='subir_documento_iniciativa'),
    path('documentos/iniciativa/<int:pk>/eliminar/', views.eliminar_documento_iniciativa, name='eliminar_documento_iniciativa'),

    # Revisión de iniciativas (aprobador)
    path('iniciativas/revision/', views.panel_aprobacion, name='panel_aprobacion'),
    path('iniciativas/revision/<int:pk>/', views.detalle_iniciativa_aprobador, name='detalle_aprobador'),

    # Formulación (responsable)
    path("iniciativas/formular/", views.formular_iniciativas, name="formular_iniciativas"),
    path("iniciativas/formular/<int:pk>/", views.formular_iniciativa, name="formular_iniciativa"),
    path("iniciativas/formular/<int:pk>/guardar/", views.guardar_formulacion, name="guardar_formulacion"),
    path("iniciativas/formulacion/<int:iniciativa_id>/", views.ver_formulacion, name="ver_formulacion"),
    path("iniciativas/formulacion/<int:pk>/editar/", views.editar_formulacion, name="editar_formulacion"),
    path("iniciativas/formulacion/<int:pk>/enviar/", views.enviar_formulacion, name="enviar_formulacion"),

    # Documentos de la formulación
    path("formulaciones/<int:pk>/documentos/subir/", views.subir_documento_formulacion, name="subir_documento_formulacion"),
    path("documentos/formulacion/<int:pk>/eliminar/", views.eliminar_documento_formulacion, name="eliminar_documento_formulacion"),

    # Revisión de formulaciones (aprobador)
    path("formulaciones/revisar/", views.revisar_formulaciones, name="revisar_formulaciones"),
    path("formulaciones/aprobar/<int:pk>/", views.aprobar_formulacion, name="aprobar_formulacion"),
    path("formulaciones/devolver/<int:pk>/", views.devolver_formulacion, name="devolver_formulacion"),
]

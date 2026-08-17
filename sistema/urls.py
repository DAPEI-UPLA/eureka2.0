from django.contrib import admin
from django.urls import path, include, re_path

from core.views import media_protegida

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('planificacion/', include('planificacion.urls')),
    path('proyectos/', include('proyectos.urls')),
    path('oct/', include('oct.urls')),
    path('otec/', include('otec.urls')),
    path('analisis/', include('analisis.urls')),
    path('evaluaciones/', include('evaluaciones.urls')),
    # Los archivos subidos se sirven SIEMPRE a través de una vista protegida
    # (login_required), tanto en desarrollo como en producción, para no exponer
    # documentos sensibles por URL directa.
    re_path(r'^media/(?P<ruta>.+)$', media_protegida, name='media_protegida'),
]

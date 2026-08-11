from pathlib import Path

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils._os import safe_join

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            return render(request, 'core/login.html', {
                'error': 'Usuario o contraseña incorrectos'
            })

    return render(request, 'core/login.html')


@login_required
def home(request):
    return render(request, 'core/home.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def media_protegida(request, ruta):
    """Sirve archivos de MEDIA_ROOT solo a usuarios autenticados.

    Evita que documentos subidos (informes, evidencias, formulaciones) sean
    accesibles por URL directa sin sesión. `safe_join` previene path traversal
    (p. ej. ``../../db.sqlite3``).
    """
    try:
        ruta_absoluta = safe_join(settings.MEDIA_ROOT, ruta)
    except SuspiciousFileOperation:
        raise Http404("Archivo no encontrado.")

    archivo = Path(ruta_absoluta)
    if not archivo.is_file():
        raise Http404("Archivo no encontrado.")

    # as_attachment=True fuerza la descarga y evita que el navegador renderice
    # contenido potencialmente malicioso (HTML/SVG) servido desde /media.
    return FileResponse(archivo.open("rb"), as_attachment=True)

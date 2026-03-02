from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from .forms import IniciativaForm
from .models import Iniciativa



def oct_home(request):
    return render(request, 'oct/home.html')


def iniciativas_home(request):
    return render(request, 'oct/iniciativas_home.html')



@login_required
def registrar_iniciativa(request):

    if request.method == "POST":
        form = IniciativaForm(request.POST)

        if form.is_valid():
            iniciativa = form.save(commit=False)
            iniciativa.responsable = request.user
            iniciativa.save()

            # Si el usuario presionó botón "Enviar"
            if "enviar" in request.POST:
                iniciativa.estado = Iniciativa.Estado.ENVIADA
                iniciativa.save()

            return redirect("oct:mis_iniciativas")

    else:
        form = IniciativaForm()

    return render(request, "oct/registrar_iniciativa.html", {
        "form": form
    })


@login_required
def mis_iniciativas(request):
    iniciativas = Iniciativa.objects.filter(responsable=request.user)

    return render(request, "oct/mis_iniciativas.html", {
        "iniciativas": iniciativas
    })

@login_required
def iniciativas_home(request):

    es_aprobador = request.user.groups.filter(
        name="Aprobadores de Iniciativas"
    ).exists()

    return render(request, "oct/iniciativas_home.html", {
        "es_aprobador": es_aprobador
    })





def es_aprobador(user):
    return user.groups.filter(
        name="Aprobadores de Iniciativas"
    ).exists()


@user_passes_test(es_aprobador)
def panel_aprobacion(request):

    iniciativas = Iniciativa.objects.filter(
        estado=Iniciativa.Estado.ENVIADA
    ).order_by("-fecha_creacion")

    return render(request, "oct/panel_aprobacion.html", {
        "iniciativas": iniciativas
    })

@user_passes_test(es_aprobador)
def detalle_iniciativa_aprobador(request, pk):

    iniciativa = get_object_or_404(Iniciativa, pk=pk)

    if request.method == "POST":

        accion = request.POST.get("accion")

        if accion == "aprobar":
            iniciativa.estado = Iniciativa.Estado.APROBADA
            iniciativa.observaciones = ""
            iniciativa.save()
            messages.success(request, "Iniciativa aprobada correctamente.")

        elif accion == "devolver":
            observaciones = request.POST.get("observaciones")
            iniciativa.estado = Iniciativa.Estado.DEVUELTA
            iniciativa.observaciones = observaciones
            iniciativa.save()
            messages.warning(request, "Iniciativa devuelta con observaciones.")

        return redirect("oct:panel_aprobacion")

    return render(request, "oct/detalle_aprobador.html", {
        "iniciativa": iniciativa
    })


@login_required
def editar_iniciativa(request, pk):

    iniciativa = get_object_or_404(Iniciativa, pk=pk)

    if iniciativa.responsable != request.user:
        raise PermissionDenied

    estados_editables = [
        Iniciativa.Estado.BORRADOR,
        Iniciativa.Estado.ENVIADA,
        Iniciativa.Estado.DEVUELTA,
    ]

    if iniciativa.estado not in estados_editables:
        raise PermissionDenied

    if request.method == "POST":
        form = IniciativaForm(request.POST, instance=iniciativa)

        if form.is_valid():
            iniciativa = form.save()

            if "enviar" in request.POST:
                iniciativa.estado = Iniciativa.Estado.ENVIADA
                iniciativa.save()

            return redirect("oct:mis_iniciativas")

    else:
        form = IniciativaForm(instance=iniciativa)

    return render(request, "oct/editar_iniciativa.html", {
        "form": form,
        "iniciativa": iniciativa
    })
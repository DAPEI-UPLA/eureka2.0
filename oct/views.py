from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from .forms import IniciativaForm, FormulacionForm
from .models import Iniciativa, Formulacion



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

# Aquí comienza el apartado de formulación de iniciativas

@login_required
def formular_iniciativa(request, pk):

    iniciativa = get_object_or_404(
        Iniciativa,
        pk=pk,
        responsable=request.user,
        estado=Iniciativa.Estado.APROBADA
    )

    if request.method == "POST":
        form = FormulacionForm(request.POST)

        if form.is_valid():
            formulacion = form.save(commit=False)
            formulacion.iniciativa = iniciativa
            formulacion.save()

            return redirect("oct:formular_iniciativas")

    else:
        form = FormulacionForm()

    return render(request, "oct/formular_iniciativa.html", {
        "form": form,
        "iniciativa": iniciativa
    })


@login_required
def formular_iniciativas(request):

    iniciativas = Iniciativa.objects.filter(
        responsable=request.user,
        estado=Iniciativa.Estado.APROBADA
    ).select_related()

    form = FormulacionForm()

    return render(request, "oct/formular_iniciativas.html", {
        "iniciativas": iniciativas,
        "form": form
    })


@login_required
def guardar_formulacion(request, pk):

    iniciativa = get_object_or_404(
        Iniciativa,
        pk=pk,
        responsable=request.user,
        estado=Iniciativa.Estado.APROBADA
    )

    if request.method == "POST":

        form = FormulacionForm(request.POST)

        if form.is_valid():

            formulacion = form.save(commit=False)
            formulacion.iniciativa = iniciativa
            formulacion.save()

            return redirect("oct:formular_iniciativas")

    return redirect("oct:formular_iniciativas")


def ver_formulacion(request, iniciativa_id):

    iniciativa = get_object_or_404(Iniciativa, id=iniciativa_id)

    formulacion = getattr(iniciativa, "formulacion", None)

    context = {
        "iniciativa": iniciativa,
        "formulacion": formulacion
    }

    return render(request, "oct/ver_formulacion.html", context)

@login_required
def editar_formulacion(request, pk):

    iniciativa = get_object_or_404(
        Iniciativa,
        pk=pk,
        responsable=request.user
    )

    formulacion = get_object_or_404(
        Formulacion,
        iniciativa=iniciativa
    )

    if request.method == "POST":

        form = FormulacionForm(request.POST, instance=formulacion)

        if form.is_valid():

            formulacion = form.save()

            if "enviar" in request.POST:
                formulacion.estado = Formulacion.Estado.ENVIADA
                formulacion.save()

            return redirect("oct:formular_iniciativas")

    else:
        form = FormulacionForm(instance=formulacion)

    return render(request, "oct/editar_formulacion.html", {
        "form": form,
        "iniciativa": iniciativa
    })

@login_required
def enviar_formulacion(request, pk):

    iniciativa = get_object_or_404(Iniciativa, pk=pk)
    formulacion = get_object_or_404(Formulacion, iniciativa=iniciativa)

    if request.method == "POST":

        formulacion.estado = "ENV"
        formulacion.save()

    return redirect("oct:formular_iniciativas")





@login_required
def revisar_formulaciones(request):

    es_aprobador = request.user.groups.filter(
        name="Aprobadores de Iniciativas"
    ).exists()

    if not es_aprobador:
        return redirect("home")

    formulaciones = Formulacion.objects.select_related(
        "iniciativa"
    ).filter(
        estado="ENV"
    )

    context = {
        "formulaciones": formulaciones
    }

    return render(
        request,
        "oct/revisar_formulaciones.html",
        context
    )



@login_required
def aprobar_formulacion(request, pk):

    formulacion = get_object_or_404(Formulacion, pk=pk)

    formulacion.estado = "APR"
    formulacion.save()

    return redirect("oct:revisar_formulaciones")


@login_required
def devolver_formulacion(request, pk):

    formulacion = get_object_or_404(Formulacion, pk=pk)

    if request.method == "POST":

        observaciones = request.POST.get("observaciones")

        formulacion.estado = "DEV"
        formulacion.observaciones = observaciones
        formulacion.save()

    return redirect("oct:revisar_formulaciones")
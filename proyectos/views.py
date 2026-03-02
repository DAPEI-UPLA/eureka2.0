from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Proyecto, ObjetivoEspecifico, Resultado
from .forms import ProyectoForm
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.http import HttpResponseForbidden

def es_encargada(user):
    return user.groups.filter(name='EncargadaProyectos').exists()


@login_required
def mis_proyectos(request):
    proyectos = Proyecto.objects.filter(asignado_a=request.user)
    return render(request, 'proyectos/mis_proyectos.html', {'proyectos': proyectos})


@login_required
def proyectos_por_tipo(request, tipo_id):
    proyectos = Proyecto.objects.filter(tipo_id=tipo_id)
    return render(request, 'proyectos/proyectos_por_tipo.html', {'proyectos': proyectos})


@login_required
def lista_proyectos(request):

    user = request.user
    es_jefe = user.groups.filter(name='JefeProyectos').exists()

    if es_jefe:
        proyectos = Proyecto.objects.all()
    else:
        proyectos = Proyecto.objects.filter(responsable=user)

    if request.method == 'POST' and es_jefe:
        form = ProyectoForm(request.POST)
        if form.is_valid():
            proyecto = form.save(commit=False)
            proyecto.creado_por = request.user
            proyecto.save()
            return redirect('proyectos:lista_proyectos')
    else:
        form = ProyectoForm()

    return render(request, 'proyectos/lista_proyectos.html', {
        'proyectos': proyectos,
        'es_jefe': es_jefe,
        'form': form
    })


def detalle_proyecto(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)

    es_encargado = request.user == proyecto.responsable
    es_jefe = request.user.groups.filter(name="Jefe").exists()

    contexto = {
        "proyecto": proyecto,
        "es_encargado": es_encargado,
        "es_jefe": es_jefe,
    }

    return render(request, "proyectos/detalle_proyecto.html", contexto)


def crear_objetivo(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)

    # 🔒 Solo encargado puede crear
    if request.user != proyecto.responsable:
        return HttpResponseForbidden("No autorizado")

    objetivo = ObjetivoEspecifico.objects.create(
        proyecto=proyecto,
        descripcion="Nuevo objetivo"
    )

    html = render_to_string(
        "proyectos/partials/objetivo_row.html",
        {"objetivo": objetivo},
        request=request
    )

    return HttpResponse(html)

def editar_objetivo_form(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)

    # 🔒 Solo encargado puede editar
    if request.user != objetivo.proyecto.responsable:
        return HttpResponseForbidden("No autorizado")

    return render(request,
                  "proyectos/partials/objetivo_input.html",
                  {"objetivo": objetivo})

def guardar_objetivo(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)

    if request.user != objetivo.proyecto.responsable:
        return HttpResponseForbidden("No autorizado")

    nueva_descripcion = request.POST.get("descripcion")
    objetivo.descripcion = nueva_descripcion
    objetivo.save()

    return render(request,
                  "proyectos/partials/objetivo_texto.html",
                  {"objetivo": objetivo})



def crear_resultado(request, pk):
    objetivo = get_object_or_404(ObjetivoEspecifico, pk=pk)

    resultado = Resultado.objects.create(
        objetivo=objetivo,
        descripcion="Nuevo resultado"
    )

    return render(
        request,
        "proyectos/partials/resultado_row.html",
        {"resultado": resultado}
    )
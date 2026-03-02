from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Indicador, Programa, TipoIndicador
from django.contrib.auth.decorators import permission_required
from .forms import IndicadorForm, ProgramaForm
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied

@login_required
def index(request):
    return render(request, 'planificacion/index.html')

def es_planificacion(user):
    return user.groups.filter(name='Planificacion').exists()

@login_required
def indicadores(request):
    areas = [
        {
            "nombre": "PD Ciencias",
            "slug": "pd-ciencias",
            "indicadores": [
                {
                    "codigo": "PD-CNAT-IN111",
                    "nombre": "(Re)diseño curricular",
                    "tipo": "Cuantitativo (Porcentual)"
                },
                {
                    "codigo": "PD-CNAT-IN122",
                    "nombre": "Grado de satisfacción de egresados/as",
                    "tipo": "Cuantitativo (Porcentual)"
                },
            ]
        },
        {
            "nombre": "PD Ingeniería",
            "slug": "pd-ingenieria",
            "indicadores": []
        },
        {
            "nombre": "PD Educación",
            "slug": "pd-educacion",
            "indicadores": [
                {
                    "codigo": "PD-EDU-IN101",
                    "nombre": "Nivel de implementación del plan curricular",
                    "tipo": "Cualitativo"
                }
            ]
        },
        {
            "nombre": "Indicadores Transversales (PEI)",
            "slug": "pei",
            "indicadores": [
                {
                    "codigo": "PEI-TRA-IN111",
                    "nombre": "Cumplimiento del plan estratégico institucional",
                    "tipo": "Cuantitativo"
                }
            ]
        },
    ]

    return render(request, 'planificacion/indicadores.html', {
        'areas': areas
    })



@login_required
def desafios(request):
    return render(request, 'planificacion/desafios.html')




def lista_indicadores(request):
    areas = Programa.objects.prefetch_related("indicadores")

    es_planificacion = request.user.groups.filter(
        name="Planificacion"
    ).exists()

    indicador_form = IndicadorForm()
    programa_form = ProgramaForm()

    if request.method == "POST":

        # 🔒 Bloquear creación si no es Planificacion
        if not es_planificacion:
            raise PermissionDenied

        form_type = request.POST.get("form_type")

        # =========================
        # CREAR INDICADOR
        # =========================
        if form_type == "indicador":
            indicador_form = IndicadorForm(request.POST)
            if indicador_form.is_valid():
                indicador_form.save()
                return redirect("planificacion:indicadores")

        # =========================
        # CREAR PROGRAMA
        # =========================
        elif form_type == "programa":
            programa_form = ProgramaForm(request.POST)
            if programa_form.is_valid():
                programa_form.save()
                return redirect("planificacion:indicadores")

    return render(request, "planificacion/lista_indicadores.html", {
        "areas": areas,
        "form": indicador_form,
        "programa_form": programa_form,
        "es_planificacion": es_planificacion
    })

@user_passes_test(es_planificacion)
@permission_required('planificacion.add_indicador', raise_exception=True)
def crear_indicador(request):
    if request.method == 'POST':
        form = IndicadorForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('planificacion:lista_indicadores')
    else:
        form = IndicadorForm()

    return render(request, 'planificacion/crear_indicador.html', {
        'form': form
    })

@user_passes_test(es_planificacion)
@permission_required('planificacion.change_indicador', raise_exception=True)
def editar_indicador(request, id):
    indicador = get_object_or_404(Indicador, id=id)

    if request.method == 'POST':
        form = IndicadorForm(request.POST, instance=indicador)
        if form.is_valid():
            form.save()
            return redirect('planificacion:lista_indicadores')
    else:
        form = IndicadorForm(instance=indicador)

    return render(request, 'planificacion/editar_indicador.html', {
        'form': form,
        'indicador': indicador
    })


@permission_required('planificacion.delete_indicador', raise_exception=True)
@user_passes_test(es_planificacion)
def eliminar_indicador(request, id):
    indicador = get_object_or_404(Indicador, id=id)

    if request.method == 'POST':
        indicador.delete()
        return redirect('planificacion:indicadores')

    return render(request, 'planificacion/eliminar_indicador.html', {
        'indicador': indicador
    })

def planificacion_home(request):
    programas = Programa.objects.all().prefetch_related("indicadores")

    return render(request, "planificacion/home.html", {
        "programas": programas,
        "es_planificacion": True,
    })


@user_passes_test(es_planificacion)
def crear_programa(request):
    if request.method == 'POST':
        form = ProgramaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('planificacion:indicadores')
    else:
        form = ProgramaForm()

    return render(request, 'planificacion/crear_programa.html', {
        'form': form
    })



@permission_required('planificacion.change_programa', raise_exception=True)
@user_passes_test(es_planificacion)
def editar_programa(request, id):
    programa = get_object_or_404(Programa, id=id)

    if request.method == "POST":
        programa.nombre = request.POST.get("nombre")
        programa.save()

    return redirect("planificacion:indicadores")


@require_POST
def eliminar_programa(request, pk):
    if not request.user.groups.filter(name="Planificacion").exists():
        raise PermissionDenied

    programa = get_object_or_404(Programa, pk=pk)
    programa.delete()

    return redirect("planificacion:indicadores")
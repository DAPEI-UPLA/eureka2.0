from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Indicador, Programa, TipoIndicador, Objetivo, Estrategia, ProgramaIndicador, SeguimientoIndicador
from django.contrib.auth.decorators import permission_required
from .forms import IndicadorForm, ProgramaForm, ObjetivoForm, EstrategiaForm, SeguimientoIndicadorForm
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
from decimal import Decimal
from django.db.models import Prefetch

@login_required
def index(request):
    return render(request, 'planificacion/index.html')

def es_planificacion(user):
    return user.groups.filter(name='Planificacion').exists()


@login_required
def desafios(request):
    return render(request, 'planificacion/desafios.html')




@login_required
def lista_indicadores(request):

    indicadores = Indicador.objects.select_related(
        "objetivo",
        "creado_por"
    )

    es_planificacion = request.user.groups.filter(
        name="Planificacion"
    ).exists()

    form = IndicadorForm()

    if request.method == "POST":

        if not es_planificacion:
            raise PermissionDenied

        form = IndicadorForm(request.POST)

        if form.is_valid():
            indicador = form.save(commit=False)
            indicador.creado_por = request.user
            indicador.save()
            return redirect("planificacion:indicadores")

    context = {
        "indicadores": indicadores,
        "form": form,
        "es_planificacion": es_planificacion
    }

    return render(
        request,
        "planificacion/lista_indicadores.html",
        context
    )



@login_required
def editar_indicador(request, pk):

    indicador = get_object_or_404(Indicador, pk=pk)

    if not request.user.groups.filter(name="Planificacion").exists():
        raise PermissionDenied

    if request.method == "POST":
        form = IndicadorForm(request.POST, instance=indicador)

        if form.is_valid():
            form.save()
            return redirect("planificacion:indicadores")
        else:
            print(form.errors)  # 👈 MUY IMPORTANTE

    return redirect("planificacion:indicadores")

@login_required
def eliminar_indicador(request, pk):

    indicador = get_object_or_404(Indicador, pk=pk)

    if not request.user.groups.filter(name="Planificacion").exists():
        raise PermissionDenied

    if request.method == "POST":
        indicador.delete()
        return redirect("planificacion:indicadores")

    return render(request, "planificacion/eliminar_indicador.html", {
        "indicador": indicador
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



@login_required
def lista_objetivos(request):

    objetivos = Objetivo.objects.prefetch_related(
        "programas_asociados"  # 🔥 CORREGIDO
    ).select_related("creado_por")

    estrategicos = objetivos.filter(
        tipo=Objetivo.TipoObjetivo.ESTRATEGICO
    )

    especificos = objetivos.filter(
        tipo=Objetivo.TipoObjetivo.ESPECIFICO
    )

    es_planificacion = request.user.groups.filter(
        name="Planificacion"
    ).exists()

    form = ObjetivoForm()

    if request.method == "POST":

        if not es_planificacion:
            raise PermissionDenied

        form = ObjetivoForm(request.POST)

        if form.is_valid():
            objetivo = form.save(commit=False)
            objetivo.creado_por = request.user
            objetivo.save()
            form.save_m2m()

            return redirect("planificacion:lista_objetivos")

    context = {
        "estrategicos": estrategicos,
        "especificos": especificos,
        "form": form,
        "es_planificacion": es_planificacion,
    }

    return render(
        request,
        "planificacion/lista_objetivos.html",
        context
    )


@login_required
def lista_estrategias(request):

    estrategias = Estrategia.objects.select_related(
        "indicador",
        "creado_por"
    )

    es_planificacion = request.user.groups.filter(
        name="Planificacion"
    ).exists()

    form = EstrategiaForm()

    if request.method == "POST":

        if not es_planificacion:
            raise PermissionDenied

        form = EstrategiaForm(request.POST)

        if form.is_valid():
            estrategia = form.save(commit=False)
            estrategia.creado_por = request.user
            estrategia.save()
            return redirect("planificacion:estrategias")

    context = {
        "estrategias": estrategias,
        "form": form,
        "es_planificacion": es_planificacion,
    }

    return render(request, "planificacion/lista_estrategias.html", context)

@login_required
def editar_estrategia(request, pk):

    estrategia = get_object_or_404(Estrategia, pk=pk)

    es_planificacion = request.user.groups.filter(
        name="Planificacion"
    ).exists()

    if not es_planificacion:
        raise PermissionDenied

    if request.method == "POST":
        form = EstrategiaForm(request.POST, instance=estrategia)

        if form.is_valid():
            form.save()
            return redirect("planificacion:estrategias")

    else:
        form = EstrategiaForm(instance=estrategia)

    context = {
        "form": form,
        "estrategia": estrategia,
    }

    return render(
        request,
        "planificacion/editar_estrategia.html",
        context
    )


@login_required
def eliminar_estrategia(request, pk):

    estrategia = get_object_or_404(Estrategia, pk=pk)

    es_planificacion = request.user.groups.filter(
        name="Planificacion"
    ).exists()

    if not es_planificacion:
        raise PermissionDenied

    estrategia.delete()

    return redirect("planificacion:estrategias")


@login_required
def lista_programas(request):

    programas = Programa.objects.prefetch_related("objetivos")

    es_planificacion = request.user.groups.filter(
        name="Planificacion"
    ).exists()

    form = ProgramaForm()

    if request.method == "POST":

        if not es_planificacion:
            raise PermissionDenied

        form = ProgramaForm(request.POST)

        if form.is_valid():
            programa = form.save(commit=False)
            programa.creado_por = request.user
            programa.save()
            form.save_m2m()

            return redirect("planificacion:lista_programas")

    context = {
        "programas": programas,
        "form": form,
        "es_planificacion": es_planificacion,
    }

    return render(request, "planificacion/lista_programas.html", context)

#------------------



@login_required
def seguimiento_programa(request, pk):

    programa = get_object_or_404(
        Programa.objects.prefetch_related(
            "objetivos",
            "programas_indicadores__indicador__estrategias",
            "programas_indicadores__seguimientos"
        ),
        pk=pk
    )

    # =====================================================
    # 🔐 PERMISO
    # =====================================================
    es_planificacion = request.user.groups.filter(
        name="Planificacion"
    ).exists()

    # =====================================================
    # 🔥 MANEJO DE POST
    # =====================================================
    if request.method == "POST" and es_planificacion:

        accion = request.POST.get("accion")

        if accion == "agregar_objetivo":
            objetivo_id = request.POST.get("objetivo_id")
            if objetivo_id:
                programa.objetivos.add(objetivo_id)

        elif accion == "eliminar_objetivo":
            objetivo_id = request.POST.get("objetivo_id")
            if objetivo_id:
                programa.objetivos.remove(objetivo_id)

        elif accion == "agregar_indicador":
            indicador_id = request.POST.get("indicador_id")
            if indicador_id:
                ProgramaIndicador.objects.get_or_create(
                    programa=programa,
                    indicador_id=indicador_id
                )

        elif accion == "eliminar_indicador":
            indicador_id = request.POST.get("indicador_id")
            if indicador_id:
                ProgramaIndicador.objects.filter(
                    programa=programa,
                    indicador_id=indicador_id
                ).delete()

        return redirect(
            "planificacion:seguimiento_programa",
            pk=pk
        )

    # =====================================================
    # 📅 Año seleccionado
    # =====================================================
    anio = request.GET.get("anio")

    try:
        anio = int(anio) if anio else 2024
    except ValueError:
        anio = 2024

    anios = list(range(2024, 2031))

    # =====================================================
    # 🔓 OBJETIVO ABIERTO (NUEVO)
    # =====================================================
    objetivo_abierto = request.GET.get("objetivo_abierto")

    # =====================================================
    # 🎯 Datos para los modales
    # =====================================================
    objetivos_disponibles = Objetivo.objects.exclude(
        programas_asociados=programa
    )

    indicadores_disponibles = Indicador.objects.exclude(
        id__in=programa.programas_indicadores.values_list(
            "indicador_id",
            flat=True
        )
    )

    # =====================================================
    # 🔷 ESTRUCTURA OPTIMIZADA
    # =====================================================

    estructura = []

    indicadores_programa_ids = set(
        programa.programas_indicadores.values_list(
            "indicador_id",
            flat=True
        )
    )

    for objetivo in programa.objetivos.prefetch_related("indicadores").all():

        indicadores = []

        for indicador in objetivo.indicadores.filter(
            id__in=indicadores_programa_ids
        ):

            pi = programa.programas_indicadores.filter(
                indicador=indicador
            ).first()

            if not pi:
                continue

            seguimiento = pi.seguimientos.filter(anio=anio).first()
            valor = seguimiento.valor if seguimiento else None

            indicadores.append({
                "indicador": indicador,
                "meta": pi.meta,
                "linea_base": pi.linea_base_valor,
                "valor": valor,
                "estrategias": indicador.estrategias.all(),
            })

        estructura.append({
            "objetivo": objetivo,
            "indicadores": indicadores
        })

    # =====================================================
    # 📦 CONTEXT FINAL
    # =====================================================

    context = {
        "programa": programa,
        "estructura": estructura,
        "anio": anio,
        "anios": anios,
        "objetivos_disponibles": objetivos_disponibles,
        "indicadores_disponibles": indicadores_disponibles,
        "es_planificacion": es_planificacion,
        "objetivo_abierto": objetivo_abierto,   # 👈 NUEVO
    }

    return render(
        request,
        "planificacion/seguimiento_programa.html",
        context
    )



@login_required
def crear_seguimiento(request, pk):
    programa_indicador = get_object_or_404(ProgramaIndicador, pk=pk)

    if request.method == "POST":
        form = SeguimientoIndicadorForm(request.POST)
        if form.is_valid():
            seguimiento = form.save(commit=False)
            seguimiento.programa_indicador = programa_indicador
            seguimiento.save()
            return redirect("planificacion:seguimiento_programa",
                            pk=programa_indicador.programa.id)
    else:
        form = SeguimientoIndicadorForm()

    return render(request, "planificacion/crear_seguimiento.html", {
        "form": form,
        "pi": programa_indicador
    })


@login_required
def agregar_indicador_programa(request, pk):

    programa = get_object_or_404(Programa, pk=pk)

    if request.method == "POST":
        indicador_id = request.POST.get("indicador")

        ProgramaIndicador.objects.get_or_create(
            programa=programa,
            indicador_id=indicador_id
        )

    return redirect("planificacion:detalle_programa", pk=pk)
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ..models import Actividad, Gasto, GastoElegible, Resultado, TipoGasto


@login_required
def cargar_resultados(request):
    objetivo_id = request.GET.get("objetivo")
    resultados = Resultado.objects.filter(objetivo_id=objetivo_id)
    return render(request, "proyectos/partials/resultados_options.html", {
        "resultados": resultados,
    })


@login_required
def cargar_actividades(request):
    resultado_id = request.GET.get("resultado")
    actividades = Actividad.objects.filter(resultado_id=resultado_id)
    return render(request, "proyectos/partials/actividades_options.html", {
        "actividades": actividades,
    })


@login_required
def cargar_tipos_gasto(request):
    transferencia_id = request.GET.get("transferencia")
    tipos = TipoGasto.objects.filter(transferencia_id=transferencia_id)
    return render(request, "proyectos/partials/tipos_gasto_options.html", {
        "tipos_gasto": tipos,
    })


@login_required
def cargar_gastos(request):
    tipo_gasto_id = request.GET.get("tipo_gasto")
    gastos = Gasto.objects.filter(tipo_gasto_id=tipo_gasto_id)
    return render(request, "proyectos/partials/gastos_options.html", {
        "gastos": gastos,
    })


@login_required
def cargar_gastos_elegibles(request):
    gasto_id = request.GET.get("gasto")
    elegibles = GastoElegible.objects.filter(gasto_id=gasto_id)
    return render(request, "proyectos/partials/gastos_elegibles_options.html", {
        "gastos_elegibles": elegibles,
    })

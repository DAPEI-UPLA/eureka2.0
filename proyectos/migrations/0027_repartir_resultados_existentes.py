"""Lleva el presupuesto de los resultados ya cargados al primer año.

Mismo criterio que la 0021 y la 0025: se concentra todo en el primer año en vez
de inventar una distribución. El reparto real lo hace cada equipo.

El año elegido es el del reparto de **su objetivo**, no el primero del proyecto:
un resultado no puede tener plata en un año en que su objetivo no tiene nada, y
si el objetivo quedó concentrado en el año 1, ahí es donde cabe el resultado.
Los que no encuentren un año con presupuesto en su objetivo se dejan sin
repartir, conservando su total, para que se resuelvan a mano.
"""

from django.db import migrations


def repartir(apps, schema_editor):
    Resultado = apps.get_model("proyectos", "Resultado")
    PresupuestoObjetivoAnual = apps.get_model("proyectos", "PresupuestoObjetivoAnual")
    PresupuestoResultadoAnual = apps.get_model("proyectos", "PresupuestoResultadoAnual")

    # El primer año con asignación de cada objetivo.
    anio_del_objetivo = {}
    for fila in PresupuestoObjetivoAnual.objects.select_related("anio").order_by(
        "objetivo_id", "anio__numero_anio"
    ):
        anio_del_objetivo.setdefault(fila.objetivo_id, fila.anio_id)

    resultados = Resultado.objects.filter(
        eliminado=False, objetivo__eliminado=False
    )
    for resultado in resultados:
        corriente = resultado.presupuesto_corriente or 0
        capital = resultado.presupuesto_capital or 0
        if not corriente and not capital:
            continue

        anio_id = anio_del_objetivo.get(resultado.objetivo_id)
        if anio_id is None:
            continue

        PresupuestoResultadoAnual.objects.get_or_create(
            resultado=resultado,
            anio_id=anio_id,
            defaults={
                "presupuesto_corriente": corriente,
                "presupuesto_capital": capital,
            },
        )


def deshacer(apps, schema_editor):
    apps.get_model("proyectos", "PresupuestoResultadoAnual").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("proyectos", "0026_presupuesto_resultado_anual"),
    ]

    operations = [
        migrations.RunPython(repartir, deshacer),
    ]

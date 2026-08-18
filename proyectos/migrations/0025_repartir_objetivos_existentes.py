"""Lleva el presupuesto de los objetivos ya cargados al primer año.

Mismo criterio que la 0021 con el presupuesto del proyecto: el reparto real lo
sabe cada equipo, así que se concentra todo en el primer año del proyecto en vez
de inventar una distribución. Un año concentrado se ve provisorio; uno repartido
en partes iguales se ve legítimo y nadie lo corregiría.

Los objetivos en cero no reciben fila: no hay nada que repartir y una fila vacía
sólo ensuciaría la pantalla.
"""

from django.db import migrations


def repartir(apps, schema_editor):
    ObjetivoEspecifico = apps.get_model("proyectos", "ObjetivoEspecifico")
    PresupuestoAnual = apps.get_model("proyectos", "PresupuestoAnual")
    PresupuestoObjetivoAnual = apps.get_model("proyectos", "PresupuestoObjetivoAnual")

    primeros = {}
    for anio in PresupuestoAnual.objects.order_by("proyecto_id", "numero_anio"):
        primeros.setdefault(anio.proyecto_id, anio)

    objetivos = ObjetivoEspecifico.objects.filter(eliminado=False).exclude(
        proyecto__isnull=True
    )
    for objetivo in objetivos:
        corriente = objetivo.presupuesto_corriente or 0
        capital = objetivo.presupuesto_capital or 0
        if not corriente and not capital:
            continue

        anio = primeros.get(objetivo.proyecto_id)
        if anio is None:
            # Proyecto sin reparto anual: no hay dónde colgarlo. El objetivo
            # conserva su total y se repartirá cuando el proyecto tenga años.
            continue

        PresupuestoObjetivoAnual.objects.get_or_create(
            objetivo=objetivo,
            anio=anio,
            defaults={
                "presupuesto_corriente": corriente,
                "presupuesto_capital": capital,
            },
        )


def deshacer(apps, schema_editor):
    """Borra el reparto por objetivo.

    Los totales de cada objetivo quedan como estén: son columnas propias y no
    se recalculan al revertir, así que no se pierde el monto.
    """
    apps.get_model("proyectos", "PresupuestoObjetivoAnual").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("proyectos", "0024_presupuesto_objetivo_anual"),
    ]

    operations = [
        migrations.RunPython(repartir, deshacer),
    ]

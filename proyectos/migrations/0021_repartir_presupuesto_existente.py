"""Le da un reparto anual de partida a los proyectos que ya existían.

Todos los proyectos cargados son multianuales, pero su presupuesto vivía en un
único par de montos (corriente/capital) sin decir cuánto tocaba cada año. No
hay forma de adivinar el reparto real —eso lo sabe el equipo de cada
proyecto—, así que se crea un solo «Año 1» con el presupuesto completo y desde
la pantalla se abre en los años que corresponda.

Se elige así, y no repartiendo en partes iguales, porque un reparto inventado
se ve legítimo: nadie lo corregiría y todos los indicadores saldrían de una
línea base falsa. Un único año concentrado es visiblemente provisorio.

El año calendario sale de los datos: la fecha de inicio si está, si no el año
más antiguo de sus planes de gasto, y como último recurso el año en curso.
"""

from datetime import date

from django.db import migrations


def repartir(apps, schema_editor):
    Proyecto = apps.get_model("proyectos", "Proyecto")
    PlanDeGasto = apps.get_model("proyectos", "PlanDeGasto")
    PresupuestoAnual = apps.get_model("proyectos", "PresupuestoAnual")

    for proyecto in Proyecto.objects.all():
        if proyecto.presupuestos_anuales.exists():
            continue

        if proyecto.fecha_inicio:
            anio = proyecto.fecha_inicio.year
        else:
            primero = (
                PlanDeGasto.objects
                .filter(
                    actividad__resultado__objetivo__proyecto_id=proyecto.id
                )
                .order_by("anio")
                .values_list("anio", flat=True)
                .first()
            )
            anio = primero or date.today().year

        PresupuestoAnual.objects.create(
            proyecto=proyecto,
            numero_anio=1,
            anio_calendario=anio,
            presupuesto_corriente=proyecto.presupuesto_corriente or 0,
            presupuesto_capital=proyecto.presupuesto_capital or 0,
        )


def deshacer(apps, schema_editor):
    """Borra el reparto anual completo.

    Cuidado: se lleva también los años que se hayan cargado a mano después de
    la migración, no sólo los que ésta creó.
    """
    apps.get_model("proyectos", "PresupuestoAnual").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("proyectos", "0020_presupuesto_anual"),
    ]

    operations = [
        migrations.RunPython(repartir, deshacer),
    ]

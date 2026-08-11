"""La actividad pasa a distinguir corriente de capital, y a registrar cuándo
terminó de verdad.

El monto que hoy tiene cada actividad en `presupuesto` se traspasa completo a
`presupuesto_corriente`: es el supuesto conservador, porque hasta ahora el campo
no distinguía y el gasto corriente es el habitual en estos proyectos. Las
actividades que en realidad ejecutan capital hay que reasignarlas a mano — la
migración inversa vuelve a sumar ambos montos en un único campo, así que nada se
pierde al revertir.
"""

from django.db import migrations, models


def separar_presupuesto(apps, schema_editor):
    Actividad = apps.get_model("proyectos", "Actividad")
    Actividad.objects.update(presupuesto_corriente=models.F("presupuesto"))


def reunir_presupuesto(apps, schema_editor):
    Actividad = apps.get_model("proyectos", "Actividad")
    Actividad.objects.update(
        presupuesto=models.F("presupuesto_corriente") + models.F("presupuesto_capital")
    )


class Migration(migrations.Migration):

    dependencies = [
        ("proyectos", "0016_inicializar_orden"),
    ]

    operations = [
        migrations.AddField(
            model_name="actividad",
            name="fecha_efectiva",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="actividad",
            name="presupuesto_corriente",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name="actividad",
            name="presupuesto_capital",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.RunPython(separar_presupuesto, reunir_presupuesto),
        migrations.RemoveField(
            model_name="actividad",
            name="presupuesto",
        ),
    ]

"""Fija la línea base de las actividades que ya existían.

`fecha_limite_original` es la primera fecha que tuvo la actividad, y de ahí en
adelante no se mueve. Para las que ya estaban cargadas no hay forma de saber si
la fecha que tienen hoy es la original o una ya reprogramada: no se guardaba
historial. Se toma la vigente como compromiso, que es lo único defendible.

Consecuencia a tener presente: los arrastres anteriores a esta migración no
aparecen. El conteo de actividades arrastradas empieza a correr desde hoy, no
desde el inicio de los proyectos.
"""

from django.db import migrations
from django.db.models import F


def fijar(apps, schema_editor):
    Actividad = apps.get_model("proyectos", "Actividad")
    Actividad.objects.filter(
        fecha_limite__isnull=False,
        fecha_limite_original__isnull=True,
    ).update(fecha_limite_original=F("fecha_limite"))


def deshacer(apps, schema_editor):
    apps.get_model("proyectos", "Actividad").objects.update(
        fecha_limite_original=None
    )


class Migration(migrations.Migration):

    dependencies = [
        ("proyectos", "0022_arrastre_de_actividades"),
    ]

    operations = [
        migrations.RunPython(fijar, deshacer),
    ]

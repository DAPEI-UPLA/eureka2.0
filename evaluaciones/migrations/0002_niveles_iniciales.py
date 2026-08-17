"""Trae los niveles requeridos que ya se habían editado en el prototipo.

El prototipo guardaba estos valores en `requerido_overrides.json`, dentro del
código de la app. Ese archivo se conservó en `datos/requerido_inicial.json` y
acá se vuelca a la tabla; después de esto ya nadie lo lee.

Si el archivo no está (una instalación limpia que no arrastra el prototipo), la
migración no hace nada: no hay nada que rescatar.
"""

import json
import pathlib

from django.db import migrations

ARCHIVO = pathlib.Path(__file__).resolve().parent.parent / "datos" / "requerido_inicial.json"


def cargar(apps, schema_editor):
    if not ARCHIVO.is_file():
        return

    NivelRequerido = apps.get_model("evaluaciones", "NivelRequerido")
    datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))

    filas = [
        NivelRequerido(ruta=ruta, clave=clave, nivel=int(nivel))
        for ruta, items in datos.items()
        for clave, nivel in items.items()
    ]
    # ignore_conflicts: si la migración se reaplica sobre datos ya editados en
    # pantalla, se respeta lo editado en vez de devolverlo al valor del archivo.
    NivelRequerido.objects.bulk_create(filas, ignore_conflicts=True)


def borrar(apps, schema_editor):
    if not ARCHIVO.is_file():
        return
    NivelRequerido = apps.get_model("evaluaciones", "NivelRequerido")
    datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    NivelRequerido.objects.filter(ruta__in=list(datos)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("evaluaciones", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(cargar, borrar),
    ]

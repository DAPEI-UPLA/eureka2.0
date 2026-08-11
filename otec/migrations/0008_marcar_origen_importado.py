"""Marca como importados los registros que existían antes del campo ``origen``.

Todo lo que había en la base a esta altura entró por ``otec_importar_tablero``:
el alta manual recién se agrega en esta misma tanda de cambios. Sin esto, esos
registros quedarían como "creados en el sistema" y el importador dejaría de
podarlos cuando desaparecen del Excel.
"""

from django.db import migrations


def marcar_importados(apps, schema_editor):
    for modelo in ("Propuesta", "Actividad"):
        apps.get_model("otec", modelo).objects.update(origen="IMPORTADO")


def revertir(apps, schema_editor):
    for modelo in ("Propuesta", "Actividad"):
        apps.get_model("otec", modelo).objects.update(origen="MANUAL")


class Migration(migrations.Migration):

    dependencies = [
        ("otec", "0007_actividad_origen_propuesta_origen"),
    ]

    operations = [
        migrations.RunPython(marcar_importados, revertir),
    ]

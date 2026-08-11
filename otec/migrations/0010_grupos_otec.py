"""Crea los grupos del equipo OTEC.

Son los que definen quién aparece en la carga laboral: «Encargado OTEC» y
«Profesional OTEC». No se les asignan permisos acá — hoy solo sirven para
identificar al equipo y repartir el trabajo.
"""

from django.db import migrations

from otec.models import GRUPO_ENCARGADO, GRUPO_PROFESIONAL


def crear_grupos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for nombre in (GRUPO_ENCARGADO, GRUPO_PROFESIONAL):
        Group.objects.get_or_create(name=nombre)


def borrar_grupos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=(GRUPO_ENCARGADO, GRUPO_PROFESIONAL)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("otec", "0009_actividad_responsables_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(crear_grupos, borrar_grupos),
    ]

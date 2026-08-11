from django.db import migrations


def crear_grupo(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="encargado_analisis")


def borrar_grupo(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="encargado_analisis").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("analisis", "0004_alter_movimientoinforme_tipo"),
        ("auth", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crear_grupo, borrar_grupo),
    ]

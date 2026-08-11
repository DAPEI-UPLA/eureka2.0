from django.db import migrations


# Antes de esta migración el orden de objetivos / resultados / actividades era
# simplemente el orden de inserción (id). Sembramos `orden` con esa misma
# secuencia para que nada cambie de sitio al desplegar; a partir de ahí el
# usuario puede reordenar con los botones ▲▼.
GRUPOS = [
    ("ObjetivoEspecifico", "proyecto_id"),
    ("Resultado", "objetivo_id"),
    ("Actividad", "resultado_id"),
]


def sembrar_orden(apps, schema_editor):
    for nombre_modelo, campo_padre in GRUPOS:
        Modelo = apps.get_model("proyectos", nombre_modelo)
        posicion_por_padre = {}
        for pk, padre_id in Modelo.objects.order_by(campo_padre, "id").values_list("pk", campo_padre):
            posicion = posicion_por_padre.get(padre_id, 0) + 1
            posicion_por_padre[padre_id] = posicion
            Modelo.objects.filter(pk=pk).update(orden=posicion)


def revertir(apps, schema_editor):
    for nombre_modelo, _ in GRUPOS:
        apps.get_model("proyectos", nombre_modelo).objects.update(orden=0)


class Migration(migrations.Migration):

    dependencies = [
        ("proyectos", "0015_alter_actividad_options_and_more"),
    ]

    operations = [
        migrations.RunPython(sembrar_orden, revertir),
    ]

from django.db import migrations, models


def copy_fk_to_m2m(apps, schema_editor):
    Estrategia = apps.get_model("planificacion", "Estrategia")
    for e in Estrategia.objects.all():
        if e.indicador_id:
            e.indicadores.add(e.indicador_id)


def copy_m2m_to_fk(apps, schema_editor):
    Estrategia = apps.get_model("planificacion", "Estrategia")
    for e in Estrategia.objects.all():
        primero = e.indicadores.first()
        if primero is not None:
            e.indicador_id = primero.id
            e.save(update_fields=["indicador"])


class Migration(migrations.Migration):

    dependencies = [
        ("planificacion", "0005_alter_objetivo_nombre"),
    ]

    operations = [
        migrations.AddField(
            model_name="estrategia",
            name="indicadores",
            field=models.ManyToManyField(
                blank=True,
                related_name="+",
                to="planificacion.indicador",
                verbose_name="Indicadores asociados",
            ),
        ),
        migrations.RunPython(copy_fk_to_m2m, copy_m2m_to_fk),
        migrations.RemoveField(
            model_name="estrategia",
            name="indicador",
        ),
        migrations.AlterField(
            model_name="estrategia",
            name="indicadores",
            field=models.ManyToManyField(
                blank=True,
                related_name="estrategias",
                to="planificacion.indicador",
                verbose_name="Indicadores asociados",
            ),
        ),
    ]

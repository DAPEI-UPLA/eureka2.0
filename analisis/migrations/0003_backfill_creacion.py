from django.db import migrations


def backfill_creacion(apps, schema_editor):
    Informe = apps.get_model("analisis", "Informe")
    Movimiento = apps.get_model("analisis", "MovimientoInforme")

    nuevos = []
    for informe in Informe.objects.all():
        if informe.movimientos.exists():
            continue
        nuevos.append(Movimiento(
            informe=informe,
            usuario=informe.responsable,
            tipo="CREACION",
            estado_nuevo=informe.estado,
            detalle="Registro inicial (backfill).",
        ))

    if nuevos:
        Movimiento.objects.bulk_create(nuevos)


def reverse(apps, schema_editor):
    Movimiento = apps.get_model("analisis", "MovimientoInforme")
    Movimiento.objects.filter(detalle="Registro inicial (backfill).").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("analisis", "0002_movimientoinforme"),
    ]

    operations = [
        migrations.RunPython(backfill_creacion, reverse),
    ]

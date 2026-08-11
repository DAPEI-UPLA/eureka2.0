"""Desglose de costos por categoría y horas asincrónicas del curso.

Los dos totales que traía la planilla —"Costo Relatoría" y "Otros gastos"—
pasan a ser el desglose: se crean primero las tablas nuevas, se copian los
montos ya cargados y recién entonces se sueltan las columnas viejas. El orden
importa: la migración automática borraba las columnas antes de leerlas.
"""

import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


def costos_al_desglose(apps, schema_editor):
    """Lo que estaba en las dos columnas pasa a relatoría y otros costos."""
    Actividad = apps.get_model("otec", "Actividad")
    CostoActividad = apps.get_model("otec", "CostoActividad")

    nuevos = [
        CostoActividad(
            actividad=actividad,
            relatoria=actividad.costo_relatoria or Decimal("0"),
            otros=actividad.otros_gastos or Decimal("0"),
        )
        for actividad in Actividad.objects.all()
        if actividad.costo_relatoria or actividad.otros_gastos
    ]
    CostoActividad.objects.bulk_create(nuevos)


def desglose_a_costos(apps, schema_editor):
    """Vuelta atrás: el detalle se aplana en los dos totales de antes."""
    CostoActividad = apps.get_model("otec", "CostoActividad")
    GastoExtra = apps.get_model("otec", "GastoExtra")

    categorias = [
        "relatoria", "materiales", "plataformas", "certificaciones",
        "traslados", "alimentacion", "arriendo", "otros",
    ]
    extras = {}
    for gasto in GastoExtra.objects.all():
        extras[gasto.actividad_id] = extras.get(gasto.actividad_id, Decimal("0")) + gasto.monto

    for costo in CostoActividad.objects.select_related("actividad"):
        total = sum((getattr(costo, c) for c in categorias), Decimal("0"))
        actividad = costo.actividad
        actividad.costo_relatoria = costo.relatoria
        actividad.otros_gastos = total - costo.relatoria + extras.get(actividad.pk, Decimal("0"))
        actividad.save(update_fields=["costo_relatoria", "otros_gastos"])


class Migration(migrations.Migration):

    dependencies = [
        ('otec', '0011_horarioclase'),
    ]

    operations = [
        migrations.AddField(
            model_name='actividad',
            name='horas_asincronicas',
            field=models.DecimalField(decimal_places=1, default=0, help_text='Cuántas de las horas del curso no se dictan en clase en vivo.', max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='Horas asincrónicas'),
        ),
        migrations.AlterField(
            model_name='actividad',
            name='horas',
            field=models.PositiveIntegerField(default=0, verbose_name='Horas totales del curso'),
        ),
        migrations.CreateModel(
            name='CostoActividad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('relatoria', models.DecimalField(decimal_places=2, default=0, max_digits=15, validators=[django.core.validators.MinValueValidator(Decimal('0'))])),
                ('materiales', models.DecimalField(decimal_places=2, default=0, max_digits=15, validators=[django.core.validators.MinValueValidator(Decimal('0'))])),
                ('plataformas', models.DecimalField(decimal_places=2, default=0, max_digits=15, validators=[django.core.validators.MinValueValidator(Decimal('0'))])),
                ('certificaciones', models.DecimalField(decimal_places=2, default=0, max_digits=15, validators=[django.core.validators.MinValueValidator(Decimal('0'))])),
                ('traslados', models.DecimalField(decimal_places=2, default=0, max_digits=15, validators=[django.core.validators.MinValueValidator(Decimal('0'))])),
                ('alimentacion', models.DecimalField(decimal_places=2, default=0, max_digits=15, validators=[django.core.validators.MinValueValidator(Decimal('0'))])),
                ('arriendo', models.DecimalField(decimal_places=2, default=0, max_digits=15, validators=[django.core.validators.MinValueValidator(Decimal('0'))])),
                ('otros', models.DecimalField(decimal_places=2, default=0, max_digits=15, validators=[django.core.validators.MinValueValidator(Decimal('0'))])),
                ('editado_en_sistema', models.BooleanField(default=False, help_text='Marcado cuando alguien detalló los costos desde la aplicación. La importación del Excel respeta ese desglose salvo que se pida sobrescribirlo: la planilla solo trae dos totales y volcarlos encima borraría el detalle.')),
                ('actividad', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='costos', to='otec.actividad')),
            ],
            options={
                'verbose_name': 'costos de la actividad',
                'verbose_name_plural': 'costos de las actividades',
            },
        ),
        migrations.CreateModel(
            name='GastoExtra',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('descripcion', models.CharField(max_length=200, verbose_name='Glosa del gasto')),
                ('monto', models.DecimalField(decimal_places=2, default=0, max_digits=15, validators=[django.core.validators.MinValueValidator(Decimal('0'))])),
                ('actividad', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gastos_extra', to='otec.actividad')),
            ],
            options={
                'verbose_name': 'gasto extra',
                'verbose_name_plural': 'gastos extras',
                'ordering': ['id'],
            },
        ),
        migrations.RunPython(costos_al_desglose, desglose_a_costos),
        migrations.RemoveField(
            model_name='actividad',
            name='costo_relatoria',
        ),
        migrations.RemoveField(
            model_name='actividad',
            name='otros_gastos',
        ),
    ]

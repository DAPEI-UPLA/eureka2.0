from django.db import migrations, models


def ejecutado_a_pagado(apps, schema_editor):
    Egreso = apps.get_model('proyectos', 'Egreso')
    Egreso.objects.filter(estado='EJECUTADO').update(estado='PAGADO')


def pagado_a_ejecutado(apps, schema_editor):
    Egreso = apps.get_model('proyectos', 'Egreso')
    Egreso.objects.filter(estado='PAGADO').update(estado='EJECUTADO')


class Migration(migrations.Migration):

    dependencies = [
        ('proyectos', '0010_egreso_estado'),
    ]

    operations = [
        migrations.RunPython(ejecutado_a_pagado, pagado_a_ejecutado),
        migrations.AlterField(
            model_name='egreso',
            name='estado',
            field=models.CharField(
                choices=[('COMPROMETIDO', 'Comprometido'), ('PAGADO', 'Pagado')],
                default='COMPROMETIDO',
                max_length=15,
            ),
        ),
    ]

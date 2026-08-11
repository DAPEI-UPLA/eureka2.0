"""Cada cuota de un honorario pasa a tener su propio monto.

Con una sola `cuota_mensual` no había forma de repartir un total que no se
divide en pesos exactos ($5.000.000 en 9 cuotas), ni de hacer un anticipo mayor
que el resto: siempre sobraban o faltaban unos pesos.

No hace falta migrar datos: los honorarios ya cargados quedan con la lista
vacía, y eso significa «todas las cuotas iguales a `cuota_mensual`», que es
exactamente lo que eran. La primera vez que se editen quedan detalladas.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proyectos', '0018_documentos_de_compra_y_naturaleza'),
    ]

    operations = [
        migrations.AddField(
            model_name='egreso',
            name='cuotas',
            field=models.JSONField(blank=True, default=list, help_text='Un monto por cuota, en orden. Vacío = todas iguales.', verbose_name='Monto de cada cuota'),
        ),
    ]

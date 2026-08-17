"""Documentos del gasto (SC/OC/Factura) y bolsa de cada transferencia.

Tres cambios que van juntos porque los tres apuntan a lo mismo — que el gasto
registrado se pueda seguir y se descuente de donde corresponde:

  * `Egreso` guarda los folios de solicitud de compra, orden de compra y
    factura, que hasta ahora sólo cabían en el campo de observaciones.
  * `Transferencia` declara si es corriente o de capital. El catálogo ya lo
    decía en el nombre, pero como dato suelto: nadie podía separar lo gastado
    en las dos bolsas en que sí está separado el presupuesto. Se rellena desde
    el nombre, que es exactamente «Corriente» y «Capital» en el catálogo.
  * Se elimina `PlanDeGasto.ejecutado`. Era una columna que ningún formulario
    escribía, así que valía $0 siempre, y de ella colgaba el ejecutado del
    resultado: un gasto marcado «Pagado» no aparecía por ningún lado. Ahora se
    calcula desde los gastos cargados al plan. Se borra al final, después de
    rellenar la naturaleza, para no dejar la BD a medio camino si algo falla.
"""

from django.db import migrations, models


def nombre_a_naturaleza(apps, schema_editor):
    Transferencia = apps.get_model("proyectos", "Transferencia")
    Transferencia.objects.filter(nombre__icontains="capital").update(
        naturaleza="CAPITAL"
    )


def naturaleza_a_nada(apps, schema_editor):
    """Vuelta atrás: el nombre sigue estando, no hay nada que restaurar."""


class Migration(migrations.Migration):

    dependencies = [
        ('proyectos', '0017_actividad_corriente_capital_y_fecha_efectiva'),
    ]

    operations = [
        migrations.AddField(
            model_name='egreso',
            name='solicitud_compra',
            field=models.CharField(blank=True, max_length=50, verbose_name='Solicitud de compra (SC)'),
        ),
        migrations.AddField(
            model_name='egreso',
            name='orden_compra',
            field=models.CharField(blank=True, max_length=50, verbose_name='Orden de compra (OC)'),
        ),
        migrations.AddField(
            model_name='egreso',
            name='factura',
            field=models.CharField(blank=True, max_length=50, verbose_name='Factura'),
        ),
        migrations.AddField(
            model_name='transferencia',
            name='naturaleza',
            field=models.CharField(choices=[('CORRIENTE', 'Corriente'), ('CAPITAL', 'Capital')], default='CORRIENTE', help_text='A qué presupuesto se descuenta lo que se gaste en esta transferencia.', max_length=10, verbose_name='Bolsa presupuestaria'),
        ),
        migrations.RunPython(nombre_a_naturaleza, naturaleza_a_nada),
        migrations.RemoveField(
            model_name='plandegasto',
            name='ejecutado',
        ),
    ]

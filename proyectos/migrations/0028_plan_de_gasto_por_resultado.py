"""El plan de gasto pasa a colgar del resultado, y la actividad pierde su monto.

El dinero se compromete a nivel de resultado y se detiene ahí. Las actividades
son el medio para cumplirlo y pueden cambiar, fusionarse o aparecer sobre la
marcha: si el POA colgara de ellas, reordenar el trabajo borraría la
planificación financiera.

Se escribe a mano en vez de dejar que `makemigrations` pregunte por un default,
porque el campo nuevo se puede deducir de los datos: el resultado de un plan es
el de su actividad. Con 0 planes cargados el backfill no toca nada, pero queda
escrito para que la migración sea correcta en cualquier base.

La actividad queda opcional y con SET_NULL: borrarla ya no puede llevarse por
delante una línea del POA.
"""

from django.db import migrations, models
import django.db.models.deletion


def poner_el_resultado(apps, schema_editor):
    """El resultado de cada plan es el de su actividad."""
    PlanDeGasto = apps.get_model("proyectos", "PlanDeGasto")
    for plan in PlanDeGasto.objects.select_related("actividad").all():
        if plan.actividad_id and not plan.resultado_id:
            plan.resultado_id = plan.actividad.resultado_id
            plan.save(update_fields=["resultado"])


def sin_vuelta(apps, schema_editor):
    """Al revertir, la actividad vuelve a ser obligatoria.

    Un plan sin actividad no puede reconstruirla —la información no existe—,
    así que esos quedarían inválidos. Con 0 planes cargados da lo mismo; si
    algún día hay datos, revisar antes de revertir.
    """
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("proyectos", "0027_repartir_resultados_existentes"),
    ]

    operations = [
        # 1. El vínculo nuevo, primero opcional para poder rellenarlo.
        migrations.AddField(
            model_name="plandegasto",
            name="resultado",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="planes_gasto",
                to="proyectos.resultado",
            ),
        ),
        migrations.RunPython(poner_el_resultado, sin_vuelta),
        migrations.AlterField(
            model_name="plandegasto",
            name="resultado",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="planes_gasto",
                to="proyectos.resultado",
            ),
        ),

        # 2. La actividad pasa a ser una referencia opcional.
        migrations.AlterField(
            model_name="plandegasto",
            name="actividad",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="planes_gasto",
                to="proyectos.actividad",
                help_text="Opcional: para qué actividad es este gasto.",
            ),
        ),

        # 3. La identidad de una línea del POA es resultado + gasto + año.
        migrations.RemoveConstraint(
            model_name="plandegasto",
            name="uniq_plan_actividad_gasto_anio",
        ),
        migrations.AddConstraint(
            model_name="plandegasto",
            constraint=models.UniqueConstraint(
                fields=("resultado", "gasto_elegible", "anio"),
                name="uniq_plan_resultado_gasto_anio",
            ),
        ),
        migrations.AlterModelOptions(
            name="plandegasto",
            options={"ordering": ["-anio", "resultado_id"]},
        ),

        # 4. La actividad deja de llevar presupuesto.
        migrations.RemoveField(model_name="actividad", name="presupuesto_corriente"),
        migrations.RemoveField(model_name="actividad", name="presupuesto_capital"),
    ]

"""Las clases dejan de ser una regla semanal y pasan a guardarse una por una.

``HorarioClase`` describía un patrón ("martes 13:30, 3 h") y las sesiones se
calculaban al dibujar. Las fechas reales las pone el relator y casi nunca
siguen un patrón, así que cada clase pasa a ser una fila con su fecha y su
hora.

Las reglas que ya estaban cargadas se **expanden**: se recorren las fechas que
la regla habría generado entre el inicio y el término del curso, saltando
feriados, y cada una queda como una clase editable. Se expande antes de borrar
el modelo viejo, que es lo que la migración automática hacía al revés.
"""

from datetime import timedelta
from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def fechas_de_la_regla(horario, actividad, feriados):
    """Las fechas que la regla semanal habría generado."""
    inicio = actividad.fecha_inicio
    if not inicio or not horario.dias:
        return []
    fin = actividad.fecha_termino or inicio
    if fin < inicio:
        return []

    dias = {int(d) for d in horario.dias if d.isdigit()}
    fechas, actual = [], inicio
    while actual <= fin:
        if actual.weekday() in dias and actual not in feriados:
            fechas.append(actual)
        actual += timedelta(days=1)
    return fechas


def reglas_a_sesiones(apps, schema_editor):
    HorarioClase = apps.get_model("otec", "HorarioClase")
    SesionClase = apps.get_model("otec", "SesionClase")
    DiaActividad = apps.get_model("otec", "DiaActividad")
    Feriado = apps.get_model("otec", "Feriado")

    feriados = set(Feriado.objects.values_list("fecha", flat=True))

    nuevas, vistas = [], set()
    for horario in HorarioClase.objects.select_related("actividad"):
        for fecha in fechas_de_la_regla(horario, horario.actividad, feriados):
            # Dos reglas del mismo grupo pueden pisarse en un mismo día y hora;
            # la clase es una sola.
            llave = (horario.actividad_id, fecha, horario.hora_inicio, horario.grupo)
            if llave in vistas:
                continue
            vistas.add(llave)
            nuevas.append(SesionClase(
                actividad_id=horario.actividad_id,
                fecha=fecha,
                hora_inicio=horario.hora_inicio,
                duracion_horas=horario.duracion_horas,
                sala_id=horario.sala_id,
                grupo=horario.grupo,
            ))
    SesionClase.objects.bulk_create(nuevas)

    # Cada clase marca su día en la carta Gantt, que es la regla nueva.
    ya_marcados = set(
        DiaActividad.objects
        .filter(actividad_id__in={s.actividad_id for s in nuevas})
        .values_list("actividad_id", "fecha")
    )
    dias = []
    for actividad_id, fecha, _hora, _grupo in vistas:
        if (actividad_id, fecha) in ya_marcados:
            continue
        ya_marcados.add((actividad_id, fecha))
        dias.append(DiaActividad(actividad_id=actividad_id, fecha=fecha, tipo="E"))
    DiaActividad.objects.bulk_create(dias)


def sesiones_a_reglas(apps, schema_editor):
    """Vuelta atrás: se reconstruye una regla por patrón observado.

    Es necesariamente aproximada — de eso se trataba el cambio: un curso con
    clases en días sueltos no cabe en una regla semanal. Se agrupan las clases
    que comparten curso, grupo, hora, duración y sala, y los días de la semana
    que aparezcan pasan a ser la recurrencia.
    """
    HorarioClase = apps.get_model("otec", "HorarioClase")
    SesionClase = apps.get_model("otec", "SesionClase")

    patrones = {}
    for sesion in SesionClase.objects.all():
        llave = (
            sesion.actividad_id, sesion.grupo, sesion.hora_inicio,
            sesion.duracion_horas, sesion.sala_id,
        )
        patrones.setdefault(llave, set()).add(sesion.fecha.weekday())

    HorarioClase.objects.bulk_create([
        HorarioClase(
            actividad_id=actividad_id,
            grupo=grupo,
            dias="".join(str(d) for d in sorted(dias)),
            hora_inicio=hora,
            duracion_horas=duracion,
            sala_id=sala_id,
        )
        for (actividad_id, grupo, hora, duracion, sala_id), dias in patrones.items()
    ])


class Migration(migrations.Migration):

    dependencies = [
        ('otec', '0012_desglose_costos_y_horas_asincronicas'),
    ]

    operations = [
        migrations.CreateModel(
            name='SesionClase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField(db_index=True)),
                ('hora_inicio', models.TimeField()),
                ('duracion_horas', models.DecimalField(decimal_places=1, default=Decimal('2.0'), max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal('0.5'))], verbose_name='Duración (horas)')),
                ('grupo', models.CharField(blank=True, help_text='Solo si el curso dicta más de un grupo en paralelo, p. ej. «AP».', max_length=40)),
                ('actividad', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sesiones', to='otec.actividad')),
                ('sala', models.ForeignKey(blank=True, help_text='Vacío si la clase no ocupa una sala Zoom.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sesiones', to='otec.salazoom')),
            ],
            options={
                'verbose_name': 'sesión de clases',
                'verbose_name_plural': 'sesiones de clases',
                'ordering': ['fecha', 'hora_inicio'],
            },
        ),
        migrations.AddConstraint(
            model_name='sesionclase',
            constraint=models.UniqueConstraint(fields=('actividad', 'fecha', 'hora_inicio', 'grupo'), name='otec_sesion_unica_por_actividad'),
        ),
        migrations.RunPython(reglas_a_sesiones, sesiones_a_reglas),
        migrations.DeleteModel(
            name='HorarioClase',
        ),
    ]

"""Convierte en clases las reservas de Zoom que trajo el Tablero.

Cada reserva con hora **ya es una clase**: día, hora de inicio, duración y
sala. Antes esto tenía que deducir una regla semanal a partir de ellas y se
rendía cuando el curso no seguía un patrón — que es justo lo que pasa cuando
las fechas las pone el relator. Ahora se copian tal cual, así que los cursos
con sesiones sueltas también quedan cargados.

    python manage.py otec_sesiones_desde_reservas [--dry-run] [--rehacer]
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from otec.models import Actividad, SesionClase


class Command(BaseCommand):
    help = "Carga las clases de cada curso desde sus reservas de Zoom."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--rehacer",
            action="store_true",
            help="Reemplaza las clases ya cargadas en vez de saltar el curso.",
        )

    def handle(self, *args, **options):
        creadas = saltados = sin_hora = 0
        detalle = []

        with transaction.atomic():
            for actividad in Actividad.objects.prefetch_related(
                "reservas_zoom__sala", "sesiones"
            ):
                reservas = [r for r in actividad.reservas_zoom.all() if r.hora_inicio]
                if not reservas:
                    continue

                if actividad.sesiones.exists():
                    if not options["rehacer"]:
                        saltados += 1
                        continue
                    actividad.sesiones.all().delete()

                # Dos reservas del mismo curso, día y hora son la misma clase
                # partida en bloques de media hora en la planilla.
                vistas, nuevas = set(), 0
                for reserva in reservas:
                    if reserva.duracion_horas is None:
                        sin_hora += 1
                        continue
                    llave = (reserva.fecha, reserva.hora_inicio)
                    if llave in vistas:
                        continue
                    vistas.add(llave)

                    SesionClase(
                        actividad=actividad,
                        fecha=reserva.fecha,
                        hora_inicio=reserva.hora_inicio,
                        duracion_horas=Decimal(str(reserva.duracion_horas)),
                        sala=reserva.sala,
                    ).save()
                    nuevas += 1

                creadas += nuevas
                actividad.refresh_from_db()
                nota = ""
                if actividad.cuadran_las_horas is False:
                    nota = (
                        f"   (suman {actividad.horas_programadas:g} h de las "
                        f"{actividad.horas_sincronicas:g} h en vivo)"
                    )
                detalle.append(
                    f"  + {actividad.nombre[:46]:<48} {nuevas} clases{nota}"
                )

            if options["dry_run"]:
                transaction.set_rollback(True)

        for linea in detalle:
            self.stdout.write(linea)

        self.stdout.write("")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("DRY-RUN: no se guardó nada."))
        self.stdout.write(self.style.SUCCESS(
            f"Clases cargadas: {creadas} · "
            f"cursos que ya tenían clases: {saltados} · "
            f"reservas sin bloque horario: {sin_hora}"
        ))
        if saltados and not options["rehacer"]:
            self.stdout.write(
                "Use --rehacer para reemplazar las clases ya cargadas."
            )

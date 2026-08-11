"""Carga el catálogo de checklist y lo propaga a las actividades existentes."""

from django.core.management.base import BaseCommand

from otec.checklist import sincronizar_catalogo
from otec.models import Actividad


class Command(BaseCommand):
    help = "Sincroniza la plantilla de checklist y crea los ítems faltantes en las actividades."

    def handle(self, *args, **options):
        creados, actualizados = sincronizar_catalogo()
        self.stdout.write(
            f"Plantilla: {creados} ítems creados, {actualizados} actualizados."
        )

        total_items = 0
        for actividad in Actividad.objects.all():
            total_items += actividad.sincronizar_checklist()

        self.stdout.write(
            self.style.SUCCESS(f"{total_items} ítems nuevos agregados a actividades existentes.")
        )

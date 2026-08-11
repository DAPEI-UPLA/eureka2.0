"""Importa la hoja ``Registro Actividades`` del Tablero Maestro OTEC.

Es reejecutable: la identidad se deduce de la propia planilla (código de
propuesta, nombre del curso, institución), así que volver a correrlo actualiza
lo que cambió en vez de duplicar. La lógica vive en ``otec.importador`` porque
la comparte con la pantalla de carga.

    python manage.py otec_importar_tablero --archivo "ruta\\Tablero.xlsx"
    python manage.py otec_importar_tablero --dry-run
"""

from django.core.management.base import BaseCommand, CommandError

from otec.importador import ErrorImportacion, ImportadorTablero


class Command(BaseCommand):
    help = "Importa la hoja 'Registro Actividades' del Tablero Maestro OTEC."

    def add_arguments(self, parser):
        parser.add_argument(
            "--archivo",
            default=r"C:\Users\claud\Desktop\OTEC\Tablero Maestro OTEC UPLA 2026 Compartida.xlsx",
            help="Ruta del .xlsx del Tablero Maestro.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Procesa y reporta sin escribir en la base de datos.",
        )
        parser.add_argument(
            "--separar-conflictos",
            action="store_true",
            help=(
                "Si un mismo ID de propuesta trae datos de expediente distintos "
                "(otra fecha de envío, otro decreto), crea una propuesta por cada "
                "combinación con sufijo -2, -3..."
            ),
        )
        parser.add_argument(
            "--sobrescribir-ediciones",
            action="store_true",
            help=(
                "Deja que el Excel pise los ítems de checklist que se editaron "
                "desde la aplicación. Por defecto esos se conservan."
            ),
        )
        parser.add_argument(
            "--detalle",
            action="store_true",
            help="Lista cambio por cambio, no solo el resumen.",
        )

    def handle(self, *args, **options):
        importador = ImportadorTablero(
            options["archivo"],
            separar_conflictos=options["separar_conflictos"],
            sobrescribir_ediciones=options["sobrescribir_ediciones"],
        )
        try:
            resultado = importador.ejecutar(aplicar=not options["dry_run"])
        except ErrorImportacion as exc:
            raise CommandError(str(exc)) from exc

        for aviso in resultado.avisos:
            self.stdout.write(self.style.WARNING(aviso))

        if options["detalle"]:
            for cambio in resultado.relevantes:
                self.stdout.write(
                    f"  {cambio.accion:<12} {cambio.entidad:<12} {cambio.nombre[:50]}"
                    + (f"  ({cambio.detalle})" if cambio.detalle else "")
                )

        self.stdout.write("")
        self.stdout.write(
            f"{'':<14}{'nuevo':>8}{'actualiz.':>11}{'renombr.':>10}"
            f"{'elimin.':>9}{'conserv.':>10}{'igual':>8}"
        )
        for fila in resultado.resumen_por_entidad():
            self.stdout.write(
                f"{fila['entidad']:<14}{fila['nuevos']:>8}{fila['actualizados']:>11}"
                f"{fila['renombrados']:>10}{fila['eliminados']:>9}"
                f"{fila['conservados']:>10}{fila['iguales']:>8}"
            )

        if resultado.descartadas:
            self.stdout.write("")
            for linea in resultado.descartadas:
                self.stdout.write(self.style.WARNING(linea))

        self.stdout.write("")
        if not resultado.aplicado:
            self.stdout.write(self.style.WARNING("DRY-RUN: no se guardó nada."))
        elif resultado.hay_cambios:
            self.stdout.write(self.style.SUCCESS(
                f"Guardado. {len(resultado.relevantes)} cambios aplicados."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "Sin cambios: el archivo ya estaba reflejado en el sistema."
            ))

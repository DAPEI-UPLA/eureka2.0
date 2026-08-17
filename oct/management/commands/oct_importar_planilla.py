"""Carga la planilla de resultados OCT desde la línea de comandos.

Es el mismo importador que usa la pantalla ``/oct/tablero/importar/``; sirve
para la primera carga y para automatizarla. Por defecto **no** pisa lo que se
editó en el sistema: hay que pedirlo con ``--sobrescribir-ediciones``.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from oct.planilla import ErrorImportacion, ImportadorPlanilla

# .../oct/management/commands/este_archivo.py -> parents[2] es la carpeta oct/,
# donde vive la planilla que entregó la OCT.
RUTA_POR_DEFECTO = Path(__file__).resolve().parents[2] / "Planilla_Resultados_OCT_2026.xlsx"


class Command(BaseCommand):
    help = "Importa la planilla de resultados OCT (hoja «Registro iniciativas»)."

    def add_arguments(self, parser):
        parser.add_argument(
            "archivo", nargs="?", default=str(RUTA_POR_DEFECTO),
            help="Ruta del .xlsx. Por defecto, el que vive en la carpeta oct/.")
        parser.add_argument(
            "--anio", type=int, default=None,
            help="Fuerza el año. Si no se indica, se lee del título de la hoja.")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Muestra qué cambiaría sin guardar nada.")
        parser.add_argument(
            "--no-podar", action="store_true",
            help="No elimina las gestiones importadas que ya no vienen en el archivo.")
        parser.add_argument(
            "--sobrescribir-ediciones", action="store_true",
            help="Deja que el Excel pise los campos editados en el sistema.")

    def handle(self, *args, **opciones):
        ruta = Path(opciones["archivo"])
        if not ruta.exists():
            raise CommandError(f"No existe el archivo: {ruta}")

        importador = ImportadorPlanilla(
            ruta,
            anio=opciones["anio"],
            podar=not opciones["no_podar"],
        )

        # Primera pasada en seco: sirve para saber qué conflictos hay y, si se
        # pidió sobrescribir, para responderlos todos con "usar el Excel".
        try:
            previo = importador.ejecutar(aplicar=False)
        except ErrorImportacion as exc:
            raise CommandError(str(exc))

        decisiones = {}
        if opciones["sobrescribir_ediciones"]:
            decisiones = {c.clave: True for c in previo.conflictos}

        resultado = previo
        if not opciones["dry_run"] or decisiones:
            resultado = ImportadorPlanilla(
                ruta,
                anio=opciones["anio"],
                podar=not opciones["no_podar"],
                decisiones=decisiones,
            ).ejecutar(aplicar=not opciones["dry_run"])

        if opciones["dry_run"]:
            self.stdout.write(self.style.WARNING("DRY-RUN: no se guardó nada."))

        self.stdout.write(f"Año: {resultado.anio}")
        for fila in resultado.resumen_por_entidad():
            self.stdout.write(
                f"  {fila['entidad']:<24} "
                f"nuevas {fila['nuevas']:>3} · "
                f"actualizadas {fila['actualizadas']:>3} · "
                f"renombradas {fila['renombradas']:>3} · "
                f"eliminadas {fila['eliminadas']:>3} · "
                f"conservadas {fila['conservadas']:>3} · "
                f"iguales {fila['iguales']:>3}"
            )

        for aviso in resultado.avisos:
            self.stdout.write(self.style.WARNING(f"  ! {aviso}"))
        for linea in resultado.descartadas:
            self.stdout.write(self.style.ERROR(f"  x {linea}"))

        if resultado.conflictos:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                f"{len(resultado.conflictos)} conflicto(s) con lo editado en el "
                f"sistema:"))
            for c in resultado.conflictos:
                decision = "se usó el Excel" if c.resuelto_con_excel else "se conservó"
                if c.es_eliminacion:
                    detalle = "ya no viene en el archivo"
                else:
                    detalle = ", ".join(d.etiqueta for d in c.diferencias)
                self.stdout.write(f"  - {c.nombre[:50]}: {detalle} ({decision})")
            if not opciones["sobrescribir_ediciones"]:
                self.stdout.write(
                    "    Use --sobrescribir-ediciones para que el archivo mande.")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"{len(resultado.relevantes)} cambios "
            f"{'previstos' if opciones['dry_run'] else 'aplicados'}."))

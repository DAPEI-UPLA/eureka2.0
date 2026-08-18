"""Chequeo previo a migrar el POA al resultado (migraciones 0020 a 0028).

Se corre **antes** de `migrate`, sobre la base que se va a migrar:

    python manage.py revisar_migracion_poa

Usa SQL directo a propósito: en ese momento el esquema de la base todavía es el
viejo y los modelos de Python ya son los nuevos, así que el ORM no sirve para
preguntarle nada.

No modifica nada. Informa tres cosas:

  1. Lo que BLOQUEA la migración (la haría fallar a medio camino).
  2. Lo que se PIERDE de forma irreversible.
  3. Lo que queda por revisar a mano después.
"""

from django.core.management.base import BaseCommand
from django.db import connection


def _hay_columna(cursor, tabla, columna):
    cursor.execute(f"PRAGMA table_info({tabla})")
    return any(fila[1] == columna for fila in cursor.fetchall())


def _pesos(valor):
    return f"${valor or 0:,.0f}".replace(",", ".")


class Command(BaseCommand):
    help = "Revisa si la base se puede migrar al POA por resultado, sin tocarla."

    def handle(self, *args, **opciones):
        with connection.cursor() as cursor:
            # Se pregunta por `resultado_id` y no por `actividad_id`: tras
            # migrar la actividad sigue existiendo, sólo que opcional, así que
            # su presencia no distingue una base de la otra.
            if _hay_columna(cursor, "proyectos_plandegasto", "resultado_id"):
                self.stdout.write(self.style.WARNING(
                    "Esta base ya está migrada (el plan ya no cuelga de la "
                    "actividad). No hay nada que revisar."
                ))
                return

            self.stdout.write(self.style.MIGRATE_HEADING(
                "\n=== 1. LO QUE BLOQUEARIA LA MIGRACION ===\n"
            ))
            self._colisiones(cursor)

            self.stdout.write(self.style.MIGRATE_HEADING(
                "\n=== 2. LO QUE SE PIERDE ===\n"
            ))
            self._presupuesto_de_actividades(cursor)

            self.stdout.write(self.style.MIGRATE_HEADING(
                "\n=== 3. LO QUE HAY QUE REVISAR DESPUES ===\n"
            ))
            self._poa_sobre_el_resultado(cursor)
            self._anios_del_poa(cursor)

    # ------------------------------------------------------------------
    def _colisiones(self, cursor):
        """La restricción nueva es (resultado, gasto elegible, año).

        Hoy es (actividad, gasto elegible, año), así que dos actividades del
        MISMO resultado pueden tener la misma línea. Al fusionarlas por
        resultado chocan, y AddConstraint falla dejando la migración a medio
        aplicar.
        """
        cursor.execute("""
            SELECT a.resultado_id, p.gasto_elegible_id, p.anio,
                   COUNT(*) AS n, SUM(p.monto) AS total
            FROM proyectos_plandegasto p
            JOIN proyectos_actividad a ON a.id = p.actividad_id
            GROUP BY a.resultado_id, p.gasto_elegible_id, p.anio
            HAVING COUNT(*) > 1
            ORDER BY n DESC
        """)
        filas = cursor.fetchall()
        if not filas:
            self.stdout.write(self.style.SUCCESS(
                "  OK  Ningun plan choca con la restriccion nueva."
            ))
            return

        self.stdout.write(self.style.ERROR(
            f"  BLOQUEA  {len(filas)} grupo(s) de planes se fusionarian en la "
            f"misma linea y la migracion fallaria:\n"
        ))
        for resultado_id, elegible_id, anio, n, total in filas[:15]:
            cursor.execute("""
                SELECT p.id, p.monto, a.nombre
                FROM proyectos_plandegasto p
                JOIN proyectos_actividad a ON a.id = p.actividad_id
                WHERE a.resultado_id = %s AND p.gasto_elegible_id = %s
                  AND p.anio = %s
            """, [resultado_id, elegible_id, anio])
            self.stdout.write(
                f"    Resultado {resultado_id} - elegible {elegible_id} - {anio}: "
                f"{n} planes, {_pesos(total)} en total"
            )
            for plan_id, monto, actividad in cursor.fetchall():
                self.stdout.write(
                    f"       - plan {plan_id}: {_pesos(monto)}  ({actividad})"
                )
        if len(filas) > 15:
            self.stdout.write(f"    ... y {len(filas) - 15} grupo(s) mas.")
        self.stdout.write(self.style.WARNING(
            "\n    Que hacer: fusionar cada grupo en un solo plan sumando sus "
            "montos,\n    o moverlos a anios distintos, ANTES de migrar."
        ))

    # ------------------------------------------------------------------
    def _presupuesto_de_actividades(self, cursor):
        cursor.execute("""
            SELECT COUNT(*), SUM(presupuesto_corriente), SUM(presupuesto_capital)
            FROM proyectos_actividad
            WHERE presupuesto_corriente > 0 OR presupuesto_capital > 0
        """)
        n, corriente, capital = cursor.fetchone()
        if not n:
            self.stdout.write(self.style.SUCCESS(
                "  OK  Ninguna actividad tiene presupuesto cargado."
            ))
            return
        self.stdout.write(
            f"  {n} actividad(es) tienen presupuesto y sus columnas se eliminan:\n"
            f"     corriente {_pesos(corriente)} - capital {_pesos(capital)}\n"
        )
        self.stdout.write(self.style.WARNING(
            "    Es el reparto INTERNO del resultado entre sus actividades, que\n"
            "    es justo lo que el equipo decidio dejar de llevar. El presupuesto\n"
            "    del resultado NO cambia: vive en sus propias columnas.\n"
            "    Si igual lo quieres de referencia, exportalo antes."
        ))

    # ------------------------------------------------------------------
    def _poa_sobre_el_resultado(self, cursor):
        """Planes que ya suman más de lo que su resultado tiene."""
        cursor.execute("""
            SELECT a.resultado_id, SUM(p.monto) AS poa,
                   r.presupuesto_corriente + r.presupuesto_capital AS tiene
            FROM proyectos_plandegasto p
            JOIN proyectos_actividad a ON a.id = p.actividad_id
            JOIN proyectos_resultado r ON r.id = a.resultado_id
            GROUP BY a.resultado_id
            HAVING poa > tiene
        """)
        filas = cursor.fetchall()
        if not filas:
            self.stdout.write(self.style.SUCCESS(
                "  OK  Ningun resultado tiene POA por sobre su presupuesto."
            ))
            return
        self.stdout.write(self.style.WARNING(
            f"  {len(filas)} resultado(s) quedaran con el POA por sobre su "
            f"presupuesto.\n"
            f"    La migracion los deja pasar, pero al editarlos el sistema los\n"
            f"    rechazara hasta que cuadren:\n"
        ))
        for resultado_id, poa, tiene in filas[:15]:
            self.stdout.write(
                f"    Resultado {resultado_id}: POA {_pesos(poa)} vs "
                f"presupuesto {_pesos(tiene)}"
            )

    # ------------------------------------------------------------------
    def _anios_del_poa(self, cursor):
        """Tras migrar, cada resultado queda con todo su presupuesto en un solo
        año. Los planes de otros años quedan sin respaldo hasta repartir."""
        cursor.execute("""
            SELECT p.anio, COUNT(*), SUM(p.monto)
            FROM proyectos_plandegasto p
            GROUP BY p.anio ORDER BY p.anio
        """)
        filas = cursor.fetchall()
        if len(filas) <= 1:
            self.stdout.write(self.style.SUCCESS(
                "  OK  El POA esta en un solo anio."
            ))
            return
        self.stdout.write(self.style.WARNING(
            f"  El POA abarca {len(filas)} anios:\n"
        ))
        for anio, n, total in filas:
            self.stdout.write(f"    {anio}: {n} plan(es), {_pesos(total)}")
        self.stdout.write(
            "\n    Las migraciones 0021/0025/0027 concentran TODO el presupuesto\n"
            "    en el primer anio (a proposito: un reparto inventado se ve\n"
            "    legitimo y nadie lo corrige). Hasta que cada equipo reparta sus\n"
            "    anios, los planes de los demas anios quedan sin respaldo y no se\n"
            "    podran editar."
        )

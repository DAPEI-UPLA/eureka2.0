"""El chequeo previo a migrar no toca nada y avisa cuando la base ya migró.

La utilidad real —detectar planes que colisionan bajo la restricción nueva— se
verificó a mano contra una copia del esquema viejo con datos sembrados: el
comando los reportó y `migrate` falló exactamente donde dijo, con
«UNIQUE constraint failed: resultado_id, gasto_elegible_id, anio».

Aquí sólo se cubre lo que se puede probar sobre una base ya migrada, que es la
que usan los tests: que no reviente, que no escriba, y que lo diga.
"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command

from .models import PlanDeGasto, PresupuestoAnual, PresupuestoObjetivoAnual
from .tests import BaseProyectoTest


class RevisarMigracionPoaTests(BaseProyectoTest):

    def _correr(self):
        salida = StringIO()
        call_command("revisar_migracion_poa", stdout=salida)
        return salida.getvalue()

    def test_avisa_que_la_base_ya_esta_migrada(self):
        self.assertIn("ya está migrada", self._correr())

    def test_no_modifica_nada(self):
        objetivo = self.crear_objetivo()
        anio = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=1, anio_calendario=2026,
            presupuesto_corriente=Decimal("600000"),
        )
        PresupuestoObjetivoAnual.objects.create(
            objetivo=objetivo, anio=anio,
            presupuesto_corriente=Decimal("100000"),
        )
        antes = (
            PlanDeGasto.objects.count(),
            PresupuestoAnual.objects.count(),
            PresupuestoObjetivoAnual.objects.count(),
            objetivo.presupuesto_corriente,
        )

        self._correr()

        objetivo.refresh_from_db()
        self.assertEqual(
            antes,
            (
                PlanDeGasto.objects.count(),
                PresupuestoAnual.objects.count(),
                PresupuestoObjetivoAnual.objects.count(),
                objetivo.presupuesto_corriente,
            ),
        )

"""La cabecera del objetivo muestra lo repartido a sus resultados.

El defecto reportado: sólo se veía el disponible, que es el resto. Con el saldo
solo, un objetivo en $0 disponible puede tener todo repartido a sus resultados
o simplemente no tener presupuesto, y los dos casos se ven idénticos.
"""

from decimal import Decimal

from django.urls import reverse

from .models import (
    PresupuestoAnual,
    PresupuestoObjetivoAnual,
    PresupuestoResultadoAnual,
)
from .tests import BaseProyectoTest


class BaseRepartoTest(BaseProyectoTest):

    def setUp(self):
        super().setUp()
        self.objetivo = self.crear_objetivo(
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
        self.r1 = self.crear_resultado(
            self.objetivo, descripcion="R1",
            presupuesto_corriente=Decimal("300000"),
            presupuesto_capital=Decimal("100000"),
        )
        self.r2 = self.crear_resultado(
            self.objetivo, descripcion="R2",
            presupuesto_corriente=Decimal("100000"),
        )

    def cabecera(self, **params):
        return self.client.get(
            reverse("proyectos:meta_objetivo", args=[self.objetivo.pk]), params
        ).content.decode()


class CalculoTests(BaseRepartoTest):

    def test_lo_repartido_es_la_suma_de_los_resultados(self):
        self.assertEqual(
            self.objetivo.presupuesto_distribuido, Decimal("500000"))

    def test_lo_sin_repartir_es_el_resto(self):
        self.assertEqual(
            self.objetivo.presupuesto_sin_repartir, Decimal("500000"))

    def test_los_dos_suman_el_presupuesto_del_objetivo(self):
        self.assertEqual(
            self.objetivo.presupuesto_distribuido
            + self.objetivo.presupuesto_sin_repartir,
            self.objetivo.presupuesto_asignado,
        )

    def test_un_resultado_eliminado_deja_de_contar(self):
        self.r2.eliminado = True
        self.r2.save()
        self.assertEqual(
            self.objetivo.presupuesto_distribuido, Decimal("400000"))

    def test_sin_resultados_no_hay_nada_repartido(self):
        otro = self.crear_objetivo(presupuesto_corriente=Decimal("100000"))
        self.assertEqual(otro.presupuesto_distribuido, Decimal("0"))
        self.assertEqual(otro.presupuesto_sin_repartir, Decimal("100000"))


class PantallaTests(BaseRepartoTest):

    def test_la_cabecera_muestra_lo_repartido(self):
        html = self.cabecera()
        self.assertIn("En resultados:", html)
        self.assertIn("500.000", html)

    def test_los_montos_van_con_punto_como_en_el_resto_de_la_app(self):
        """`intcomma` con es-CL agrupa con espacio duro. Esta caja era la única
        que lo hacía, y con el número nuevo quedaban dos formatos juntos."""
        html = self.cabecera()
        self.assertIn("$600.000", html)
        self.assertNotIn(" ", html)  # espacio duro

    def test_tambien_muestra_lo_que_falta_por_repartir(self):
        self.assertIn("Sin repartir", self.cabecera())

    def test_repartido_y_saldo_ya_no_se_confunden(self):
        """El caso que motivó el arreglo: todo repartido deja el saldo en cero,
        y antes eso se veía igual que un objetivo sin presupuesto."""
        self.r2.presupuesto_corriente = Decimal("300000")
        self.r2.presupuesto_capital = Decimal("300000")
        self.r2.save()

        self.objetivo.refresh_from_db()
        self.assertEqual(self.objetivo.presupuesto_sin_repartir, Decimal("0"))
        html = self.cabecera()
        self.assertIn("1.000.000", html)  # lo repartido sigue a la vista


class PorAnioTests(BaseRepartoTest):
    """Con un año en pantalla, lo repartido tiene que ser el de ese año."""

    def setUp(self):
        super().setUp()
        self.a1 = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=1, anio_calendario=2026,
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
        self.oa = PresupuestoObjetivoAnual.objects.create(
            objetivo=self.objetivo, anio=self.a1,
            presupuesto_corriente=Decimal("400000"),
            presupuesto_capital=Decimal("200000"),
        )
        PresupuestoResultadoAnual.objects.create(
            resultado=self.r1, anio=self.a1,
            presupuesto_corriente=Decimal("250000"),
            presupuesto_capital=Decimal("150000"),
        )

    def test_cuenta_solo_el_reparto_de_ese_anio(self):
        self.assertEqual(self.objetivo.distribuido_en(2026), Decimal("400000"))

    def test_un_anio_sin_reparto_da_cero(self):
        self.assertEqual(self.objetivo.distribuido_en(2027), Decimal("0"))

    def test_la_fila_anual_expone_los_mismos_nombres(self):
        """La plantilla lee un solo par de nombres, mire el objetivo completo o
        su fila del año; si divergen, la cabecera muestra un vacío en silencio."""
        self.assertEqual(self.oa.presupuesto_distribuido, Decimal("400000"))
        self.assertEqual(self.oa.presupuesto_sin_repartir, Decimal("200000"))

    def test_la_cabecera_del_anio_no_muestra_el_total_del_proyecto(self):
        """Sería el mismo error de antes: una cifra de toda la vida del
        objetivo bajo un encabezado que dice «Año 1»."""
        html = self.cabecera(anio=2026)
        self.assertIn("400.000", html)
        self.assertIn("Año 1", html)

    def test_el_objeto_de_ceros_no_revienta_la_cabecera(self):
        """Un objetivo sin asignación en el año elegido."""
        otro = self.crear_objetivo(presupuesto_corriente=Decimal("50000"))
        html = self.client.get(
            reverse("proyectos:meta_objetivo", args=[otro.pk]), {"anio": 2026}
        ).content.decode()
        self.assertIn("En resultados:", html)
        self.assertIn("$0", html)

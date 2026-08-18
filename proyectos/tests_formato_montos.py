"""Los montos se escriben y se leen con punto de miles.

`intcomma` no sirve aquí: con `LANGUAGE_CODE = 'es-cl'` el módulo de formato del
locale manda sobre `settings.THOUSAND_SEPARATOR` y agrupa con espacio duro
(U+00A0), así que un presupuesto de nueve cifras salía «25 000 000». El filtro
`miles` impone el punto sin depender del locale.

Lo importante es que el formato viaje de ida y de vuelta: lo que la pantalla
pinta con puntos tiene que volver al servidor y guardarse como el mismo número.
"""

from decimal import Decimal

from django.urls import reverse

from .models import PresupuestoAnual, PresupuestoObjetivoAnual
from .templatetags.montos import miles
from .tests import BaseProyectoTest


class FiltroMilesTests(BaseProyectoTest):

    def test_agrupa_de_a_tres_con_punto(self):
        self.assertEqual(miles(Decimal("25000000")), "25.000.000")
        self.assertEqual(miles(Decimal("1500")), "1.500")
        self.assertEqual(miles(Decimal("999")), "999")

    def test_los_montos_chicos_no_llevan_separador(self):
        self.assertEqual(miles(Decimal("0")), "0")
        self.assertEqual(miles(Decimal("7")), "7")

    def test_redondea_los_decimales(self):
        self.assertEqual(miles(Decimal("1234.56")), "1.235")

    def test_lo_vacio_se_muestra_como_cero(self):
        self.assertEqual(miles(None), "0")
        self.assertEqual(miles(""), "0")

    def test_acepta_texto_ya_formateado(self):
        """Tras un error, el valor puede volver como lo escribió el usuario."""
        self.assertEqual(miles("25.000.000"), "25.000.000")
        self.assertEqual(miles("25\xa0000\xa0000"), "25.000.000")

    def test_no_revienta_con_basura(self):
        self.assertEqual(miles("abc"), "abc")


class MontosEnPantallaTests(BaseProyectoTest):
    """Proyecto de $1.000.000: $600.000 corriente + $400.000 capital."""

    def setUp(self):
        super().setUp()
        self.a1 = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=1, anio_calendario=2026,
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
        self.a2 = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=2, anio_calendario=2027,
        )

    def test_el_reparto_del_proyecto_muestra_puntos(self):
        respuesta = self.client.get(
            reverse("proyectos:listar_presupuesto_anual", args=[self.proyecto.pk])
        )
        cuerpo = respuesta.content.decode()
        self.assertIn('value="600.000"', cuerpo)
        self.assertIn('value="400.000"', cuerpo)
        self.assertNotIn('value="600000"', cuerpo)

    def test_las_cajas_quedan_marcadas_para_el_formateo_en_vivo(self):
        respuesta = self.client.get(
            reverse("proyectos:listar_presupuesto_anual", args=[self.proyecto.pk])
        )
        self.assertContains(respuesta, 'data-monto="1"')
        self.assertContains(respuesta, 'inputmode="numeric"')

    def test_el_reparto_del_objetivo_muestra_puntos(self):
        objetivo = self.crear_objetivo()
        PresupuestoObjetivoAnual.objects.create(
            objetivo=objetivo, anio=self.a1,
            presupuesto_corriente=Decimal("250000"),
        )
        respuesta = self.client.get(
            reverse("proyectos:presupuesto_objetivo_anual", args=[objetivo.pk])
        )
        self.assertContains(respuesta, 'value="250.000"')

    def test_lo_que_se_pinta_vuelve_y_se_guarda_igual(self):
        """El viaje completo: la pantalla escribe «400.000» y el servidor tiene
        que guardar 400000, no 400 ni reventar."""
        self.client.post(
            reverse("proyectos:guardar_anios", args=[self.proyecto.pk]),
            {
                f"corriente_{self.a1.pk}": "400.000",
                f"capital_{self.a1.pk}": "250.000",
                f"corriente_{self.a2.pk}": "200.000",
                f"capital_{self.a2.pk}": "150.000",
            },
        )
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.assertEqual(self.a1.presupuesto_corriente, Decimal("400000"))
        self.assertEqual(self.a1.presupuesto_capital, Decimal("250000"))
        self.assertEqual(self.a2.presupuesto_corriente, Decimal("200000"))
        self.assertEqual(self.a2.presupuesto_capital, Decimal("150000"))
        self.assertTrue(self.proyecto.anios_cuadrados)

    def test_un_monto_de_nueve_cifras_sobrevive_el_viaje(self):
        self.proyecto.presupuesto_total = Decimal("250000000")
        self.proyecto.presupuesto_corriente = Decimal("250000000")
        self.proyecto.presupuesto_capital = Decimal("0")
        self.proyecto.save()

        self.client.post(
            reverse("proyectos:guardar_anios", args=[self.proyecto.pk]),
            {
                f"corriente_{self.a1.pk}": "225.000.000",
                f"capital_{self.a1.pk}": "0",
                f"corriente_{self.a2.pk}": "25.000.000",
                f"capital_{self.a2.pk}": "0",
            },
        )
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.assertEqual(self.a1.presupuesto_corriente, Decimal("225000000"))
        self.assertEqual(self.a2.presupuesto_corriente, Decimal("25000000"))

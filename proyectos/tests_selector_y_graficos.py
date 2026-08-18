"""El selector de año se refresca solo, y los gráficos respetan el año.

Dos cosas reportadas:

  - Al agregar un año había que apretar F5 para que apareciera en los botones.
    El selector era HTML fijo de la página, y los años se crean desde una
    sección de más abajo que sólo repinta su propia caja.

  - Los gráficos mostraban siempre el proyecto completo, aunque se estuviera
    mirando un año.
"""

from decimal import Decimal

from django.urls import reverse

from .models import (
    Actividad,
    CORRIENTE,
    Egreso,
    GastoElegible,
    PlanDeGasto,
    PresupuestoAnual,
    PresupuestoObjetivoAnual,
)
from .tests import BaseProyectoTest


class SelectorSeRefrescaSoloTests(BaseProyectoTest):

    def test_el_selector_vive_en_su_propio_contenedor(self):
        """Si fuera HTML fijo, un año nuevo no aparecería hasta recargar."""
        respuesta = self.client.get(
            reverse("proyectos:detalle_proyecto", args=[self.proyecto.pk])
        )
        self.assertContains(respuesta, 'id="anio-selector-container"')
        self.assertContains(respuesta, "estructuraActualizada from:body")

    def test_crear_un_anio_avisa_para_que_el_selector_se_repinte(self):
        respuesta = self.client.post(
            reverse("proyectos:crear_anio", args=[self.proyecto.pk])
        )
        self.assertIn("estructuraActualizada", respuesta.headers.get("HX-Trigger", ""))

    def test_el_selector_devuelve_los_anios_al_dia(self):
        url = reverse("proyectos:selector_anios", args=[self.proyecto.pk])
        self.assertNotContains(self.client.get(url), "Año 1")

        self.client.post(reverse("proyectos:crear_anio", args=[self.proyecto.pk]))
        respuesta = self.client.get(url)
        self.assertContains(respuesta, "Año 1")
        self.assertContains(respuesta, "Todo el proyecto")

    def test_el_selector_conserva_cual_esta_activo(self):
        for _ in range(2):
            self.client.post(reverse("proyectos:crear_anio", args=[self.proyecto.pk]))
        segundo = self.proyecto.presupuestos_anuales.get(numero_anio=2)

        respuesta = self.client.get(
            reverse("proyectos:selector_anios", args=[self.proyecto.pk]),
            {"anio": segundo.anio_calendario},
        )
        self.assertEqual(respuesta.context["anio_sel"].pk, segundo.pk)
        self.assertContains(respuesta, "Viendo")

    def test_sin_anios_no_se_muestra_ningun_boton(self):
        respuesta = self.client.get(
            reverse("proyectos:selector_anios", args=[self.proyecto.pk])
        )
        self.assertNotContains(respuesta, "anio-selector")


class GraficosPorAnioTests(BaseProyectoTest):
    """Proyecto de $1.000.000 en dos años de $500.000."""

    def setUp(self):
        super().setUp()
        for numero, calendario in ((1, 2026), (2, 2027)):
            PresupuestoAnual.objects.create(
                proyecto=self.proyecto, numero_anio=numero,
                anio_calendario=calendario,
                presupuesto_corriente=Decimal("300000"),
                presupuesto_capital=Decimal("200000"),
            )
        self.a1 = self.proyecto.presupuesto_del_calendario(2026)
        self.a2 = self.proyecto.presupuesto_del_calendario(2027)

        self.objetivo = self.crear_objetivo()
        PresupuestoObjetivoAnual.objects.create(
            objetivo=self.objetivo, anio=self.a1,
            presupuesto_corriente=Decimal("200000"),
        )
        PresupuestoObjetivoAnual.objects.create(
            objetivo=self.objetivo, anio=self.a2,
            presupuesto_corriente=Decimal("50000"),
        )
        self.resultado = self.crear_resultado(
            self.objetivo, presupuesto_corriente=Decimal("250000"),
        )
        self.actividad = Actividad.objects.create(
            resultado=self.resultado, nombre="A",
            presupuesto_corriente=Decimal("250000"),
        )
        elegible = GastoElegible.objects.filter(
            gasto__tipo_gasto__transferencia__naturaleza=CORRIENTE
        ).first()
        self.plan_2026 = PlanDeGasto.objects.create(
            actividad=self.actividad, gasto_elegible=elegible,
            anio=2026, monto=Decimal("200000"),
        )
        # Un gasto pagado sólo en 2026.
        Egreso.objects.create(
            proyecto=self.proyecto, tipo=Egreso.TIPO_COMPRA,
            subtipo_compra=Egreso.SUB_BIENES_INSUMOS,
            estado=Egreso.ESTADO_PAGADO,
            plan_de_gasto=self.plan_2026, gasto_elegible=elegible,
            cantidad=1, valor_sin_iva=Decimal("100000"),
        )
        self.url = reverse("proyectos:graficos_proyecto", args=[self.proyecto.pk])

    def test_sin_anio_la_cascada_es_del_proyecto_completo(self):
        cascada = self.client.get(self.url).context["cascada"]
        self.assertEqual(cascada["data"][0], 1000000.0)

    def test_con_un_anio_la_cascada_es_de_ese_anio(self):
        cascada = self.client.get(self.url, {"anio": 2026}).context["cascada"]
        self.assertEqual(cascada["data"][0], 500000.0)

    def test_lo_gastado_se_cuenta_solo_en_su_anio(self):
        """El gasto está cargado a un plan de 2026: en 2027 no aparece."""
        en_2026 = self.client.get(self.url, {"anio": 2026}).context["comprometido_pagado"]
        en_2027 = self.client.get(self.url, {"anio": 2027}).context["comprometido_pagado"]

        self.assertEqual(en_2026["data"][0], 119000.0)  # pagado, con IVA
        self.assertEqual(en_2027["data"][0], 0.0)

    def test_el_presupuesto_por_objetivo_es_el_del_anio(self):
        completo = self.client.get(self.url).context["avance_objetivos"]
        en_2027 = self.client.get(self.url, {"anio": 2027}).context["avance_objetivos"]

        self.assertEqual(completo["presupuesto"], [250000.0])
        self.assertEqual(en_2027["presupuesto"], [50000.0])

    def test_el_avance_fisico_no_cambia_con_el_anio(self):
        """No hay cumplimiento por año: se muestra el global y se avisa."""
        completo = self.client.get(self.url).context["avance_objetivos"]
        en_2027 = self.client.get(self.url, {"anio": 2027})

        self.assertEqual(completo["avance"], en_2027.context["avance_objetivos"]["avance"])
        self.assertContains(en_2027, "no se registra por año")

    def test_los_gastos_por_transferencia_se_filtran_por_anio(self):
        en_2026 = self.client.get(self.url, {"anio": 2026}).context["gastos_transferencia"]
        en_2027 = self.client.get(self.url, {"anio": 2027}).context["gastos_transferencia"]

        self.assertEqual(sum(en_2026["data"]), 119000.0)
        self.assertEqual(en_2027["data"], [])

    def test_un_anio_inexistente_muestra_el_proyecto_completo(self):
        cascada = self.client.get(self.url, {"anio": 2099}).context["cascada"]
        self.assertEqual(cascada["data"][0], 1000000.0)

    def test_el_detalle_le_pasa_el_anio_al_contenedor_de_graficos(self):
        respuesta = self.client.get(
            reverse("proyectos:detalle_proyecto", args=[self.proyecto.pk]),
            {"anio": 2027},
        )
        self.assertContains(respuesta, "graficos/?anio=2027")

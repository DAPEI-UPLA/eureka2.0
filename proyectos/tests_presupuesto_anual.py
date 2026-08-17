"""Pruebas del reparto del presupuesto por año calendario.

Un proyecto de 36 meses no tiene un presupuesto, tiene tres: uno por año, que
es como se transfiere y como se rinde. Aquí se cubre el reparto en sí, el techo
que le pone al POA de cada año, y el CRUD por HTMX.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from .models import PlanDeGasto, PresupuestoAnual
from .tests import BaseGastosTest, BaseProyectoTest


class PresupuestoAnualTests(BaseProyectoTest):
    """El proyecto base tiene $1.000.000 ($600.000 corriente + $400.000 capital)."""

    def crear_anio(self, numero, calendario, corriente="0", capital="0"):
        anio = PresupuestoAnual(
            proyecto=self.proyecto,
            numero_anio=numero,
            anio_calendario=calendario,
            presupuesto_corriente=Decimal(corriente),
            presupuesto_capital=Decimal(capital),
        )
        anio.full_clean()
        anio.save()
        return anio

    def test_la_suma_de_los_anios_no_puede_pasarse_del_proyecto(self):
        self.crear_anio(1, 2026, corriente="500000")
        with self.assertRaises(ValidationError) as caso:
            self.crear_anio(2, 2027, corriente="200000")
        self.assertIn("presupuesto_corriente", caso.exception.message_dict)

    def test_las_bolsas_se_topan_por_separado(self):
        """Que sobre corriente no habilita a pasarse en capital."""
        self.crear_anio(1, 2026, corriente="100000", capital="400000")
        with self.assertRaises(ValidationError):
            self.crear_anio(2, 2027, capital="1")

    def test_el_reparto_cuadra_cuando_suma_el_total(self):
        self.crear_anio(1, 2026, corriente="300000", capital="200000")
        self.assertFalse(self.proyecto.anios_cuadrados)
        self.assertEqual(self.proyecto.sin_repartir_por_anio, Decimal("500000"))

        self.crear_anio(2, 2027, corriente="300000", capital="200000")
        self.assertTrue(self.proyecto.anios_cuadrados)
        self.assertEqual(self.proyecto.sin_repartir_por_anio, Decimal("0"))

    def test_no_se_repite_el_numero_de_anio(self):
        self.crear_anio(1, 2026)
        with self.assertRaises(ValidationError):
            self.crear_anio(1, 2027)

    def test_no_se_repite_el_anio_calendario(self):
        self.crear_anio(1, 2026)
        with self.assertRaises(ValidationError):
            self.crear_anio(2, 2026)

    def test_cantidad_de_anios_sugerida_sale_de_las_fechas(self):
        """Un proyecto que parte en julio y dura 36 meses toca cuatro años
        calendario, no tres: por eso mandan las fechas sobre la duración."""
        self.proyecto.fecha_inicio = date(2025, 7, 1)
        self.proyecto.fecha_fin = date(2028, 6, 30)
        self.proyecto.duracion_meses = 36
        self.assertEqual(self.proyecto.cantidad_anios_sugerida, 4)

    def test_sin_fechas_la_sugerencia_sale_de_la_duracion(self):
        self.proyecto.duracion_meses = 36
        self.assertEqual(self.proyecto.cantidad_anios_sugerida, 3)
        self.proyecto.duracion_meses = 30
        self.assertEqual(self.proyecto.cantidad_anios_sugerida, 3)

    def test_anio_en_curso_es_el_del_calendario_de_hoy(self):
        self.crear_anio(1, date.today().year)
        self.crear_anio(2, date.today().year + 1)
        self.assertEqual(self.proyecto.anio_en_curso.numero_anio, 1)


class TechoAnualDelPlanTests(BaseGastosTest):
    """`BaseGastosTest` deja el proyecto con planes por $600.000 corriente y
    $400.000 capital, todos en 2026."""

    def repartir(self, corriente_por_anio, capital_por_anio):
        for numero, calendario in ((1, 2026), (2, 2027)):
            PresupuestoAnual.objects.create(
                proyecto=self.proyecto,
                numero_anio=numero,
                anio_calendario=calendario,
                presupuesto_corriente=Decimal(corriente_por_anio),
                presupuesto_capital=Decimal(capital_por_anio),
            )

    def test_sin_reparto_anual_todo_sigue_como_antes(self):
        """Los proyectos que no repartieron su presupuesto no ven techo nuevo."""
        self.assertFalse(self.proyecto.presupuestos_anuales.exists())
        plan = PlanDeGasto(
            actividad=self.actividad,
            gasto_elegible=self.elegible_corriente,
            anio=2027,
            monto=Decimal("0"),
        )
        plan.full_clean()  # no revienta

    def test_un_plan_no_cabe_en_un_anio_sin_presupuesto(self):
        PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=1, anio_calendario=2026,
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
        self.plan_corriente.anio = 2028
        with self.assertRaises(ValidationError) as caso:
            self.plan_corriente.full_clean()
        self.assertIn("anio", caso.exception.message_dict)

    def test_el_poa_del_anio_no_puede_superar_su_presupuesto(self):
        """El caso que motivó la regla: cargar todo el POA de un proyecto
        multianual en el primer año."""
        self.repartir("300000", "200000")
        # El plan corriente de 2026 vale $600.000 y su año sólo tiene $300.000.
        with self.assertRaises(ValidationError) as caso:
            self.plan_corriente.full_clean()
        self.assertIn("monto", caso.exception.message_dict)

    def test_el_mismo_poa_cabe_repartido_entre_los_dos_anios(self):
        self.repartir("300000", "200000")

        self.plan_corriente.monto = Decimal("300000")
        self.plan_corriente.full_clean()
        self.plan_corriente.save()

        self.plan_capital.monto = Decimal("200000")
        self.plan_capital.full_clean()
        self.plan_capital.save()

        anio_1 = self.proyecto.presupuesto_del_calendario(2026)
        self.assertEqual(anio_1.planificado_corriente, Decimal("300000"))
        self.assertEqual(anio_1.planificado_capital, Decimal("200000"))
        self.assertEqual(anio_1.disponible, Decimal("0"))

    def test_editar_un_plan_no_cuenta_su_propio_monto_dos_veces(self):
        """Sin esto, reguardar un plan que ya llena su año lo rechazaría y
        quedaría imposible de corregir."""
        PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=1, anio_calendario=2026,
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
        self.plan_corriente.full_clean()  # llena su año justo, no revienta

    def test_el_anio_reporta_lo_gastado_para_medir_subejecucion(self):
        PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=1, anio_calendario=2026,
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
        self.compra(plan=self.plan_corriente, neto="100000")  # $119.000 con IVA
        anio = self.proyecto.presupuesto_del_calendario(2026)
        self.assertEqual(anio.gastos_total, Decimal("119000"))
        self.assertEqual(anio.porcentaje_ejecutado, Decimal("11.90"))


class PresupuestoAnualVistasTests(BaseProyectoTest):
    """El CRUD por HTMX del reparto anual."""

    def test_agregar_anio_lo_crea_en_cero_y_correlativo(self):
        url = reverse("proyectos:crear_anio", args=[self.proyecto.pk])
        self.client.post(url)
        self.client.post(url)

        anios = list(self.proyecto.presupuestos_anuales.all())
        self.assertEqual([a.numero_anio for a in anios], [1, 2])
        self.assertEqual(
            [a.anio_calendario for a in anios],
            [date.today().year, date.today().year + 1],
        )
        self.assertEqual(anios[0].presupuesto_total, Decimal("0"))

    def test_guardar_montos_los_persiste(self):
        self.client.post(reverse("proyectos:crear_anio", args=[self.proyecto.pk]))
        anio = self.proyecto.presupuestos_anuales.first()

        self.client.post(reverse("proyectos:guardar_anio", args=[anio.pk]), {
            "presupuesto_corriente": "600.000",
            "presupuesto_capital": "400.000",
        })
        anio.refresh_from_db()
        self.assertEqual(anio.presupuesto_corriente, Decimal("600000"))
        self.assertEqual(anio.presupuesto_capital, Decimal("400000"))

    def test_guardar_de_mas_muestra_el_error_y_no_pisa_lo_guardado(self):
        self.client.post(reverse("proyectos:crear_anio", args=[self.proyecto.pk]))
        anio = self.proyecto.presupuestos_anuales.first()

        respuesta = self.client.post(
            reverse("proyectos:guardar_anio", args=[anio.pk]),
            {"presupuesto_corriente": "999999999", "presupuesto_capital": "0"},
        )
        anio.refresh_from_db()
        self.assertEqual(anio.presupuesto_corriente, Decimal("0"))
        self.assertContains(respuesta, "Supera el presupuesto corriente")

    def test_eliminar_renumera_los_anios_restantes(self):
        url = reverse("proyectos:crear_anio", args=[self.proyecto.pk])
        for _ in range(3):
            self.client.post(url)

        segundo = self.proyecto.presupuestos_anuales.get(numero_anio=2)
        self.client.post(reverse("proyectos:eliminar_anio", args=[segundo.pk]))

        anios = list(self.proyecto.presupuestos_anuales.all())
        self.assertEqual([a.numero_anio for a in anios], [1, 2])
        # El año calendario no se renumera: es un dato, no una posición.
        self.assertEqual(
            [a.anio_calendario for a in anios],
            [date.today().year, date.today().year + 2],
        )

    def test_quien_no_es_responsable_ni_jefe_no_puede_tocar_el_reparto(self):
        otro = User.objects.create_user("ajeno", password="x")
        self.client.force_login(otro)
        respuesta = self.client.post(
            reverse("proyectos:crear_anio", args=[self.proyecto.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_el_detalle_muestra_la_seccion(self):
        respuesta = self.client.get(
            reverse("proyectos:detalle_proyecto", args=[self.proyecto.pk])
        )
        self.assertContains(respuesta, "Presupuesto por año")
        self.assertContains(respuesta, "presupuesto-anual-container")

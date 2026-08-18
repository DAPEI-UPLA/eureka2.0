"""Pruebas del reparto del presupuesto de un objetivo por año.

Un escalón bajo `PresupuestoAnual`: el proyecto reparte su plata por año, y
dentro de cada año se reparte entre los objetivos. El total del objetivo pasa a
ser la suma de sus años y deja de editarse a mano.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from .models import (
    Actividad,
    GastoElegible,
    CORRIENTE,
    PlanDeGasto,
    PresupuestoAnual,
    PresupuestoObjetivoAnual,
)
from .tests import BaseProyectoTest


class BaseObjetivoAnualTest(BaseProyectoTest):
    """Proyecto de $1.000.000 repartido en dos años de $500.000.

    Cada año: $300.000 corriente + $200.000 capital.
    """

    def setUp(self):
        super().setUp()
        for numero, calendario in ((1, 2026), (2, 2027)):
            PresupuestoAnual.objects.create(
                proyecto=self.proyecto,
                numero_anio=numero,
                anio_calendario=calendario,
                presupuesto_corriente=Decimal("300000"),
                presupuesto_capital=Decimal("200000"),
            )
        self.anio_1 = self.proyecto.presupuesto_del_calendario(2026)
        self.anio_2 = self.proyecto.presupuesto_del_calendario(2027)
        self.objetivo = self.crear_objetivo()

    def asignar(self, objetivo, anio, corriente="0", capital="0"):
        fila = PresupuestoObjetivoAnual(
            objetivo=objetivo,
            anio=anio,
            presupuesto_corriente=Decimal(corriente),
            presupuesto_capital=Decimal(capital),
        )
        fila.full_clean()
        fila.save()
        return fila


class RepartoDelObjetivoTests(BaseObjetivoAnualTest):

    def test_el_total_del_objetivo_es_la_suma_de_sus_anios(self):
        self.asignar(self.objetivo, self.anio_1, "100000", "50000")
        self.asignar(self.objetivo, self.anio_2, "200000", "80000")

        self.objetivo.refresh_from_db()
        self.assertEqual(self.objetivo.presupuesto_corriente, Decimal("300000"))
        self.assertEqual(self.objetivo.presupuesto_capital, Decimal("130000"))
        self.assertEqual(self.objetivo.presupuesto_asignado, Decimal("430000"))

    def test_editar_una_asignacion_recalcula_el_total(self):
        fila = self.asignar(self.objetivo, self.anio_1, "100000")
        fila.presupuesto_corriente = Decimal("250000")
        fila.full_clean()
        fila.save()

        self.objetivo.refresh_from_db()
        self.assertEqual(self.objetivo.presupuesto_corriente, Decimal("250000"))

    def test_borrar_una_asignacion_recalcula_el_total(self):
        self.asignar(self.objetivo, self.anio_1, "100000")
        fila_2 = self.asignar(self.objetivo, self.anio_2, "200000")
        fila_2.delete()

        self.objetivo.refresh_from_db()
        self.assertEqual(self.objetivo.presupuesto_corriente, Decimal("100000"))

    def test_los_objetivos_de_un_anio_no_pueden_pasarse_de_ese_anio(self):
        otro = self.crear_objetivo()
        self.asignar(self.objetivo, self.anio_1, "250000")
        with self.assertRaises(ValidationError) as caso:
            self.asignar(otro, self.anio_1, "100000")
        self.assertIn("presupuesto_corriente", caso.exception.message_dict)

    def test_cada_anio_tiene_su_propio_techo(self):
        """Llenar el año 1 no impide repartir el año 2."""
        self.asignar(self.objetivo, self.anio_1, "300000", "200000")
        otro = self.crear_objetivo()
        self.asignar(otro, self.anio_2, "300000", "200000")  # no revienta

        self.assertEqual(self.anio_1.sin_asignar_a_objetivos, Decimal("0"))
        self.assertEqual(self.anio_2.sin_asignar_a_objetivos, Decimal("0"))

    def test_las_bolsas_se_topan_por_separado(self):
        self.asignar(self.objetivo, self.anio_1, "0", "200000")
        otro = self.crear_objetivo()
        with self.assertRaises(ValidationError):
            self.asignar(otro, self.anio_1, "0", "1")

    def test_un_anio_de_otro_proyecto_se_rechaza(self):
        otro_proyecto = self.proyecto.__class__.objects.create(
            nombre="Otro", presupuesto_total=Decimal("100"),
            presupuesto_corriente=Decimal("100"), presupuesto_capital=Decimal("0"),
        )
        anio_ajeno = PresupuestoAnual.objects.create(
            proyecto=otro_proyecto, numero_anio=1, anio_calendario=2026,
            presupuesto_corriente=Decimal("100"),
        )
        fila = PresupuestoObjetivoAnual(
            objetivo=self.objetivo, anio=anio_ajeno,
            presupuesto_corriente=Decimal("10"),
        )
        with self.assertRaises(ValidationError):
            fila.full_clean()

    def test_el_anio_informa_lo_que_le_queda_por_asignar(self):
        self.asignar(self.objetivo, self.anio_1, "120000", "80000")

        self.assertEqual(self.anio_1.asignado_a_objetivos, Decimal("200000"))
        self.assertEqual(self.anio_1.sin_asignar_corriente, Decimal("180000"))
        self.assertEqual(self.anio_1.sin_asignar_capital, Decimal("120000"))
        self.assertEqual(self.anio_1.porcentaje_asignado, Decimal("40.00"))

    def test_borrar_el_anio_del_proyecto_se_lleva_sus_asignaciones(self):
        self.asignar(self.objetivo, self.anio_1, "100000")
        self.anio_1.delete()

        self.assertEqual(PresupuestoObjetivoAnual.objects.count(), 0)


class TechoDelObjetivoEnElAnioTests(BaseObjetivoAnualTest):
    """El POA de un objetivo en un año no puede pasarse de lo que le tocó."""

    def setUp(self):
        super().setUp()
        self.asignar(self.objetivo, self.anio_1, "100000", "0")

        self.resultado = self.crear_resultado(
            self.objetivo, presupuesto_corriente=Decimal("100000"),
        )
        self.actividad = Actividad.objects.create(
            resultado=self.resultado, nombre="Actividad",
            presupuesto_corriente=Decimal("100000"),
        )
        self.elegible = GastoElegible.objects.filter(
            gasto__tipo_gasto__transferencia__naturaleza=CORRIENTE
        ).first()

    def _plan(self, anio, monto):
        return PlanDeGasto(
            actividad=self.actividad, gasto_elegible=self.elegible,
            anio=anio, monto=Decimal(monto),
        )

    def test_un_plan_cabe_dentro_de_lo_asignado_al_objetivo(self):
        plan = self._plan(2026, "100000")
        plan.full_clean()  # no revienta

    def test_un_plan_que_supera_lo_del_objetivo_se_rechaza(self):
        """El proyecto tiene $300.000 corriente en 2026, pero este objetivo
        sólo $100.000: el techo que manda es el del objetivo."""
        self.actividad.presupuesto_corriente = Decimal("300000")
        self.resultado.presupuesto_corriente = Decimal("300000")
        self.resultado.save()
        self.actividad.save()

        plan = self._plan(2026, "150000")
        with self.assertRaises(ValidationError) as caso:
            plan.full_clean()
        self.assertIn("monto", caso.exception.message_dict)
        self.assertIn("de este objetivo", str(caso.exception.message_dict))

    def test_sin_asignacion_para_ese_anio_manda_el_techo_del_proyecto(self):
        """El objetivo no tiene reparto en 2027, así que no impone techo."""
        plan = self._plan(2027, "100000")
        plan.full_clean()  # no revienta

    def test_no_se_puede_bajar_la_asignacion_por_debajo_de_lo_planificado(self):
        plan = self._plan(2026, "100000")
        plan.full_clean()
        plan.save()

        fila = self.objetivo.presupuesto_del_anio(self.anio_1)
        fila.presupuesto_corriente = Decimal("40000")
        with self.assertRaises(ValidationError) as caso:
            fila.full_clean()
        self.assertIn("presupuesto_corriente", caso.exception.message_dict)


class VistasDelRepartoTests(BaseObjetivoAnualTest):

    def test_el_editor_del_total_redirige_al_reparto_por_anio(self):
        """Con años cargados, el total deja de editarse a mano."""
        respuesta = self.client.get(
            reverse("proyectos:editar_presupuesto_objetivo", args=[self.objetivo.pk])
        )
        self.assertContains(respuesta, "obj-anual")
        self.assertContains(respuesta, "Año 1")
        self.assertContains(respuesta, "Año 2")

    def test_sin_anios_el_editor_del_total_sigue_funcionando(self):
        """Los proyectos que no repartieron su presupuesto no cambian."""
        self.proyecto.presupuestos_anuales.all().delete()
        respuesta = self.client.get(
            reverse("proyectos:editar_presupuesto_objetivo", args=[self.objetivo.pk])
        )
        self.assertContains(respuesta, "presupuesto_corriente")
        self.assertNotContains(respuesta, "obj-anual")

    def _guardar(self, **montos):
        """Envía la tabla completa, que es como la manda la pantalla."""
        datos = {}
        for anio in (self.anio_1, self.anio_2):
            datos[f"corriente_{anio.pk}"] = montos.get(f"c{anio.numero_anio}", "0")
            datos[f"capital_{anio.pk}"] = montos.get(f"k{anio.numero_anio}", "0")
        return self.client.post(
            reverse("proyectos:guardar_presupuesto_objetivo_anual",
                    args=[self.objetivo.pk]),
            datos,
        )

    def test_guardar_el_reparto_lo_crea_y_actualiza_el_total(self):
        self._guardar(c1="150.000", k1="50.000")
        self.objetivo.refresh_from_db()
        self.assertEqual(self.objetivo.presupuesto_corriente, Decimal("150000"))
        self.assertEqual(self.objetivo.presupuesto_capital, Decimal("50000"))

    def test_se_puede_repartir_entre_los_dos_anios_de_una_vez(self):
        """Lo que antes era imposible: mover plata de un año a otro."""
        self._guardar(c1="150000", c2="120000")
        self.objetivo.refresh_from_db()
        self.assertEqual(self.objetivo.presupuesto_corriente, Decimal("270000"))
        self.assertEqual(
            self.objetivo.presupuesto_del_anio(self.anio_2).presupuesto_corriente,
            Decimal("120000"),
        )

    def test_guardar_de_mas_muestra_el_error_y_no_guarda(self):
        respuesta = self._guardar(c1="999999999")
        self.assertContains(respuesta, "puede llegar hasta")
        self.objetivo.refresh_from_db()
        self.assertEqual(self.objetivo.presupuesto_corriente, Decimal("0"))

    def test_un_anio_sin_presupuesto_en_el_proyecto_lo_dice_claro(self):
        """El mensaje tiene que mandar a repartir el proyecto primero, no
        limitarse a decir que el tope es $0."""
        self.anio_2.presupuesto_corriente = Decimal("0")
        self.anio_2.presupuesto_capital = Decimal("0")
        self.anio_2.save()

        respuesta = self._guardar(c2="10000")
        self.assertContains(respuesta, "Presupuesto por año")

    def test_la_pantalla_ofrece_una_fila_por_anio_del_proyecto(self):
        respuesta = self.client.get(
            reverse("proyectos:presupuesto_objetivo_anual", args=[self.objetivo.pk])
        )
        self.assertEqual(len(respuesta.context["filas"]), 2)
        # El año sin asignación también aparece: es lo que falta repartir.
        self.assertIsNone(respuesta.context["filas"][0]["asignacion"])

    def test_quien_no_es_responsable_no_puede_repartir(self):
        from django.contrib.auth.models import User
        otro = User.objects.create_user("ajeno", password="x")
        self.client.force_login(otro)
        respuesta = self.client.post(
            reverse("proyectos:guardar_presupuesto_objetivo_anual",
                    args=[self.objetivo.pk]),
            {"anio": self.anio_1.pk, "presupuesto_corriente": "1"},
        )
        self.assertEqual(respuesta.status_code, 403)

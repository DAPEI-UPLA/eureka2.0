"""Pruebas del reparto del presupuesto de un resultado por año.

Último escalón del reparto anual: debajo están las actividades, que no se
reparten porque pueden cambiar mientras el resultado se cumpla. El techo de un
resultado en un año es lo que ese año le dio a **su objetivo**.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from .models import (
    Actividad,
    CORRIENTE,
    GastoElegible,
    PlanDeGasto,
    PresupuestoAnual,
    PresupuestoObjetivoAnual,
    PresupuestoResultadoAnual,
)
from .tests import BaseProyectoTest


class BaseResultadoAnualTest(BaseProyectoTest):
    """Proyecto de $1.000.000 en dos años de $500.000 ($300k corriente + $200k
    capital cada uno). Un objetivo con $200.000 corriente y $100.000 capital
    asignados al año 1."""

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
        self.obj_anio_1 = PresupuestoObjetivoAnual.objects.create(
            objetivo=self.objetivo, anio=self.anio_1,
            presupuesto_corriente=Decimal("200000"),
            presupuesto_capital=Decimal("100000"),
        )
        self.resultado = self.crear_resultado(self.objetivo)

    def asignar(self, resultado, anio, corriente="0", capital="0"):
        fila = PresupuestoResultadoAnual(
            resultado=resultado, anio=anio,
            presupuesto_corriente=Decimal(corriente),
            presupuesto_capital=Decimal(capital),
        )
        fila.full_clean()
        fila.save()
        return fila


class RepartoDelResultadoTests(BaseResultadoAnualTest):

    def test_el_total_del_resultado_es_la_suma_de_sus_anios(self):
        self.asignar(self.resultado, self.anio_1, "150000", "60000")

        self.resultado.refresh_from_db()
        self.assertEqual(self.resultado.presupuesto_corriente, Decimal("150000"))
        self.assertEqual(self.resultado.presupuesto_capital, Decimal("60000"))

    def test_el_techo_es_lo_que_el_anio_le_dio_a_su_objetivo(self):
        """El año tiene $300.000 corriente, pero el objetivo sólo $200.000."""
        with self.assertRaises(ValidationError) as caso:
            self.asignar(self.resultado, self.anio_1, "250000")
        mensaje = str(caso.exception.message_dict)
        self.assertIn("del objetivo", mensaje)

    def test_los_resultados_hermanos_comparten_el_techo_del_objetivo(self):
        otro = self.crear_resultado(self.objetivo)
        self.asignar(self.resultado, self.anio_1, "150000")
        with self.assertRaises(ValidationError):
            self.asignar(otro, self.anio_1, "100000")

    def test_un_anio_sin_reparto_del_objetivo_se_rechaza(self):
        """El objetivo no tiene nada en 2027, así que el resultado tampoco puede."""
        with self.assertRaises(ValidationError) as caso:
            self.asignar(self.resultado, self.anio_2, "10000")
        self.assertIn(
            "no tiene presupuesto asignado",
            str(caso.exception.message_dict),
        )

    def test_las_bolsas_se_topan_por_separado(self):
        self.asignar(self.resultado, self.anio_1, "0", "100000")
        otro = self.crear_resultado(self.objetivo)
        with self.assertRaises(ValidationError):
            self.asignar(otro, self.anio_1, "0", "1")

    def test_borrar_una_asignacion_recalcula_el_total(self):
        fila = self.asignar(self.resultado, self.anio_1, "150000")
        fila.delete()

        self.resultado.refresh_from_db()
        self.assertEqual(self.resultado.presupuesto_corriente, Decimal("0"))

    def test_borrar_el_anio_se_lleva_la_asignacion(self):
        self.asignar(self.resultado, self.anio_1, "150000")
        self.anio_1.delete()
        self.assertEqual(PresupuestoResultadoAnual.objects.count(), 0)


class TechoDelResultadoEnElAnioTests(BaseResultadoAnualTest):
    """El POA de un resultado en un año no puede pasarse de lo que le tocó."""

    def setUp(self):
        super().setUp()
        self.asignar(self.resultado, self.anio_1, "100000", "0")
        self.actividad = Actividad.objects.create(
            resultado=self.resultado, nombre="Actividad",
        )
        self.elegible = GastoElegible.objects.filter(
            gasto__tipo_gasto__transferencia__naturaleza=CORRIENTE
        ).first()

    def _plan(self, anio, monto):
        return PlanDeGasto(
            resultado=self.resultado, actividad=self.actividad, gasto_elegible=self.elegible,
            anio=anio, monto=Decimal(monto),
        )

    def test_un_plan_cabe_dentro_de_lo_asignado_al_resultado(self):
        self._plan(2026, "100000").full_clean()  # no revienta

    def test_un_plan_que_supera_lo_del_resultado_se_rechaza(self):
        """El objetivo tiene $200.000 en 2026, pero este resultado sólo
        $100.000: manda el techo más bajo."""
        self.resultado.presupuesto_corriente = Decimal("200000")
        self.resultado.save(update_fields=["presupuesto_corriente"])
        self.actividad.presupuesto_corriente = Decimal("200000")
        self.actividad.save()

        plan = self._plan(2026, "150000")
        with self.assertRaises(ValidationError) as caso:
            plan.full_clean()
        self.assertIn("de este resultado", str(caso.exception.message_dict))

    def test_no_se_puede_bajar_por_debajo_de_lo_planificado(self):
        plan = self._plan(2026, "100000")
        plan.full_clean()
        plan.save()

        fila = self.resultado.presupuesto_del_anio(self.anio_1)
        fila.presupuesto_corriente = Decimal("40000")
        with self.assertRaises(ValidationError) as caso:
            fila.full_clean()
        self.assertIn("presupuesto_corriente", caso.exception.message_dict)

    def test_las_actividades_no_se_reparten_por_anio(self):
        """Decisión explícita: las actividades pueden cambiar mientras el
        resultado se cumpla, así que no tienen reparto anual propio."""
        self.assertFalse(hasattr(self.actividad, "presupuestos_anuales"))


class VistasDelRepartoResultadoTests(BaseResultadoAnualTest):

    def test_el_form_del_total_redirige_al_reparto_por_anio(self):
        respuesta = self.client.get(
            reverse("proyectos:form_asignar_presupuesto", args=[self.resultado.pk])
        )
        self.assertContains(respuesta, "presupuesto-res-")
        self.assertContains(respuesta, "Año 1")

    def test_sin_reparto_en_el_objetivo_el_form_del_total_sigue_igual(self):
        self.obj_anio_1.delete()
        respuesta = self.client.get(
            reverse("proyectos:form_asignar_presupuesto", args=[self.resultado.pk])
        )
        self.assertNotContains(respuesta, "presupuesto-res-")

    def test_solo_se_ofrecen_los_anios_en_que_el_objetivo_tiene_plata(self):
        """El objetivo sólo reparte el año 1: ofrecer el 2 llevaría a un error
        seguro al guardar."""
        respuesta = self.client.get(
            reverse("proyectos:presupuesto_resultado_anual", args=[self.resultado.pk])
        )
        self.assertEqual(len(respuesta.context["filas"]), 1)
        self.assertEqual(respuesta.context["filas"][0]["anio"].pk, self.anio_1.pk)

    def _guardar(self, corriente="0", capital="0"):
        """Envía la tabla completa; el objetivo sólo reparte el año 1."""
        return self.client.post(
            reverse("proyectos:guardar_presupuesto_resultado_anual",
                    args=[self.resultado.pk]),
            {
                f"corriente_{self.anio_1.pk}": corriente,
                f"capital_{self.anio_1.pk}": capital,
            },
        )

    def test_guardar_el_reparto_actualiza_el_total(self):
        self._guardar("150.000", "60.000")
        self.resultado.refresh_from_db()
        self.assertEqual(self.resultado.presupuesto_corriente, Decimal("150000"))
        self.assertEqual(self.resultado.presupuesto_capital, Decimal("60000"))

    def test_guardar_de_mas_muestra_el_error_y_no_guarda(self):
        respuesta = self._guardar("999999999")
        self.assertContains(respuesta, "puede llegar hasta")
        self.resultado.refresh_from_db()
        self.assertEqual(self.resultado.presupuesto_corriente, Decimal("0"))

    def test_quien_no_es_responsable_no_puede_repartir(self):
        otro = User.objects.create_user("ajeno", password="x")
        self.client.force_login(otro)
        respuesta = self.client.post(
            reverse("proyectos:guardar_presupuesto_resultado_anual",
                    args=[self.resultado.pk]),
            {"anio": self.anio_1.pk, "presupuesto_corriente": "1"},
        )
        self.assertEqual(respuesta.status_code, 403)

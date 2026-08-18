"""El POA cuelga del resultado y la actividad ya no lleva presupuesto.

Decisión del equipo: el dinero se compromete a nivel de resultado y se detiene
ahí. Las actividades son el medio para cumplirlo y pueden cambiar, fusionarse o
aparecer sobre la marcha; si el POA colgara de ellas, reordenar el trabajo
borraría la planificación financiera.

La actividad se puede indicar en un plan como referencia de para qué es el
gasto, pero es opcional y borrarla no se lleva la línea del POA.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.urls import reverse

from .models import (
    Actividad,
    CAPITAL,
    CORRIENTE,
    Egreso,
    GastoElegible,
    PlanDeGasto,
    PresupuestoAnual,
    PresupuestoObjetivoAnual,
    PresupuestoResultadoAnual,
)
from .tests import BaseProyectoTest


class BasePoaTest(BaseProyectoTest):
    """Proyecto $1.000.000 en dos años; un objetivo y un resultado con
    $200.000 corriente y $100.000 capital en 2026."""

    def setUp(self):
        super().setUp()
        for numero, calendario in ((1, 2026), (2, 2027)):
            PresupuestoAnual.objects.create(
                proyecto=self.proyecto, numero_anio=numero,
                anio_calendario=calendario,
                presupuesto_corriente=Decimal("300000"),
                presupuesto_capital=Decimal("200000"),
            )
        self.a2026 = self.proyecto.presupuesto_del_calendario(2026)
        self.a2027 = self.proyecto.presupuesto_del_calendario(2027)

        self.objetivo = self.crear_objetivo()
        PresupuestoObjetivoAnual.objects.create(
            objetivo=self.objetivo, anio=self.a2026,
            presupuesto_corriente=Decimal("200000"),
            presupuesto_capital=Decimal("100000"),
        )
        self.resultado = self.crear_resultado(self.objetivo)
        PresupuestoResultadoAnual.objects.create(
            resultado=self.resultado, anio=self.a2026,
            presupuesto_corriente=Decimal("200000"),
            presupuesto_capital=Decimal("100000"),
        )
        self.actividad = Actividad.objects.create(
            resultado=self.resultado, nombre="Taller",
        )
        self.corriente = GastoElegible.objects.filter(
            gasto__tipo_gasto__transferencia__naturaleza=CORRIENTE
        ).first()
        self.capital = GastoElegible.objects.filter(
            gasto__tipo_gasto__transferencia__naturaleza=CAPITAL
        ).first()

    def plan(self, monto, anio=2026, elegible=None, actividad=None):
        return PlanDeGasto(
            resultado=self.resultado,
            actividad=actividad,
            gasto_elegible=elegible or self.corriente,
            anio=anio,
            monto=Decimal(monto),
        )


class ElPlanCuelgaDelResultadoTests(BasePoaTest):

    def test_un_plan_sin_actividad_es_valido(self):
        p = self.plan("100000")
        p.full_clean()
        p.save()
        self.assertIsNone(p.actividad)

    def test_se_puede_indicar_una_actividad_como_referencia(self):
        p = self.plan("100000", actividad=self.actividad)
        p.full_clean()
        p.save()
        self.assertEqual(p.actividad, self.actividad)

    def test_la_actividad_debe_ser_del_mismo_resultado(self):
        otro = self.crear_resultado(self.objetivo)
        ajena = Actividad.objects.create(resultado=otro, nombre="Ajena")

        p = self.plan("10000", actividad=ajena)
        with self.assertRaises(ValidationError) as caso:
            p.full_clean()
        self.assertIn("actividad", caso.exception.message_dict)

    def test_borrar_la_actividad_no_se_lleva_el_plan(self):
        """El motivo de todo el cambio: reordenar el trabajo no puede borrar
        la planificación financiera."""
        p = self.plan("100000", actividad=self.actividad)
        p.full_clean()
        p.save()

        self.actividad.delete()
        p.refresh_from_db()
        self.assertIsNone(p.actividad)
        self.assertEqual(p.monto, Decimal("100000"))
        self.assertEqual(p.resultado, self.resultado)

    def test_borrar_el_resultado_si_se_lleva_sus_planes(self):
        p = self.plan("100000")
        p.full_clean()
        p.save()

        self.resultado.delete()
        self.assertEqual(PlanDeGasto.objects.count(), 0)

    def test_no_se_repite_la_linea_de_resultado_gasto_y_anio(self):
        self.plan("50000").save()
        with self.assertRaises(IntegrityError):
            self.plan("50000").save()

    def test_el_mismo_gasto_cabe_en_otro_anio(self):
        PresupuestoResultadoAnual.objects.create(
            resultado=self.resultado, anio=self.a2027,
            presupuesto_corriente=Decimal("100000"),
        )
        PresupuestoObjetivoAnual.objects.create(
            objetivo=self.objetivo, anio=self.a2027,
            presupuesto_corriente=Decimal("100000"),
        )
        self.plan("50000", anio=2026).save()
        p = self.plan("50000", anio=2027)
        p.full_clean()
        p.save()
        self.assertEqual(PlanDeGasto.objects.count(), 2)


class TechoDelPoaTests(BasePoaTest):
    """El tope de un plan es el presupuesto de su resultado en su año."""

    def test_cabe_lo_que_el_resultado_tiene_ese_anio(self):
        self.plan("200000").full_clean()  # no revienta

    def test_no_cabe_mas_de_lo_que_el_resultado_tiene(self):
        with self.assertRaises(ValidationError) as caso:
            self.plan("250000").full_clean()
        self.assertIn("monto", caso.exception.message_dict)

    def test_las_bolsas_se_topan_por_separado(self):
        """Que sobre corriente no habilita a pasarse en capital."""
        self.plan("200000").save()
        p = self.plan("150000", elegible=self.capital)
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_un_anio_sin_presupuesto_del_resultado_se_rechaza(self):
        p = self.plan("10000", anio=2027)
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_bajar_el_presupuesto_del_resultado_respeta_el_poa(self):
        self.plan("200000").save()
        fila = self.resultado.presupuesto_del_anio(self.a2026)
        fila.presupuesto_corriente = Decimal("50000")
        with self.assertRaises(ValidationError) as caso:
            fila.full_clean()
        self.assertIn("presupuesto_corriente", caso.exception.message_dict)

    def test_el_resultado_reporta_lo_planificado(self):
        self.plan("120000").save()
        self.plan("80000", elegible=self.capital).save()

        self.assertEqual(self.resultado.corriente_distribuido, Decimal("120000"))
        self.assertEqual(self.resultado.capital_distribuido, Decimal("80000"))
        self.assertEqual(self.resultado.presupuesto_distribuido, Decimal("200000"))


class CumplimientoSinPresupuestoTests(BasePoaTest):
    """Sin monto en las actividades, el avance del resultado es promedio simple."""

    def test_todas_las_actividades_pesan_igual(self):
        self.actividad.cumplimiento = Decimal("100")
        self.actividad.save()
        otra = Actividad.objects.create(resultado=self.resultado, nombre="Otra")
        otra.cumplimiento = Decimal("0")
        otra.save()

        self.assertEqual(self.resultado.cumplimiento, Decimal("50.00"))

    def test_un_resultado_sin_actividades_va_en_cero(self):
        self.actividad.delete()
        self.assertEqual(self.resultado.cumplimiento, Decimal("0"))


class ElGastoVaAlAnioDeSuPlanTests(BasePoaTest):
    """Un gasto consume el presupuesto del año de su plan, no el de su fecha."""

    def setUp(self):
        super().setUp()
        self.plan_2026 = self.plan("200000")
        self.plan_2026.save()
        # Pagado en enero del año siguiente, contra un plan de 2026.
        self.egreso = Egreso.objects.create(
            proyecto=self.proyecto, tipo=Egreso.TIPO_COMPRA,
            subtipo_compra=Egreso.SUB_BIENES_INSUMOS,
            estado=Egreso.ESTADO_PAGADO,
            plan_de_gasto=self.plan_2026, gasto_elegible=self.corriente,
            cantidad=1, valor_sin_iva=Decimal("100000"),
            fecha="2027-01-15",
        )

    def test_cuenta_en_el_anio_del_plan_y_no_en_el_de_la_fecha(self):
        self.assertEqual(self.a2026.gastos_total, Decimal("119000"))
        self.assertEqual(self.a2027.gastos_total, Decimal("0"))

    def test_el_filtro_de_la_lista_usa_el_anio_del_plan(self):
        url = reverse("proyectos:listar_egresos", args=[self.proyecto.pk])

        en_2026 = self.client.get(url, {"anio": 2026})
        self.assertEqual(len(en_2026.context["egresos"]), 1)

        en_2027 = self.client.get(url, {"anio": 2027})
        self.assertEqual(len(en_2027.context["egresos"]), 0)

    def test_los_anios_que_ofrece_el_filtro_salen_del_poa(self):
        url = reverse("proyectos:listar_egresos", args=[self.proyecto.pk])
        self.assertEqual(self.client.get(url).context["anios"], [2026])


class FormularioDelPlanTests(BasePoaTest):

    def test_el_form_ofrece_la_actividad_como_opcional(self):
        respuesta = self.client.get(
            reverse("proyectos:crear_plan_gasto_form", args=[self.proyecto.pk]),
            {"resultado": self.resultado.pk},
        )
        self.assertContains(respuesta, "Sin actividad específica")
        self.assertContains(respuesta, "(opcional)")

    def test_se_crea_un_plan_sin_elegir_actividad(self):
        respuesta = self.client.post(
            reverse("proyectos:crear_plan_gasto", args=[self.proyecto.pk]),
            {
                "resultado": self.resultado.pk,
                "actividad": "",
                "gasto_elegible": self.corriente.pk,
                "anio": "2026",
                "monto": "150.000",
            },
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.content.decode()[:300])
        plan = PlanDeGasto.objects.get()
        self.assertEqual(plan.resultado, self.resultado)
        self.assertIsNone(plan.actividad)
        self.assertEqual(plan.monto, Decimal("150000"))

    def test_un_plan_que_se_pasa_devuelve_el_motivo(self):
        respuesta = self.client.post(
            reverse("proyectos:crear_plan_gasto", args=[self.proyecto.pk]),
            {
                "resultado": self.resultado.pk,
                "gasto_elegible": self.corriente.pk,
                "anio": "2026",
                "monto": "999.999.999",
            },
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(PlanDeGasto.objects.count(), 0)

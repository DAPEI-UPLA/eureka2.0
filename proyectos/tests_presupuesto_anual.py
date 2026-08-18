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

from .models import (
    CORRIENTE,
    Actividad,
    GastoElegible,
    PlanDeGasto,
    PresupuestoAnual,
    PresupuestoObjetivoAnual,
    PresupuestoResultadoAnual,
)
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


class SelectorDeAnioTests(BaseGastosTest):
    """El selector filtra el dinero, nunca la estructura.

    `BaseGastosTest` deja planes por $600.000 corriente y $400.000 capital,
    todos en 2026.
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
        # Los planes de BaseGastosTest no caben en un año de $300.000/$200.000.
        PlanDeGasto.objects.filter(pk=self.plan_corriente.pk).update(
            monto=Decimal("300000")
        )
        PlanDeGasto.objects.filter(pk=self.plan_capital.pk).update(
            monto=Decimal("200000")
        )
        self.url = reverse("proyectos:detalle_proyecto", args=[self.proyecto.pk])

    def test_el_detalle_ofrece_un_boton_por_anio(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Todo el proyecto")
        self.assertContains(respuesta, "Año 1")
        self.assertContains(respuesta, "Año 2")

    def test_sin_anio_se_ve_el_proyecto_completo(self):
        respuesta = self.client.get(self.url)
        self.assertIsNone(respuesta.context["anio_sel"])

    def test_elegir_un_anio_lo_deja_seleccionado(self):
        respuesta = self.client.get(self.url, {"anio": 2027})
        self.assertEqual(respuesta.context["anio_sel"].numero_anio, 2)
        self.assertContains(respuesta, "Viendo")

    def test_un_anio_que_no_existe_cae_a_todo_el_proyecto(self):
        """Mejor mostrar el proyecto entero que una pantalla vacía."""
        respuesta = self.client.get(self.url, {"anio": 2099})
        self.assertIsNone(respuesta.context["anio_sel"])

    def test_un_anio_con_basura_no_revienta(self):
        respuesta = self.client.get(self.url, {"anio": "no-soy-un-año"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(respuesta.context["anio_sel"])

    def test_los_planes_de_gasto_se_filtran_por_anio(self):
        url = reverse("proyectos:listar_planes_gasto", args=[self.proyecto.pk])

        completo = self.client.get(url)
        self.assertEqual(len(completo.context["planes"]), 2)

        en_2026 = self.client.get(url, {"anio": 2026})
        self.assertEqual(len(en_2026.context["planes"]), 2)

        en_2027 = self.client.get(url, {"anio": 2027})
        self.assertEqual(len(en_2027.context["planes"]), 0)

    def test_el_dashboard_muestra_las_cifras_del_anio(self):
        url = reverse("proyectos:dashboard_proyecto", args=[self.proyecto.pk])
        respuesta = self.client.get(url, {"anio": 2026})
        anio = respuesta.context["anio_sel"]

        self.assertEqual(anio.presupuesto_total, Decimal("500000"))
        self.assertEqual(anio.planificado, Decimal("500000"))
        self.assertEqual(anio.disponible, Decimal("0"))
        self.assertContains(respuesta, "Presupuesto 2026")

    def test_el_ano_sin_poa_queda_con_todo_disponible(self):
        url = reverse("proyectos:dashboard_proyecto", args=[self.proyecto.pk])
        respuesta = self.client.get(url, {"anio": 2027})
        anio = respuesta.context["anio_sel"]

        self.assertEqual(anio.planificado, Decimal("0"))
        self.assertEqual(anio.disponible, Decimal("500000"))

    def test_la_estructura_no_se_filtra_por_anio(self):
        """Los objetivos y actividades son los mismos todos los años: elegir un
        año no puede hacerlos desaparecer."""
        url = reverse("proyectos:listar_objetivos", args=[self.proyecto.pk])
        completo = self.client.get(url)
        en_2027 = self.client.get(url, {"anio": 2027})
        self.assertEqual(
            completo.context["proyecto"].objetivos.count(),
            en_2027.context["proyecto"].objetivos.count(),
        )

    def test_el_anio_no_lleva_separador_de_miles(self):
        """Django localiza los enteros y el año salía como «2 026».

        En el texto sólo se ve feo, pero en el enlace del selector rompía el
        filtro: `?anio=2 026` no se puede leer como número, así que apretar un
        año no hacía nada. El año es un identificador, no una cantidad.
        """
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "?anio=2026")
        self.assertNotContains(respuesta, "?anio=2&nbsp;026")
        self.assertNotContains(respuesta, "?anio=2\xa0026")

    def test_los_comentarios_del_template_no_se_imprimen(self):
        """`{# … #}` de Django es de una sola línea.

        Los comentarios de varias líneas se colaban tal cual en el HTML de la
        página: se veía el texto explicativo del template encima del selector.
        """
        respuesta = self.client.get(self.url)
        cuerpo = respuesta.content.decode()
        self.assertNotIn("{#", cuerpo)
        self.assertNotIn("SELECTOR DE AÑO", cuerpo)


class RedistribuirEntreAniosTests(BaseProyectoTest):
    """Mover plata de un año a otro.

    El defecto reportado: con todo el presupuesto en el Año 1 —como lo dejó la
    migración— no había forma de ponerle plata al Año 2. El tope es la SUMA de
    los años, así que bajar el 1 y subir el 2 son dos pasos y cada uno por
    separado es inválido. Ahora la tabla entera se guarda junta.
    """

    def setUp(self):
        super().setUp()
        self.a1 = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=1, anio_calendario=2026,
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
        self.client.post(reverse("proyectos:crear_anio", args=[self.proyecto.pk]))
        self.a2 = self.proyecto.presupuestos_anuales.get(numero_anio=2)
        self.url = reverse("proyectos:guardar_anios", args=[self.proyecto.pk])

    def _post(self, c1, k1, c2, k2):
        return self.client.post(self.url, {
            f"corriente_{self.a1.pk}": c1, f"capital_{self.a1.pk}": k1,
            f"corriente_{self.a2.pk}": c2, f"capital_{self.a2.pk}": k2,
        })

    def test_se_puede_pasar_plata_del_anio_1_al_anio_2(self):
        self._post("400000", "250000", "200000", "150000")

        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.assertEqual(self.a1.presupuesto_corriente, Decimal("400000"))
        self.assertEqual(self.a2.presupuesto_corriente, Decimal("200000"))
        self.assertEqual(self.a2.presupuesto_capital, Decimal("150000"))
        self.assertTrue(self.proyecto.anios_cuadrados)

    def test_la_suma_sigue_topada_por_el_presupuesto_del_proyecto(self):
        respuesta = self._post("600000", "400000", "1", "0")

        self.assertContains(respuesta, "sobran")
        self.a2.refresh_from_db()
        self.assertEqual(self.a2.presupuesto_corriente, Decimal("0"))

    def test_un_reparto_rechazado_no_guarda_nada(self):
        """O entra entero o no entra: si el Año 1 bajara y el Año 2 fuera
        rechazado, el proyecto quedaría con plata desaparecida."""
        self._post("100000", "0", "999999999", "0")

        self.a1.refresh_from_db()
        self.assertEqual(self.a1.presupuesto_corriente, Decimal("600000"))

    def test_el_error_muestra_los_montos_escritos_no_los_guardados(self):
        respuesta = self._post("600000", "400000", "50000", "0")
        cuerpo = respuesta.content.decode().replace("\xa0", "").replace(".", "")
        self.assertIn('value="50000"', cuerpo)

    def test_reenviar_los_montos_ya_formateados_no_los_pierde(self):
        """La trampa del separador de miles.

        Los inputs se pintan formateados y con `USE_THOUSAND_SEPARATOR` Django
        agrupa con espacio duro (U+00A0). Si se guarda sin tocar nada, eso vuelve
        tal cual al servidor: si no se limpiara, el presupuesto se iría a $0.
        """
        self._post("400\xa0000", "250\xa0000", "200\xa0000", "150\xa0000")

        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.assertEqual(self.a1.presupuesto_corriente, Decimal("400000"))
        self.assertEqual(self.a2.presupuesto_capital, Decimal("150000"))

    def test_no_se_puede_bajar_un_anio_por_debajo_de_su_poa(self):
        objetivo = self.crear_objetivo(presupuesto_corriente=Decimal("600000"))
        resultado = self.crear_resultado(objetivo, presupuesto_corriente=Decimal("600000"))
        actividad = Actividad.objects.create(
            resultado=resultado, nombre="A", presupuesto_corriente=Decimal("600000"),
        )
        PlanDeGasto.objects.create(
            actividad=actividad,
            gasto_elegible=GastoElegible.objects.filter(
                gasto__tipo_gasto__transferencia__naturaleza=CORRIENTE
            ).first(),
            anio=2026, monto=Decimal("500000"),
        )

        respuesta = self._post("100000", "400000", "500000", "0")
        self.assertContains(respuesta, "ya suman")
        self.a1.refresh_from_db()
        self.assertEqual(self.a1.presupuesto_corriente, Decimal("600000"))


class MontosSegunElAnioTests(BaseProyectoTest):
    """Con un año elegido, objetivos y resultados muestran lo de ESE año.

    El defecto reportado: estando en el Año 2 se veía el presupuesto total del
    objetivo, que incluye el Año 1.
    """

    def setUp(self):
        super().setUp()
        self.a1 = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=1, anio_calendario=2026,
            presupuesto_corriente=Decimal("300000"),
            presupuesto_capital=Decimal("200000"),
        )
        self.a2 = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=2, anio_calendario=2027,
            presupuesto_corriente=Decimal("300000"),
            presupuesto_capital=Decimal("200000"),
        )
        self.objetivo = self.crear_objetivo()
        PresupuestoObjetivoAnual.objects.create(
            objetivo=self.objetivo, anio=self.a1,
            presupuesto_corriente=Decimal("100000"),
        )
        PresupuestoObjetivoAnual.objects.create(
            objetivo=self.objetivo, anio=self.a2,
            presupuesto_corriente=Decimal("50000"),
        )
        self.url = reverse("proyectos:listar_objetivos", args=[self.proyecto.pk])

    def _sin_formato(self, respuesta):
        return respuesta.content.decode().replace("\xa0", "").replace(".", "").replace(",", "")

    def test_sin_anio_se_ve_el_total(self):
        self.objetivo.refresh_from_db()
        self.assertEqual(self.objetivo.presupuesto_corriente, Decimal("150000"))
        self.assertIn("150000", self._sin_formato(self.client.get(self.url)))

    def test_con_un_anio_se_ve_solo_lo_de_ese_anio(self):
        cuerpo = self._sin_formato(self.client.get(self.url, {"anio": 2027}))
        self.assertNotIn("150000", cuerpo)

    def test_un_objetivo_sin_asignacion_en_el_anio_sale_en_cero(self):
        otro = self.crear_objetivo()
        respuesta = self.client.get(self.url, {"anio": 2027})
        montos = [
            o.montos for o in respuesta.context["objetivos"] if o.pk == otro.pk
        ][0]
        self.assertEqual(montos.presupuesto_corriente, Decimal("0"))

    def test_los_resultados_tambien_respetan_el_anio(self):
        resultado = self.crear_resultado(self.objetivo)
        PresupuestoResultadoAnual.objects.create(
            resultado=resultado, anio=self.a2,
            presupuesto_corriente=Decimal("40000"),
        )
        respuesta = self.client.get(
            reverse("proyectos:listar_resultados", args=[self.objetivo.pk]),
            {"anio": 2027},
        )
        montos = respuesta.context["resultados"][0].montos
        self.assertEqual(montos.presupuesto_corriente, Decimal("40000"))

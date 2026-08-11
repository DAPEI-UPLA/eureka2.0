import tempfile
from datetime import date, time
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from .importador import ImportadorTablero
from .models import (
    Actividad,
    CostoActividad,
    CostoDirecto,
    CostoTransversal,
    DiaActividad,
    GastoExtra,
    Institucion,
    LineaFinanciera,
    MetaAnual,
    Propuesta,
    ReservaZoom,
    SalaZoom,
    SesionClase,
    SupuestosFinancieros,
)


class BaseOtec(TestCase):
    """Sesión iniciada y una institución: todas las vistas piden login."""

    def setUp(self):
        self.usuario = get_user_model().objects.create_user("tester", password="clave")
        self.client.force_login(self.usuario)
        self.institucion = Institucion.objects.create(nombre="Servicio Nacional")

    def crear_actividad(self, nombre, dias, propuesta=None):
        propuesta = propuesta or Propuesta.objects.create(
            codigo=f"PROP-{nombre[:6]}", institucion=self.institucion, anio=2026
        )
        actividad = Actividad.objects.create(propuesta=propuesta, nombre=nombre)
        for fecha in dias:
            DiaActividad.objects.create(actividad=actividad, fecha=fecha)
        return actividad


class CartaGanttFiltroCursoTests(BaseOtec):
    """El filtro por curso de la carta Gantt."""

    def setUp(self):
        super().setUp()
        # Dos cursos que no se pisan y uno que corre junto al primero: el
        # tercero es el que hace que la fila de paralelo tenga algo que decir.
        self.agosto = self.crear_actividad(
            "Diplomado en Gestión", [date(2026, 8, 3), date(2026, 8, 4)]
        )
        self.septiembre = self.crear_actividad(
            "Curso de Excel", [date(2026, 9, 7), date(2026, 9, 8)]
        )
        self.paralelo = self.crear_actividad(
            "Taller de Liderazgo", [date(2026, 8, 3)]
        )
        self.url = reverse("otec:carta_gantt")

    def test_sin_filtro_se_ven_todos_los_cursos(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["filas"]), 3)
        # Cuatro fechas distintas: el taller comparte el 3 de agosto.
        self.assertEqual(len(r.context["fechas"]), 4)

    def test_filtrar_por_curso_deja_solo_ese_curso(self):
        r = self.client.get(self.url, {"curso": self.septiembre.pk})
        filas = r.context["filas"]
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["actividad"], self.septiembre)
        self.assertEqual(r.context["curso_activo"], self.septiembre)

    def test_la_grilla_se_recorta_a_los_dias_del_curso(self):
        """Aislar un curso y seguir mostrando 124 columnas no serviría de nada."""
        r = self.client.get(self.url, {"curso": self.septiembre.pk})
        self.assertEqual(
            r.context["fechas"], [date(2026, 9, 7), date(2026, 9, 8)]
        )
        # Y los meses ofrecidos son los de ese curso, no los de la cartera.
        self.assertEqual([m["etiqueta"] for m in r.context["meses"]], ["Septiembre 2026"])

    def test_el_filtro_de_mes_sigue_funcionando_junto_al_de_curso(self):
        r = self.client.get(
            self.url, {"curso": self.agosto.pk, "mes": "2026-8"}
        )
        self.assertEqual(len(r.context["filas"]), 1)
        self.assertTrue(all(f.month == 8 for f in r.context["fechas"]))
        self.assertTrue(r.context["hay_filtro"])

    def test_las_actividades_en_paralelo_cuentan_todos_los_cursos(self):
        """Al aislar uno, lo que interesa es cuántos más corren esos días."""
        r = self.client.get(self.url, {"curso": self.agosto.pk})
        conteos = {p["fecha"]: p["n"] for p in r.context["paralelo"]}
        self.assertEqual(conteos[date(2026, 8, 3)], 2)  # con el taller
        self.assertEqual(conteos[date(2026, 8, 4)], 1)

    def test_un_curso_inexistente_no_rompe_la_pantalla(self):
        r = self.client.get(self.url, {"curso": "99999"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["filas"]), 3)
        self.assertIsNone(r.context["curso_activo"])

    def test_un_curso_no_numerico_se_ignora(self):
        r = self.client.get(self.url, {"curso": "cualquier-cosa"})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["curso_activo"])

    def test_el_desplegable_ofrece_los_cursos_en_orden_alfabetico(self):
        r = self.client.get(self.url)
        nombres = [c["actividad"].nombre for c in r.context["cursos"]]
        self.assertEqual(nombres, sorted(nombres))
        self.assertEqual(len(nombres), 3)

    def test_los_cursos_estimados_tambien_se_pueden_filtrar(self):
        """Los que no tienen días marcados entran con su tramo estimado."""
        propuesta = Propuesta.objects.create(
            codigo="PROP-EST", institucion=self.institucion, anio=2026
        )
        estimado = Actividad.objects.create(
            propuesta=propuesta,
            nombre="Curso sin calendarizar",
            fecha_inicio=date(2026, 10, 5),
            fecha_termino=date(2026, 10, 7),
        )
        r = self.client.get(self.url, {"curso": estimado.pk})
        self.assertEqual(len(r.context["filas"]), 1)
        self.assertTrue(r.context["filas"][0]["estimada"])
        self.assertEqual(len(r.context["fechas"]), 3)


class FlujoDeCajaTests(BaseOtec):
    """Los botones de edición del flujo de caja."""

    def setUp(self):
        super().setUp()
        self.linea = LineaFinanciera.objects.create(
            codigo="ING-001",
            institucion=self.institucion,
            descripcion="Diplomado en Gestión",
            certeza=LineaFinanciera.Certeza.CONFIRMADO,
            monto_contratado=Decimal("12000000"),
            fecha_pago_estimada=date(2026, 9, 30),
        )
        self.transversal = CostoTransversal.objects.create(
            codigo="CT-001",
            descripcion="Coordinación OTEC",
            monto=Decimal("2400000"),
            fecha_pago=date(2026, 9, 1),
        )

    def test_la_pantalla_ofrece_editar_cada_cosa(self):
        r = self.client.get(reverse("otec:flujo_caja"), {"anio": 2026})
        html = r.content.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn(reverse("otec:editar_linea", args=[self.linea.pk]), html)
        self.assertIn(
            reverse("otec:editar_costo_transversal", args=[self.transversal.pk]), html
        )
        self.assertIn(reverse("otec:editar_supuestos", args=[2026]), html)
        self.assertIn(reverse("otec:editar_meta", args=[2026]), html)

    def test_el_anio_no_lleva_separador_de_miles(self):
        """Un año no es una cantidad: «2 026» además rompía el enlace de vuelta.

        La configuración agrupa los miles para la plata, y sin `unlocalize` eso
        alcanzaba también al año, tanto en los títulos como en el `?anio=` que
        lleva de vuelta al año correcto después de guardar.
        """
        html = self.client.get(reverse("otec:flujo_caja"), {"anio": 2026}).content.decode()
        self.assertNotIn("2\xa0026", html)
        self.assertIn("Flujo de caja 2026", html)
        self.assertIn("?anio=2026", html)
        self.assertIn('<option value="2026"', html)

    def test_guardar_devuelve_al_anio_desde_el_que_se_abrio(self):
        r = self.client.post(
            reverse("otec:editar_meta", args=[2026]) + "?anio=2026",
            {"monto": "1000"},
            follow=True,
        )
        self.assertEqual(r.context["anio"], 2026)

    def test_una_linea_sin_fecha_de_pago_sigue_siendo_alcanzable(self):
        """Sin fecha no entra en ningún mes: es la que más hay que poder abrir."""
        LineaFinanciera.objects.all().update(fecha_pago_estimada=None)
        CostoTransversal.objects.all().update(fecha_pago=None)
        r = self.client.get(reverse("otec:flujo_caja"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context.get("sin_datos"))
        self.assertIn(
            reverse("otec:editar_linea", args=[self.linea.pk]), r.content.decode()
        )

    def test_sin_ningun_dato_se_muestra_la_pantalla_vacia(self):
        LineaFinanciera.objects.all().delete()
        CostoTransversal.objects.all().delete()
        r = self.client.get(reverse("otec:flujo_caja"))
        self.assertTrue(r.context["sin_datos"])

    # --- Supuestos -------------------------------------------------------

    def test_los_porcentajes_se_editan_en_porcentaje(self):
        """El modelo guarda 0,15 pero nadie razona el reparto así."""
        SupuestosFinancieros.objects.create(anio=2026, pct_upla=Decimal("0.15"))
        html = self.client.get(
            reverse("otec:editar_supuestos", args=[2026])
        ).content.decode()
        self.assertIn('name="pct_upla"', html)
        self.assertIn('value="15"', html)
        self.assertNotIn('value="0.1500"', html)

    def test_guardar_supuestos_los_crea_si_no_existian(self):
        r = self.client.post(
            reverse("otec:editar_supuestos", args=[2026]) + "?anio=2026",
            {
                "saldo_inicial": "8000000",
                "fecha_corte": "2026-08-31",
                "saldo_minimo": "3000000",
                "pct_upla": "20",
                "pct_otec": "10",
                "pct_autoaprendizaje": "50",
                "valor_hora_relatoria": "35000",
                "plazo_pago_costos_dias": "40",
            },
        )
        self.assertRedirects(r, reverse("otec:flujo_caja") + "?anio=2026")
        supuestos = SupuestosFinancieros.objects.get(anio=2026)
        self.assertEqual(supuestos.saldo_inicial, Decimal("8000000"))
        self.assertEqual(supuestos.pct_upla, Decimal("0.20"))
        self.assertEqual(supuestos.pct_otec, Decimal("0.10"))
        self.assertEqual(supuestos.pct_autoaprendizaje, Decimal("0.50"))

    def test_un_porcentaje_imposible_se_rechaza(self):
        r = self.client.post(
            reverse("otec:editar_supuestos", args=[2026]),
            {
                "saldo_inicial": "0", "saldo_minimo": "0",
                "pct_upla": "150", "pct_otec": "15", "pct_autoaprendizaje": "50",
                "valor_hora_relatoria": "0", "plazo_pago_costos_dias": "40",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(SupuestosFinancieros.objects.exists())

    # --- Meta ------------------------------------------------------------

    def test_guardar_la_meta_la_crea_si_no_existia(self):
        r = self.client.post(
            reverse("otec:editar_meta", args=[2026]) + "?anio=2026",
            {"monto": "120000000"},
        )
        self.assertRedirects(r, reverse("otec:flujo_caja") + "?anio=2026")
        self.assertEqual(
            MetaAnual.objects.get(anio=2026).monto, Decimal("120000000")
        )

    # --- Línea de ingreso y sus costos ------------------------------------

    def datos_linea(self, **extra):
        datos = {
            "codigo": "ING-001",
            "institucion": self.institucion.pk,
            "descripcion": "Diplomado en Gestión",
            "estado": LineaFinanciera.EstadoLinea.CONTRATADA,
            "certeza": LineaFinanciera.Certeza.CONFIRMADO,
            "participantes": "30",
            "horas": "120",
            "fecha_pago_estimada": "2026-09-30",
            "valor_ofertado": "0",
            "monto_contratado": "15000000",
            "monto_facturado": "0",
            "monto_pagado": "0",
            "costos-relatoria": "3000000",
            "costos-materiales": "0",
            "costos-plataformas": "0",
            "costos-certificaciones": "0",
            "costos-traslados": "0",
            "costos-alimentacion": "0",
            "costos-arriendo": "0",
            "costos-otros": "0",
            "costos-fecha_pago_estimada": "2026-10-15",
        }
        datos.update(extra)
        return datos

    def test_editar_una_linea_guarda_tambien_sus_costos(self):
        r = self.client.post(
            reverse("otec:editar_linea", args=[self.linea.pk]) + "?anio=2026",
            self.datos_linea(),
        )
        self.assertRedirects(r, reverse("otec:flujo_caja") + "?anio=2026")

        self.linea.refresh_from_db()
        self.assertEqual(self.linea.monto_contratado, Decimal("15000000"))
        costo = CostoDirecto.objects.get(linea=self.linea)
        self.assertEqual(costo.relatoria, Decimal("3000000"))
        self.assertEqual(costo.fecha_egreso, date(2026, 10, 15))

    def test_el_cambio_se_ve_reflejado_en_el_flujo(self):
        """El punto de poder editar: la caja se recalcula, no se copia."""
        self.client.post(
            reverse("otec:editar_linea", args=[self.linea.pk]),
            self.datos_linea(),
        )
        r = self.client.get(reverse("otec:flujo_caja"), {"anio": 2026})
        self.assertEqual(r.context["r"]["total_ingresos"], Decimal("15000000"))

    def test_no_se_puede_pagar_mas_de_lo_facturado(self):
        r = self.client.post(
            reverse("otec:editar_linea", args=[self.linea.pk]),
            self.datos_linea(monto_facturado="1000", monto_pagado="5000"),
        )
        self.assertEqual(r.status_code, 200)
        self.linea.refresh_from_db()
        self.assertEqual(self.linea.monto_contratado, Decimal("12000000"))

    def test_no_se_puede_repetir_el_codigo_de_una_linea(self):
        otra = LineaFinanciera.objects.create(
            codigo="ING-002", institucion=self.institucion, descripcion="Otra"
        )
        r = self.client.post(
            reverse("otec:editar_linea", args=[otra.pk]),
            self.datos_linea(codigo="ING-001", descripcion="Otra"),
        )
        self.assertEqual(r.status_code, 200)
        otra.refresh_from_db()
        self.assertEqual(otra.codigo, "ING-002")

    # --- Costo transversal ------------------------------------------------

    def test_editar_un_costo_transversal(self):
        r = self.client.post(
            reverse("otec:editar_costo_transversal", args=[self.transversal.pk])
            + "?anio=2026",
            {
                "codigo": "CT-001",
                "tipo": "Personal",
                "descripcion": "Coordinación OTEC",
                "area": "Gestión",
                "monto": "3000000",
                "fecha_pago": "2026-09-01",
                "criterio": "",
                "fuente_financiamiento": "",
                "incluir_en_flujo": "on",
                "observacion": "",
            },
        )
        self.assertRedirects(r, reverse("otec:flujo_caja") + "?anio=2026")
        self.transversal.refresh_from_db()
        self.assertEqual(self.transversal.monto, Decimal("3000000"))

    def test_excluir_un_costo_lo_saca_de_la_caja(self):
        self.client.post(
            reverse("otec:editar_costo_transversal", args=[self.transversal.pk]),
            {
                "codigo": "CT-001",
                "tipo": "",
                "descripcion": "Coordinación OTEC",
                "area": "",
                "monto": "2400000",
                "fecha_pago": "2026-09-01",
                "criterio": "",
                "fuente_financiamiento": "",
                "observacion": "",
            },
        )
        self.transversal.refresh_from_db()
        self.assertFalse(self.transversal.incluir_en_flujo)
        r = self.client.get(reverse("otec:flujo_caja"), {"anio": 2026})
        self.assertEqual(r.context["r"]["costos_transversales"], Decimal("0"))


class DesgloseDeCostosTests(BaseOtec):
    """Los costos de un curso, abiertos por categoría más las líneas libres."""

    def setUp(self):
        super().setUp()
        self.propuesta = Propuesta.objects.create(
            codigo="PROP-COST", institucion=self.institucion, anio=2026
        )
        self.actividad = Actividad.objects.create(
            propuesta=self.propuesta,
            nombre="Diplomado en Gestión",
            horas=40,
            valor_ofertado=Decimal("5000000"),
        )

    def test_sin_desglose_los_costos_son_cero(self):
        """La propiedad tiene que funcionar antes de que exista el desglose."""
        self.assertEqual(self.actividad.costo_relatoria, Decimal("0"))
        self.assertEqual(self.actividad.otros_gastos, Decimal("0"))
        self.assertEqual(self.actividad.costo_total, Decimal("0"))
        self.assertEqual(self.actividad.excedente_estimado, Decimal("5000000"))

    def test_relatoria_y_otros_gastos_salen_del_desglose(self):
        CostoActividad.objects.create(
            actividad=self.actividad,
            relatoria=Decimal("1500000"),
            materiales=Decimal("180000"),
            traslados=Decimal("90000"),
        )
        actividad = Actividad.objects.get(pk=self.actividad.pk)
        self.assertEqual(actividad.costo_relatoria, Decimal("1500000"))
        # Todo lo que no es relatoría cae en "otros gastos", como en la planilla.
        self.assertEqual(actividad.otros_gastos, Decimal("270000"))
        self.assertEqual(actividad.costo_total, Decimal("1770000"))

    def test_los_gastos_extras_tambien_cuentan(self):
        CostoActividad.objects.create(
            actividad=self.actividad, relatoria=Decimal("1500000")
        )
        GastoExtra.objects.create(
            actividad=self.actividad, descripcion="Coffee break", monto=Decimal("55000")
        )
        GastoExtra.objects.create(
            actividad=self.actividad, descripcion="Traslado", monto=Decimal("90000")
        )
        actividad = Actividad.objects.get(pk=self.actividad.pk)
        self.assertEqual(actividad.otros_gastos, Decimal("145000"))
        self.assertEqual(actividad.costo_total, Decimal("1645000"))
        self.assertEqual(actividad.excedente_estimado, Decimal("3355000"))
        self.assertEqual(actividad.margen_estimado_pct, 67)

    def test_el_desglose_lista_solo_lo_que_tiene_monto(self):
        CostoActividad.objects.create(
            actividad=self.actividad,
            relatoria=Decimal("1500000"),
            materiales=Decimal("180000"),
        )
        GastoExtra.objects.create(
            actividad=self.actividad, descripcion="Coffee break", monto=Decimal("55000")
        )
        etiquetas = [l["label"] for l in self.actividad.desglose_costos()]
        self.assertEqual(
            etiquetas,
            ["Honorarios de relatoría", "Materiales e insumos", "Coffee break"],
        )

    # --- Por el formulario ------------------------------------------------

    def datos_actividad(self, **extra):
        """Lo mínimo que pide el formulario de actividad, con formsets vacíos."""
        datos = {
            "propuesta": self.propuesta.pk,
            "nombre": "Curso nuevo",
            "modalidad": Actividad.Modalidad.ELEARNING,
            "prioridad": Actividad.Prioridad.MEDIA,
            "n_participantes": "20",
            "horas": "40",
            "horas_asincronicas": "0",
            "tipo_relator": Actividad.TipoRelator.NO_DEFINIDO,
            "estado_ejecucion": Actividad.EstadoEjecucion.NO_PROGRAMADA,
            "valor_ofertado": "5000000",
            "monto_adjudicado": "0",
            "monto_facturado": "0",
            "monto_pagado": "0",
            "responsable_seguimiento": "",
            "observaciones": "",
            "n_factura": "",
            # Formset con su fila en blanco: no debe pedir que se llene.
            "extras-TOTAL_FORMS": "1",
            "extras-INITIAL_FORMS": "0",
            "extras-MIN_NUM_FORMS": "0",
            "extras-MAX_NUM_FORMS": "1000",
            "extras-0-descripcion": "",
            "extras-0-monto": "",
            # Categorías del desglose.
            "relatoria": "0",
            "materiales": "0",
            "plataformas": "0",
            "certificaciones": "0",
            "traslados": "0",
            "alimentacion": "0",
            "arriendo": "0",
            "otros": "0",
        }
        datos.update(extra)
        return datos

    def test_crear_una_actividad_con_su_desglose(self):
        datos = self.datos_actividad(relatoria="1500000", materiales="180000")
        datos["extras-0-descripcion"] = "Coffee break"
        datos["extras-0-monto"] = "55000"

        r = self.client.post(reverse("otec:crear_actividad"), datos)
        self.assertEqual(r.status_code, 302, r.content.decode()[:2000])

        actividad = Actividad.objects.get(nombre="Curso nuevo")
        self.assertEqual(actividad.costos.relatoria, Decimal("1500000"))
        self.assertEqual(actividad.otros_gastos, Decimal("235000"))
        self.assertEqual(actividad.gastos_extra.count(), 1)

    def test_una_fila_de_gasto_extra_en_blanco_no_estorba(self):
        """El formset ofrece siempre una fila de más; vacía se ignora."""
        r = self.client.post(
            reverse("otec:crear_actividad"), self.datos_actividad(relatoria="800000")
        )
        self.assertEqual(r.status_code, 302, r.content.decode()[:2000])
        actividad = Actividad.objects.get(nombre="Curso nuevo")
        self.assertEqual(actividad.gastos_extra.count(), 0)
        self.assertEqual(actividad.costo_relatoria, Decimal("800000"))

    def test_guardar_desde_el_sistema_marca_el_desglose(self):
        """La marca es la que impide que el Excel lo pise en la próxima carga."""
        self.client.post(
            reverse("otec:crear_actividad"), self.datos_actividad(relatoria="800000")
        )
        actividad = Actividad.objects.get(nombre="Curso nuevo")
        self.assertTrue(actividad.costos.editado_en_sistema)

    def test_la_fila_en_blanco_llega_con_un_cero_desde_el_navegador(self):
        """El campo se dibuja con el 0 por defecto, así que eso es lo que llega."""
        datos = self.datos_actividad(relatoria="800000")
        datos["extras-0-monto"] = "0"
        r = self.client.post(reverse("otec:crear_actividad"), datos)
        self.assertEqual(r.status_code, 302, r.content.decode()[:2000])
        self.assertEqual(
            Actividad.objects.get(nombre="Curso nuevo").gastos_extra.count(), 0
        )

    def test_sin_costos_no_se_crea_un_desglose_vacio(self):
        r = self.client.post(reverse("otec:crear_actividad"), self.datos_actividad())
        self.assertEqual(r.status_code, 302, r.content.decode()[:2000])
        actividad = Actividad.objects.get(nombre="Curso nuevo")
        self.assertFalse(CostoActividad.objects.filter(actividad=actividad).exists())

    def test_editar_sin_tocar_los_costos_no_los_desconecta_del_excel(self):
        """Corregir el nombre del curso no es decidir que el Excel deje de mandar."""
        CostoActividad.objects.create(
            actividad=self.actividad, relatoria=Decimal("1500000")
        )
        datos = self.datos_actividad(
            nombre="Diplomado en Gestión Patrimonial", relatoria="1500000"
        )
        datos["extras-INITIAL_FORMS"] = "0"
        r = self.client.post(
            reverse("otec:editar_actividad", args=[self.actividad.pk]), datos
        )
        self.assertEqual(r.status_code, 302, r.content.decode()[:2000])

        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.nombre, "Diplomado en Gestión Patrimonial")
        self.assertFalse(self.actividad.costos.editado_en_sistema)

    def test_tocar_un_monto_si_marca_el_desglose(self):
        CostoActividad.objects.create(
            actividad=self.actividad, relatoria=Decimal("1500000")
        )
        datos = self.datos_actividad(relatoria="1800000")
        datos["extras-INITIAL_FORMS"] = "0"
        self.client.post(
            reverse("otec:editar_actividad", args=[self.actividad.pk]), datos
        )
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.costos.relatoria, Decimal("1800000"))
        self.assertTrue(self.actividad.costos.editado_en_sistema)

    def test_el_detalle_muestra_el_desglose(self):
        CostoActividad.objects.create(
            actividad=self.actividad,
            relatoria=Decimal("1500000"),
            traslados=Decimal("90000"),
        )
        html = self.client.get(
            reverse("otec:detalle_actividad", args=[self.actividad.pk])
        ).content.decode()
        self.assertIn("Honorarios de relatoría", html)
        self.assertIn("Traslados y viáticos", html)
        self.assertNotIn("Alimentación", html)  # sin monto, no se lista


class HorasAsincronicasTests(BaseOtec):
    """Las horas asincrónicas son parte del total, no horas aparte."""

    def setUp(self):
        super().setUp()
        self.propuesta = Propuesta.objects.create(
            codigo="PROP-HORAS", institucion=self.institucion, anio=2026
        )
        self.actividad = Actividad.objects.create(
            propuesta=self.propuesta,
            nombre="E-learning mixto",
            horas=40,
            horas_asincronicas=Decimal("16"),
            fecha_inicio=date(2026, 8, 3),
            fecha_termino=date(2026, 9, 25),
        )

    def test_las_sincronicas_son_el_resto(self):
        self.assertEqual(self.actividad.horas_sincronicas, Decimal("24"))

    def test_no_puede_haber_mas_asincronicas_que_horas(self):
        self.actividad.horas_asincronicas = Decimal("50")
        with self.assertRaises(ValidationError) as capturado:
            self.actividad.full_clean()
        self.assertIn("horas_asincronicas", capturado.exception.error_dict)

    def test_el_formulario_rechaza_el_descuadre(self):
        datos = DesgloseDeCostosTests.datos_actividad(
            self, horas="40", horas_asincronicas="50"
        )
        datos["propuesta"] = self.propuesta.pk
        r = self.client.post(reverse("otec:crear_actividad"), datos)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Actividad.objects.filter(nombre="Curso nuevo").exists())
        self.assertIn("no puede tener 50 h asincrónicas", r.content.decode())

    def test_las_clases_se_comparan_contra_las_horas_en_vivo(self):
        """Antes se comparaba contra el total y ningún e-learning cuadraba."""
        for dia in (3, 10, 17, 24):  # cuatro lunes de 3 h cada uno
            SesionClase.objects.create(
                actividad=self.actividad, fecha=date(2026, 8, dia),
                hora_inicio=time(18, 0), duracion_horas=Decimal("6.0"),
            )
        actividad = Actividad.objects.get(pk=self.actividad.pk)
        self.assertEqual(actividad.horas_programadas, Decimal("24.0"))
        self.assertTrue(actividad.cuadran_las_horas)

    def test_avisa_cuando_faltan_clases(self):
        SesionClase.objects.create(
            actividad=self.actividad, fecha=date(2026, 8, 3),
            hora_inicio=time(18, 0), duracion_horas=Decimal("8.0"),
        )
        actividad = Actividad.objects.get(pk=self.actividad.pk)
        self.assertFalse(actividad.cuadran_las_horas)
        self.assertEqual(actividad.horas_por_programar, Decimal("16.0"))

    def test_las_clases_no_tienen_que_seguir_ningun_patron(self):
        """El caso que motivó el cambio: fechas y horas a gusto del relator."""
        for fecha, hora, duracion in (
            (date(2026, 8, 10), time(14, 0), "8.0"),   # lunes
            (date(2026, 8, 11), time(13, 0), "8.0"),   # martes
            (date(2026, 8, 17), time(20, 0), "8.0"),   # lunes, otra hora
        ):
            SesionClase.objects.create(
                actividad=self.actividad, fecha=fecha,
                hora_inicio=hora, duracion_horas=Decimal(duracion),
            )
        actividad = Actividad.objects.get(pk=self.actividad.pk)
        self.assertEqual(actividad.horas_programadas, Decimal("24.0"))
        self.assertTrue(actividad.cuadran_las_horas)

    def test_dos_grupos_en_paralelo_no_duplican_las_horas(self):
        """Cada grupo repite las mismas horas: el curso sigue durando lo mismo."""
        sala = SalaZoom.objects.create(nombre="Sala 1")
        for grupo, hora in (("A", time(18, 0)), ("B", time(20, 0))):
            for dia in (3, 10, 17, 24):
                SesionClase.objects.create(
                    actividad=self.actividad, grupo=grupo,
                    fecha=date(2026, 8, dia), hora_inicio=hora,
                    duracion_horas=Decimal("6.0"), sala=sala,
                )
        actividad = Actividad.objects.get(pk=self.actividad.pk)
        self.assertEqual(actividad.horas_programadas, Decimal("24.0"))
        self.assertTrue(actividad.cuadran_las_horas)

    def test_sin_clases_no_se_puede_opinar(self):
        self.assertIsNone(self.actividad.cuadran_las_horas)

    def test_las_horas_del_gantt_se_muestran_como_contraste(self):
        for dia in (5, 12):
            DiaActividad.objects.create(
                actividad=self.actividad, fecha=date(2026, 8, dia),
                horas_asincronicas=Decimal("4.0"),
            )
        actividad = Actividad.objects.get(pk=self.actividad.pk)
        self.assertEqual(actividad.horas_asincronicas_en_gantt, Decimal("8.0"))
        html = self.client.get(
            reverse("otec:detalle_actividad", args=[actividad.pk])
        ).content.decode()
        self.assertIn("8 h", html)


class ImportadorCostosTests(BaseOtec):
    """El Excel solo trae dos totales; el desglose es más fino que eso."""

    COLUMNAS = [
        "ID Propuesta", "Institución Cliente", "Actividad/Curso", "Año",
        "Horas", "Valor Ofertado", "Costo Relatoría", "Otros gastos",
    ]

    def planilla(self, **celdas):
        """Un .xlsx mínimo con la hoja que el importador espera."""
        from openpyxl import Workbook

        fila = {
            "ID Propuesta": "PROP-2026-001",
            "Institución Cliente": "Servicio Nacional",
            "Actividad/Curso": "Diplomado en Gestión",
            "Año": 2026,
            "Horas": 40,
            "Valor Ofertado": 5000000,
            "Costo Relatoría": 1500000,
            "Otros gastos": 300000,
        }
        fila.update(celdas)

        libro = Workbook()
        hoja = libro.active
        hoja.title = "Registro Actividades"
        hoja.append(self.COLUMNAS)
        hoja.append([fila[c] for c in self.COLUMNAS])

        ruta = Path(tempfile.mkdtemp()) / "tablero.xlsx"
        libro.save(ruta)
        return ruta

    def importar(self, ruta, **opciones):
        return ImportadorTablero(ruta, **opciones).ejecutar(aplicar=True)

    def test_los_dos_totales_del_excel_llegan_al_desglose(self):
        self.importar(self.planilla())

        actividad = Actividad.objects.get(nombre="Diplomado en Gestión")
        self.assertEqual(actividad.costos.relatoria, Decimal("1500000"))
        self.assertEqual(actividad.costos.otros, Decimal("300000"))
        # Y las propiedades siguen dando lo mismo que daban las columnas.
        self.assertEqual(actividad.costo_relatoria, Decimal("1500000"))
        self.assertEqual(actividad.otros_gastos, Decimal("300000"))

    def test_un_desglose_hecho_a_mano_no_se_pisa(self):
        """La planilla trae dos totales: volcarlos borraría el detalle abierto."""
        self.importar(self.planilla())
        actividad = Actividad.objects.get(nombre="Diplomado en Gestión")
        costos = actividad.costos
        costos.otros = Decimal("0")
        costos.materiales = Decimal("180000")
        costos.traslados = Decimal("120000")
        costos.editado_en_sistema = True
        costos.save()

        resultado = self.importar(self.planilla(**{"Otros gastos": 999999}))

        costos.refresh_from_db()
        self.assertEqual(costos.materiales, Decimal("180000"))
        self.assertEqual(costos.otros, Decimal("0"))
        self.assertTrue(
            any("desglosados en el sistema" in a for a in resultado.avisos),
            resultado.avisos,
        )

    def test_se_puede_pedir_que_mande_el_excel(self):
        self.importar(self.planilla())
        costos = Actividad.objects.get(nombre="Diplomado en Gestión").costos
        costos.materiales = Decimal("180000")
        costos.editado_en_sistema = True
        costos.save()

        self.importar(
            self.planilla(**{"Otros gastos": 999999}), sobrescribir_ediciones=True
        )

        costos.refresh_from_db()
        self.assertEqual(costos.otros, Decimal("999999"))
        self.assertFalse(costos.editado_en_sistema)

    def test_una_columna_de_monto_vacia_en_todo_el_archivo_se_ignora(self):
        """Es la firma de un .xlsx guardado sin recalcular las fórmulas."""
        self.importar(self.planilla())

        resultado = self.importar(self.planilla(**{"Costo Relatoría": None}))

        costos = Actividad.objects.get(nombre="Diplomado en Gestión").costos
        self.assertEqual(costos.relatoria, Decimal("1500000"))
        self.assertTrue(
            any("Costo Relatoría" in a for a in resultado.avisos), resultado.avisos
        )

    def test_sin_montos_no_se_crea_un_desglose_vacio(self):
        self.importar(
            self.planilla(**{"Costo Relatoría": 0, "Otros gastos": 0})
        )
        actividad = Actividad.objects.get(nombre="Diplomado en Gestión")
        self.assertFalse(CostoActividad.objects.filter(actividad=actividad).exists())
        self.assertEqual(actividad.costo_total, Decimal("0"))


class MigracionDelDesgloseTests(TransactionTestCase):
    """La migración que traspasa los dos totales viejos al desglose.

    Importa porque el servidor ya tiene montos cargados: si el traspaso se
    hiciera mal, se perderían sin que nadie lo note. Se recorre la migración de
    verdad, hacia adelante y hacia atrás.
    """

    ANTES = ("otec", "0011_horarioclase")
    DESPUES = ("otec", "0012_desglose_costos_y_horas_asincronicas")

    def migrar(self, destino):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([destino])
        executor.loader.build_graph()
        return executor.loader.project_state([destino]).apps

    def tearDown(self):
        # Las demás pruebas esperan la base al día.
        self.migrar(self.DESPUES)

    def sembrar(self, apps):
        Institucion = apps.get_model("otec", "Institucion")
        Propuesta = apps.get_model("otec", "Propuesta")
        Actividad = apps.get_model("otec", "Actividad")

        institucion = Institucion.objects.create(nombre="Servicio Nacional")
        propuesta = Propuesta.objects.create(
            codigo="PROP-2026-001", institucion=institucion, anio=2026
        )
        Actividad.objects.create(
            propuesta=propuesta, nombre="Con costos",
            costo_relatoria=Decimal("1500000"), otros_gastos=Decimal("300000"),
        )
        Actividad.objects.create(
            propuesta=propuesta, nombre="Sin costos",
            costo_relatoria=Decimal("0"), otros_gastos=Decimal("0"),
        )

    def test_los_montos_viejos_quedan_en_el_desglose(self):
        self.sembrar(self.migrar(self.ANTES))
        apps = self.migrar(self.DESPUES)

        CostoActividad = apps.get_model("otec", "CostoActividad")
        costos = CostoActividad.objects.get(actividad__nombre="Con costos")
        self.assertEqual(costos.relatoria, Decimal("1500000"))
        self.assertEqual(costos.otros, Decimal("300000"))

        # La que no tenía montos no estrena una fila de ceros.
        self.assertFalse(
            CostoActividad.objects.filter(actividad__nombre="Sin costos").exists()
        )

    def test_la_vuelta_atras_aplana_el_detalle_en_los_dos_totales(self):
        self.sembrar(self.migrar(self.ANTES))
        apps = self.migrar(self.DESPUES)

        # Alguien abre el detalle antes de que haya que revertir.
        CostoActividad = apps.get_model("otec", "CostoActividad")
        GastoExtra = apps.get_model("otec", "GastoExtra")
        costos = CostoActividad.objects.get(actividad__nombre="Con costos")
        costos.otros = Decimal("0")
        costos.materiales = Decimal("180000")
        costos.traslados = Decimal("120000")
        costos.save()
        GastoExtra.objects.create(
            actividad_id=costos.actividad_id, descripcion="Coffee", monto=Decimal("50000")
        )

        apps = self.migrar(self.ANTES)

        Actividad = apps.get_model("otec", "Actividad")
        actividad = Actividad.objects.get(nombre="Con costos")
        self.assertEqual(actividad.costo_relatoria, Decimal("1500000"))
        # Lo que no es relatoría vuelve al saco de "otros gastos", extras incluidos.
        self.assertEqual(actividad.otros_gastos, Decimal("350000"))


class CalendarioDelCursoTests(BaseOtec):
    """Colocar las clases una por una, con la fecha y la hora que tengan."""

    def setUp(self):
        super().setUp()
        self.propuesta = Propuesta.objects.create(
            codigo="PROP-CAL", institucion=self.institucion, anio=2026
        )
        self.actividad = Actividad.objects.create(
            propuesta=self.propuesta, nombre="Herramientas de Gestión",
            horas=16, horas_asincronicas=Decimal("10"),
            fecha_inicio=date(2026, 8, 3), fecha_termino=date(2026, 8, 28),
        )
        self.sala = SalaZoom.objects.create(nombre="Sala 1")
        self.url = reverse("otec:calendario_curso", args=[self.actividad.pk])

    def datos(self, **extra):
        datos = {
            "fecha": "2026-08-10",
            "hora_inicio": "14:00",
            "duracion_horas": "2.0",
            "sala": "",
            "grupo": "",
            "mes": "2026-8",
        }
        datos.update(extra)
        return datos

    def test_el_calendario_se_abre_en_el_mes_del_curso(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["mes_nombre"], "Agosto")
        self.assertEqual(r.context["anio"], 2026)
        # Seis columnas por semana más el relleno de los meses vecinos.
        self.assertTrue(all(len(s) == 7 for s in r.context["semanas"]))

    def test_agregar_una_clase(self):
        r = self.client.post(self.url, self.datos())
        self.assertEqual(r.status_code, 302, r.content.decode()[:1500])

        sesion = self.actividad.sesiones.get()
        self.assertEqual(sesion.fecha, date(2026, 8, 10))
        self.assertEqual(sesion.hora_inicio, time(14, 0))
        self.assertEqual(sesion.hora_fin, time(16, 0))

    def test_las_clases_no_siguen_ningun_patron(self):
        """El caso reportado: lunes 14:00, martes 13:00, lunes 20:00."""
        self.client.post(self.url, self.datos(fecha="2026-08-10", hora_inicio="14:00"))
        self.client.post(self.url, self.datos(fecha="2026-08-11", hora_inicio="13:00"))
        self.client.post(self.url, self.datos(fecha="2026-08-17", hora_inicio="20:00"))

        fechas = [(s.fecha, s.hora_inicio) for s in self.actividad.sesiones.all()]
        self.assertEqual(fechas, [
            (date(2026, 8, 10), time(14, 0)),
            (date(2026, 8, 11), time(13, 0)),
            (date(2026, 8, 17), time(20, 0)),
        ])
        self.assertEqual(
            Actividad.objects.get(pk=self.actividad.pk).horas_programadas,
            Decimal("6.0"),
        )

    def test_la_clase_marca_su_dia_en_la_carta_gantt(self):
        self.client.post(self.url, self.datos())
        dia = DiaActividad.objects.get(actividad=self.actividad)
        self.assertEqual(dia.fecha, date(2026, 8, 10))
        self.assertEqual(dia.tipo, DiaActividad.Tipo.EJECUCION)

    def test_quitar_la_clase_desmarca_el_dia(self):
        self.client.post(self.url, self.datos())
        sesion = self.actividad.sesiones.get()

        r = self.client.post(reverse("otec:eliminar_sesion", args=[sesion.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(self.actividad.sesiones.exists())
        self.assertFalse(DiaActividad.objects.filter(actividad=self.actividad).exists())

    def test_un_dia_con_horas_asincronicas_no_se_desmarca(self):
        """Ese día tiene sentido propio aunque ya no haya clase en vivo."""
        self.client.post(self.url, self.datos())
        dia = DiaActividad.objects.get(actividad=self.actividad)
        dia.horas_asincronicas = Decimal("4.0")
        dia.save()

        self.client.post(
            reverse("otec:eliminar_sesion", args=[self.actividad.sesiones.get().pk])
        )
        self.assertTrue(DiaActividad.objects.filter(actividad=self.actividad).exists())

    def test_dos_clases_el_mismo_dia_dejan_el_dia_marcado(self):
        self.client.post(self.url, self.datos(hora_inicio="09:00"))
        self.client.post(self.url, self.datos(hora_inicio="14:00"))
        primera = self.actividad.sesiones.first()

        self.client.post(reverse("otec:eliminar_sesion", args=[primera.pk]))
        self.assertEqual(self.actividad.sesiones.count(), 1)
        self.assertTrue(DiaActividad.objects.filter(actividad=self.actividad).exists())

    def test_no_se_puede_pisar_la_sala_de_otro_curso(self):
        otra = Actividad.objects.create(
            propuesta=self.propuesta, nombre="Portugués Básico", horas=8
        )
        SesionClase.objects.create(
            actividad=otra, fecha=date(2026, 8, 10), hora_inicio=time(13, 0),
            duracion_horas=Decimal("1.5"), sala=self.sala,
        )

        r = self.client.post(
            self.url, self.datos(hora_inicio="14:00", sala=self.sala.pk)
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("Portugués Básico", r.content.decode())
        self.assertFalse(self.actividad.sesiones.exists())

    def test_la_misma_sala_a_otra_hora_si_se_puede(self):
        otra = Actividad.objects.create(
            propuesta=self.propuesta, nombre="Portugués Básico", horas=8
        )
        SesionClase.objects.create(
            actividad=otra, fecha=date(2026, 8, 10), hora_inicio=time(9, 0),
            duracion_horas=Decimal("2.0"), sala=self.sala,
        )
        r = self.client.post(
            self.url, self.datos(hora_inicio="14:00", sala=self.sala.pk)
        )
        self.assertEqual(r.status_code, 302, r.content.decode()[:1500])

    # --- Choques contra las reservas del Tablero -------------------------
    #
    # Casi toda la ocupación real de las salas viene de las reservas
    # importadas, no de las clases cargadas en el sistema: comprobar solo
    # contra las clases dejaba el aviso sin efecto.

    def reserva(self, hora, duracion=2, actividad=None, etiqueta="Otro curso"):
        return ReservaZoom.objects.create(
            sala=self.sala,
            fecha=date(2026, 8, 10),
            hora_inicio=hora,
            hora_fin=time(hora.hour + duracion, hora.minute),
            actividad=actividad,
            etiqueta=etiqueta,
        )

    def test_no_se_puede_pisar_una_reserva_del_tablero(self):
        self.reserva(time(13, 0), etiqueta="Oratoria y Comunicación Efectiva")

        r = self.client.post(
            self.url, self.datos(hora_inicio="14:00", sala=self.sala.pk)
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("Oratoria y Comunicación Efectiva", r.content.decode())
        self.assertIn("Tablero", r.content.decode())
        self.assertFalse(self.actividad.sesiones.exists())

    def test_una_reserva_a_otra_hora_no_estorba(self):
        self.reserva(time(8, 0))
        r = self.client.post(
            self.url, self.datos(hora_inicio="14:00", sala=self.sala.pk)
        )
        self.assertEqual(r.status_code, 302, r.content.decode()[:1500])

    def test_una_reserva_en_otra_sala_no_estorba(self):
        otra_sala = SalaZoom.objects.create(nombre="Sala 2")
        ReservaZoom.objects.create(
            sala=otra_sala, fecha=date(2026, 8, 10),
            hora_inicio=time(14, 0), hora_fin=time(16, 0), etiqueta="Otro curso",
        )
        r = self.client.post(
            self.url, self.datos(hora_inicio="14:00", sala=self.sala.pk)
        )
        self.assertEqual(r.status_code, 302, r.content.decode()[:1500])

    def test_la_reserva_del_propio_curso_no_choca_consigo_misma(self):
        """Suele ser esta misma clase, tal como venía en el Tablero."""
        self.reserva(time(14, 0), actividad=self.actividad)
        r = self.client.post(
            self.url, self.datos(hora_inicio="14:00", sala=self.sala.pk)
        )
        self.assertEqual(r.status_code, 302, r.content.decode()[:1500])

    def test_una_reserva_sin_bloque_horario_no_bloquea(self):
        """Las hay sin hora en el Tablero; no se puede saber si se pisan."""
        ReservaZoom.objects.create(
            sala=self.sala, fecha=date(2026, 8, 10), etiqueta="Sin bloque",
        )
        r = self.client.post(
            self.url, self.datos(hora_inicio="14:00", sala=self.sala.pk)
        )
        self.assertEqual(r.status_code, 302, r.content.decode()[:1500])

    def test_sin_sala_no_hay_nada_que_comprobar(self):
        self.reserva(time(13, 0))
        r = self.client.post(self.url, self.datos(hora_inicio="14:00", sala=""))
        self.assertEqual(r.status_code, 302, r.content.decode()[:1500])

    def test_el_calendario_marca_los_choques_que_ya_venian(self):
        sesion = SesionClase.objects.create(
            actividad=self.actividad, fecha=date(2026, 8, 10),
            hora_inicio=time(14, 0), duracion_horas=Decimal("2.0"), sala=self.sala,
        )
        self.reserva(time(13, 0), etiqueta="Oratoria y Comunicación Efectiva")

        r = self.client.get(self.url)
        self.assertEqual(r.context["n_conflictos"], 1)
        self.assertIn("Oratoria y Comunicación Efectiva", r.content.decode())
        self.assertEqual(sesion.choques()[0]["nombre"], "Oratoria y Comunicación Efectiva")

    def test_editar_una_clase_ya_cargada(self):
        self.client.post(self.url, self.datos())
        sesion = self.actividad.sesiones.get()

        self.client.post(
            self.url,
            self.datos(fecha="2026-08-12", hora_inicio="18:30", sesion=sesion.pk),
        )
        sesion.refresh_from_db()
        self.assertEqual(sesion.fecha, date(2026, 8, 12))
        self.assertEqual(sesion.hora_inicio, time(18, 30))
        # El día viejo se soltó y el nuevo quedó marcado.
        marcados = set(
            DiaActividad.objects
            .filter(actividad=self.actividad)
            .values_list("fecha", flat=True)
        )
        self.assertEqual(marcados, {date(2026, 8, 12)})

    def test_al_hacer_clic_en_un_dia_el_formulario_llega_con_esa_fecha(self):
        r = self.client.get(self.url, {"fecha": "2026-08-19"})
        self.assertEqual(r.context["form"]["fecha"].value(), date(2026, 8, 19))

    def test_la_segunda_clase_hereda_la_forma_de_la_primera(self):
        """Cambian las fechas, no la duración ni la sala: repetirlas es trabajo inventado."""
        self.client.post(
            self.url,
            self.datos(hora_inicio="15:00", duracion_horas="3.0", sala=self.sala.pk),
        )
        r = self.client.get(self.url, {"fecha": "2026-08-19"})
        form = r.context["form"]
        self.assertEqual(form["hora_inicio"].value(), time(15, 0))
        self.assertEqual(form["duracion_horas"].value(), Decimal("3.0"))
        self.assertEqual(form["sala"].value(), self.sala.pk)

    def test_las_clases_aparecen_en_el_calendario_de_salas(self):
        self.client.post(
            self.url, self.datos(fecha="2026-08-10", sala=self.sala.pk)
        )
        r = self.client.get(reverse("otec:calendario_zoom"), {"semana": "2026-08-10"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Herramientas de Gestión", r.content.decode())

    def test_la_ficha_enlaza_al_calendario(self):
        html = self.client.get(
            reverse("otec:detalle_actividad", args=[self.actividad.pk])
        ).content.decode()
        self.assertIn(self.url, html)


class MigracionDeSesionesTests(TransactionTestCase):
    """La migración que expande cada regla semanal en clases concretas.

    Es la que corre sobre los cursos ya cargados: si expandiera mal, los
    horarios que hoy existen se perderían o se duplicarían.
    """

    ANTES = ("otec", "0012_desglose_costos_y_horas_asincronicas")
    DESPUES = ("otec", "0013_sesiones_de_clase")

    def migrar(self, destino):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([destino])
        executor.loader.build_graph()
        return executor.loader.project_state([destino]).apps

    def tearDown(self):
        self.migrar(self.DESPUES)

    def sembrar(self, apps):
        Institucion = apps.get_model("otec", "Institucion")
        Propuesta = apps.get_model("otec", "Propuesta")
        Actividad = apps.get_model("otec", "Actividad")
        HorarioClase = apps.get_model("otec", "HorarioClase")
        Feriado = apps.get_model("otec", "Feriado")

        institucion = Institucion.objects.create(nombre="Servicio Nacional")
        propuesta = Propuesta.objects.create(
            codigo="PROP-1", institucion=institucion, anio=2026
        )
        actividad = Actividad.objects.create(
            propuesta=propuesta, nombre="Con horario", horas=16,
            fecha_inicio=date(2026, 8, 3), fecha_termino=date(2026, 8, 31),
        )
        # Lunes 18:00, 2 h. Entre el 3 y el 31 de agosto hay cinco lunes,
        # pero el 17 es feriado.
        Feriado.objects.create(fecha=date(2026, 8, 17), nombre="Feriado de prueba")
        HorarioClase.objects.create(
            actividad=actividad, dias="0", hora_inicio=time(18, 0),
            duracion_horas=Decimal("2.0"),
        )
        return actividad

    def test_la_regla_se_expande_en_clases_salvo_los_feriados(self):
        self.sembrar(self.migrar(self.ANTES))
        apps = self.migrar(self.DESPUES)

        SesionClase = apps.get_model("otec", "SesionClase")
        fechas = list(SesionClase.objects.values_list("fecha", flat=True))
        self.assertEqual(fechas, [
            date(2026, 8, 3), date(2026, 8, 10),
            date(2026, 8, 24), date(2026, 8, 31),
        ])
        self.assertTrue(
            all(s.duracion_horas == Decimal("2.0") for s in SesionClase.objects.all())
        )

    def test_cada_clase_queda_marcada_en_la_carta_gantt(self):
        self.sembrar(self.migrar(self.ANTES))
        apps = self.migrar(self.DESPUES)

        DiaActividad = apps.get_model("otec", "DiaActividad")
        self.assertEqual(DiaActividad.objects.count(), 4)
        self.assertTrue(all(d.tipo == "E" for d in DiaActividad.objects.all()))

    def test_la_vuelta_atras_reconstruye_una_regla(self):
        self.sembrar(self.migrar(self.ANTES))
        self.migrar(self.DESPUES)
        apps = self.migrar(self.ANTES)

        HorarioClase = apps.get_model("otec", "HorarioClase")
        horario = HorarioClase.objects.get()
        self.assertEqual(horario.dias, "0")  # todas cayeron en lunes
        self.assertEqual(horario.hora_inicio, time(18, 0))

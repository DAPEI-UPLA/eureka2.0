"""Valor ganado: la aritmética y lo que la pantalla dice a partir de ella.

El primer caso es un ejemplo trabajado a mano de punta a punta. Si algo cambia
en cómo se arma el BAC, el PV o el AC, ese test cae y obliga a rehacer el
número a mano antes de dar por bueno el cambio — que es exactamente lo que se
quiere de un indicador del que después cuelgan alertas.
"""

from datetime import date
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from . import evm
from .models import (
    CAPITAL,
    CORRIENTE,
    Egreso,
    GastoElegible,
    PlanDeGasto,
    PresupuestoAnual,
    PresupuestoResultadoAnual,
)
from .tests import BaseProyectoTest


class BaseEVMTest(BaseProyectoTest):

    def setUp(self):
        super().setUp()
        self.proyecto.presupuesto_total = Decimal("100000000")
        self.proyecto.presupuesto_corriente = Decimal("100000000")
        self.proyecto.presupuesto_capital = Decimal("0")
        self.proyecto.save()

        self.objetivo = self.crear_objetivo(
            presupuesto_corriente=Decimal("100000000"),
        )
        self.r_a = self.crear_resultado(
            self.objetivo, descripcion="Resultado A",
            presupuesto_corriente=Decimal("60000000"),
        )
        self.r_b = self.crear_resultado(
            self.objetivo, descripcion="Resultado B",
            presupuesto_corriente=Decimal("40000000"),
        )

    def avance(self, resultado, porcentaje):
        """Fija el avance del resultado creando actividades a medida.

        `Resultado.cumplimiento` es el promedio de sus actividades, así que se
        siembra una sola con el valor buscado.
        """
        from .models import Actividad
        resultado.actividades.all().delete()
        Actividad.objects.create(
            resultado=resultado, nombre="Actividad",
            cumplimiento=Decimal(porcentaje),
        )

    def gastar(self, neto, estado=Egreso.ESTADO_PAGADO):
        """Un egreso por `neto` sin IVA. El total queda 19% arriba."""
        from .models import Actividad
        actividad = self.r_a.actividades.first() or Actividad.objects.create(
            resultado=self.r_a, nombre="Actividad"
        )
        elegible = GastoElegible.objects.filter(
            gasto__tipo_gasto__transferencia__naturaleza=CORRIENTE
        ).first()
        plan, _ = PlanDeGasto.objects.get_or_create(
            resultado=self.r_a, gasto_elegible=elegible, anio=2026,
            defaults={"actividad": actividad, "monto": Decimal("60000000")},
        )
        return Egreso.objects.create(
            proyecto=self.proyecto, tipo=Egreso.TIPO_COMPRA,
            subtipo_compra=Egreso.SUB_BIENES_INSUMOS, estado=estado,
            plan_de_gasto=plan, gasto_elegible=elegible,
            cantidad=1, valor_sin_iva=Decimal(neto),
        )


class EjemploTrabajadoAManoTests(BaseEVMTest):
    """El caso completo, con los números calculados fuera del código.

    Proyecto de $100.000.000 repartidos en dos resultados:
        A: $60.000.000, lleva 50% hecho  ->  gana $30.000.000
        B: $40.000.000, lleva 25% hecho  ->  gana $10.000.000
                                     EV  =  $40.000.000

    El reparto anual pone $50.000.000 en 2026 y $50.000.000 en 2027. Mirado el
    31-dic-2026, el primer año cuenta entero y el segundo todavía no empieza:
                                     PV  =  $50.000.000

    Se gastaron $42.016.807 sin IVA, que con IVA son $50.000.000:
                                     AC  =  $50.000.000

        SPI = 40 / 50 = 0,800   ->  lleva el 80% del trabajo que debería
        CPI = 40 / 50 = 0,800   ->  cada peso rindió 80 centavos
        EAC = 100 / 0,8 = $125.000.000
        VAC = 100 - 125 = -$25.000.000  (faltarían 25 millones para terminar)
    """

    def setUp(self):
        super().setUp()
        self.avance(self.r_a, 50)
        self.avance(self.r_b, 25)
        # Los años se arman a mano para que queden explícitos en el test.
        a1 = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=1, anio_calendario=2026,
            presupuesto_corriente=Decimal("50000000"),
        )
        a2 = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=2, anio_calendario=2027,
            presupuesto_corriente=Decimal("50000000"),
        )
        for anio, (monto_a, monto_b) in ((a1, (30000000, 20000000)),
                                         (a2, (30000000, 20000000))):
            PresupuestoResultadoAnual.objects.create(
                resultado=self.r_a, anio=anio,
                presupuesto_corriente=Decimal(monto_a))
            PresupuestoResultadoAnual.objects.create(
                resultado=self.r_b, anio=anio,
                presupuesto_corriente=Decimal(monto_b))

        self.gastar("42016807")
        self.v = evm.calcular(self.proyecto, hoy=date(2026, 12, 31))

    def test_bac(self):
        self.assertEqual(self.v.bac, Decimal("100000000"))

    def test_valor_ganado(self):
        self.assertEqual(self.v.ev, Decimal("40000000"))

    def test_valor_planificado(self):
        self.assertEqual(self.v.pv, Decimal("50000000"))
        self.assertEqual(self.v.origen_pv, "reparto_anual")

    def test_costo_real(self):
        self.assertEqual(self.v.ac, Decimal("50000000"))

    def test_indices(self):
        self.assertEqual(self.v.spi, Decimal("0.800"))
        self.assertEqual(self.v.cpi, Decimal("0.800"))

    def test_desviaciones(self):
        self.assertEqual(self.v.sv, Decimal("-10000000"))
        self.assertEqual(self.v.cv, Decimal("-10000000"))

    def test_estimacion_al_termino(self):
        self.assertEqual(self.v.eac, Decimal("125000000"))
        self.assertEqual(self.v.vac, Decimal("-25000000"))

    def test_los_dos_indices_quedan_en_rojo(self):
        self.assertEqual(self.v.estado_spi, evm.CRITICO)
        self.assertEqual(self.v.estado_cpi, evm.CRITICO)
        self.assertEqual(self.v.estado, evm.CRITICO)


class ValorPlanificadoTests(BaseEVMTest):

    def test_el_anio_en_curso_cuenta_la_fraccion_transcurrida(self):
        """A mitad de año se espera la mitad del presupuesto de ese año."""
        anio = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=1, anio_calendario=2026,
            presupuesto_corriente=Decimal("100000000"),
        )
        PresupuestoResultadoAnual.objects.create(
            resultado=self.r_a, anio=anio,
            presupuesto_corriente=Decimal("100000000"))

        v = evm.calcular(self.proyecto, hoy=date(2026, 7, 2))
        # 183 de 365 días = 0,5014
        self.assertEqual(v.pv, Decimal("50136986"))

    def test_un_anio_futuro_no_aporta_nada(self):
        anio = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=1, anio_calendario=2028,
            presupuesto_corriente=Decimal("100000000"),
        )
        PresupuestoResultadoAnual.objects.create(
            resultado=self.r_a, anio=anio,
            presupuesto_corriente=Decimal("100000000"))
        self.assertEqual(evm.calcular(self.proyecto, hoy=date(2026, 6, 1)).pv, 0)

    def test_sin_reparto_anual_cae_al_plazo_del_proyecto(self):
        """Y lo dice, porque suponer gasto parejo mes a mes es discutible."""
        self.proyecto.fecha_inicio = date(2026, 1, 1)
        self.proyecto.fecha_fin = date(2027, 12, 31)
        self.proyecto.save()
        v = evm.calcular(self.proyecto, hoy=date(2026, 12, 31))
        self.assertEqual(v.origen_pv, "plazo_total")
        self.assertEqual(v.pv, Decimal("50000000"))

    def test_sin_reparto_ni_fechas_no_hay_pv(self):
        """No se inventa una base: sin ella el SPI simplemente no existe."""
        v = evm.calcular(self.proyecto, hoy=date(2026, 6, 1))
        self.assertIsNone(v.pv)
        self.assertIsNone(v.spi)
        self.assertIsNone(v.sv)
        self.assertEqual(v.origen_pv, "sin_base")
        self.assertEqual(v.estado_spi, evm.SIN_DATO)


class IndicesIndefinidosTests(BaseEVMTest):

    def test_sin_gasto_no_hay_cpi(self):
        """Un proyecto que no ha gastado nada no tiene CPI perfecto ni
        infinito: no tiene CPI. Devolver 1 lo pintaría de verde sin motivo."""
        self.avance(self.r_a, 50)
        v = evm.calcular(self.proyecto, hoy=date(2026, 6, 1))
        self.assertEqual(v.ac, 0)
        self.assertIsNone(v.cpi)
        self.assertIsNone(v.eac)
        self.assertEqual(v.estado_cpi, evm.SIN_DATO)

    def test_un_proyecto_sin_nada_no_es_medible(self):
        v = evm.calcular(self.proyecto, hoy=date(2026, 6, 1))
        self.assertFalse(v.medible)
        self.assertEqual(v.estado, evm.SIN_DATO)
        self.assertEqual(v.alertas, [])


class SemaforoTests(BaseEVMTest):

    def test_los_umbrales(self):
        self.assertEqual(evm._semaforo(Decimal("1.10")), evm.BIEN)
        self.assertEqual(evm._semaforo(Decimal("0.95")), evm.BIEN)
        self.assertEqual(evm._semaforo(Decimal("0.949")), evm.ATENCION)
        self.assertEqual(evm._semaforo(Decimal("0.85")), evm.ATENCION)
        self.assertEqual(evm._semaforo(Decimal("0.849")), evm.CRITICO)
        self.assertEqual(evm._semaforo(None), evm.SIN_DATO)

    def test_manda_el_peor_de_los_dos(self):
        self.avance(self.r_a, 100)
        self.avance(self.r_b, 100)
        self.proyecto.fecha_inicio = date(2026, 1, 1)
        self.proyecto.fecha_fin = date(2027, 12, 31)
        self.proyecto.save()
        # Al día en plazo (EV 100M vs PV 50M) pero carísimo.
        self.gastar("168067227")  # ~200M con IVA
        v = evm.calcular(self.proyecto, hoy=date(2026, 12, 31))
        self.assertEqual(v.estado_spi, evm.BIEN)
        self.assertEqual(v.estado_cpi, evm.CRITICO)
        self.assertEqual(v.estado, evm.CRITICO)

    def test_un_proyecto_sano_no_genera_alertas(self):
        self.avance(self.r_a, 100)
        self.avance(self.r_b, 100)
        self.proyecto.fecha_inicio = date(2026, 1, 1)
        self.proyecto.fecha_fin = date(2027, 12, 31)
        self.proyecto.save()
        self.gastar("42016807")  # 50M con IVA para 100M de trabajo
        v = evm.calcular(self.proyecto, hoy=date(2026, 12, 31))
        self.assertEqual(v.estado, evm.BIEN)
        self.assertEqual(v.alertas, [])


class AlertasTests(BaseEVMTest):

    def setUp(self):
        super().setUp()
        self.avance(self.r_a, 20)
        self.avance(self.r_b, 20)
        self.proyecto.fecha_inicio = date(2026, 1, 1)
        self.proyecto.fecha_fin = date(2027, 12, 31)
        self.proyecto.save()
        self.gastar("42016807")
        self.v = evm.calcular(self.proyecto, hoy=date(2026, 12, 31))

    def test_la_alerta_habla_en_pesos_y_no_solo_en_indice(self):
        """«SPI 0,40» no mueve a nadie; «faltan $30.000.000» sí."""
        atraso = next(a for a in self.v.alertas if a["indice"] == "SPI")
        self.assertEqual(atraso["nivel"], evm.CRITICO)
        self.assertIn("30.000.000", atraso["detalle"])

    def test_avisa_que_el_presupuesto_no_alcanzaria(self):
        self.assertTrue(any(a["indice"] == "EAC" for a in self.v.alertas))
        self.assertTrue(self.v.hay_alerta)

    def test_los_montos_van_con_separador_de_miles(self):
        for alerta in self.v.alertas:
            self.assertNotRegex(alerta["detalle"], r"\$\d{7,}")


class PresupuestoSinRepartirTests(BaseEVMTest):

    def test_lo_no_repartido_queda_fuera_de_la_base_pero_se_informa(self):
        """Meterlo en el BAC daría un déficit permanente que no habla ni de
        plazo ni de costo: es plata sin trabajo asociado, no trabajo atrasado."""
        self.objetivo.presupuesto_corriente = Decimal("70000000")
        self.objetivo.save()
        self.r_a.presupuesto_corriente = Decimal("40000000")
        self.r_a.save()
        self.r_b.presupuesto_corriente = Decimal("30000000")
        self.r_b.save()

        v = evm.calcular(self.proyecto, hoy=date(2026, 6, 1))
        self.assertEqual(v.bac, Decimal("70000000"))
        self.assertEqual(v.sin_repartir, Decimal("30000000"))


class PanelTests(BaseEVMTest):

    def setUp(self):
        super().setUp()
        self.avance(self.r_a, 20)
        self.avance(self.r_b, 20)
        self.proyecto.fecha_inicio = date(2026, 1, 1)
        self.proyecto.fecha_fin = date(2027, 12, 31)
        self.proyecto.save()
        self.gastar("42016807")

    def crear_proyecto_vacio(self):
        from .models import Proyecto
        return Proyecto.objects.create(
            nombre="Recién creado", responsable=self.user,
            presupuesto_total=Decimal("10000000"),
            presupuesto_corriente=Decimal("10000000"),
        )

    def url(self):
        return reverse("proyectos:valor_ganado", args=[self.proyecto.pk])

    def test_el_panel_responde(self):
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["v"].estado, evm.CRITICO)

    def test_muestra_los_cuatro_montos_y_los_dos_indices(self):
        html = self.client.get(self.url()).content.decode()
        for etiqueta in ("Valor planificado", "Valor ganado", "Costo real",
                         "SPI", "CPI"):
            self.assertIn(etiqueta, html)

    def test_los_indices_no_se_localizan_con_coma(self):
        """Un «0,800» se lee bien en castellano, pero el atributo de estilo de
        la barra no: ahí tiene que ir punto."""
        html = self.client.get(self.url()).content.decode()
        import re
        for estilo in re.findall(r'style="([^"]*)"', html):
            self.assertNotRegex(estilo, r"\d,\d")

    def test_dice_con_que_regla_calculo_el_pv(self):
        """Sin Año 1 declarado el respaldo son las fechas del proyecto."""
        self.assertContains(self.client.get(self.url()), "fechas de inicio y")

    def test_sin_datos_el_panel_dice_que_falta_y_no_muestra_indices(self):
        """Un panel con «—» y barras vacías se lee como «todo en cero», que es
        una afirmación. Lo que corresponde decir es que aún no se puede medir."""
        vacio = self.crear_proyecto_vacio()
        html = self.client.get(
            reverse("proyectos:valor_ganado", args=[vacio.pk])
        ).content.decode()
        self.assertIn("Todavía no hay con qué medir", html)
        self.assertNotIn("evm-indices", html)

    def test_hay_que_estar_autenticado(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url()).status_code, 302)

    def test_el_detalle_carga_el_panel(self):
        html = self.client.get(
            reverse("proyectos:detalle_proyecto", args=[self.proyecto.pk])
        ).content.decode()
        self.assertIn(self.url(), html)


class ListaTests(BaseEVMTest):

    def test_la_alerta_se_ve_sin_entrar_al_detalle(self):
        self.avance(self.r_a, 20)
        self.avance(self.r_b, 20)
        self.proyecto.fecha_inicio = date(2026, 1, 1)
        self.proyecto.fecha_fin = date(2027, 12, 31)
        self.proyecto.save()
        self.gastar("42016807")

        html = self.client.get(reverse("proyectos:lista_proyectos")).content.decode()
        self.assertIn("evm-chip", html)

    def test_un_proyecto_sin_datos_no_muestra_chip(self):
        html = self.client.get(reverse("proyectos:lista_proyectos")).content.decode()
        self.assertNotIn("evm-chip", html)


class ConsultasTests(BaseEVMTest):
    """El chip de la lista no puede volverse una consulta por resultado.

    `_resultados_vivos` y `_valor_planificado` usan `.all()` en vez de
    `.filter(...)` o `.select_related(...)` justamente para no descartar el
    prefetch de quien llama. Es una optimización silenciosa: si alguien la
    revierte «por claridad» nada falla, la página sólo se pone lenta.

    Se mide el aporte DEL CHIP, no el total de la página: la lista ya traía de
    antes unas dieciséis consultas por proyecto (`presupuesto_disponible_real`
    y compañía), y un test sobre el total fallaría por deuda ajena y taparía la
    propia.
    """

    def crear_otro_proyecto(self, nombre, resultados=3):
        from .models import ObjetivoEspecifico, Proyecto, Resultado
        proyecto = Proyecto.objects.create(
            nombre=nombre, responsable=self.user,
            presupuesto_total=Decimal("50000000"),
            presupuesto_corriente=Decimal("50000000"),
            fecha_inicio=date(2026, 1, 1), fecha_fin=date(2027, 12, 31),
        )
        objetivo = ObjetivoEspecifico.objects.create(
            proyecto=proyecto, descripcion="O",
            presupuesto_corriente=Decimal("50000000"),
        )
        for i in range(resultados):
            Resultado.objects.create(
                objetivo=objetivo, descripcion=f"R{i}",
                presupuesto_corriente=Decimal("10000000"),
            )
        return proyecto

    def _consultas_de_la_lista(self, con_chip):
        """Consultas de la página, con el cálculo real o con uno inerte."""
        from unittest.mock import patch
        url = reverse("proyectos:lista_proyectos")
        if con_chip:
            with CaptureQueriesContext(connection) as capturadas:
                self.client.get(url)
            return len(capturadas)
        inerte = evm.ValorGanado(hoy=date(2026, 6, 1))
        with patch("proyectos.views.proyectos.evm.calcular", return_value=inerte):
            with CaptureQueriesContext(connection) as capturadas:
                self.client.get(url)
        return len(capturadas)

    def test_el_chip_cuesta_una_consulta_por_proyecto_y_no_una_por_resultado(self):
        for i in range(5):
            self.crear_otro_proyecto(f"Proyecto {i}", resultados=3)

        proyectos = 6  # los cinco nuevos más el de la base
        costo = self._consultas_de_la_lista(True) - self._consultas_de_la_lista(False)

        # Una por proyecto son los egresos, que se consultan uno a uno. Si
        # alguna vez cuesta el triple, es que volvió a consultarse por
        # resultado: hay dieciocho resultados en esta página.
        self.assertLessEqual(
            costo, proyectos,
            f"el chip costó {costo} consultas para {proyectos} proyectos "
            f"con 3 resultados cada uno",
        )


class BorradoLogicoTests(BaseEVMTest):

    def test_un_objetivo_eliminado_no_aporta_al_valor_ganado(self):
        self.avance(self.r_a, 100)
        self.avance(self.r_b, 100)
        antes = evm.calcular(self.proyecto, hoy=date(2026, 6, 1)).ev
        self.assertEqual(antes, Decimal("100000000"))

        self.objetivo.eliminado = True
        self.objetivo.save()
        self.proyecto.refresh_from_db()
        self.assertEqual(evm.calcular(self.proyecto, hoy=date(2026, 6, 1)).ev, 0)

    def test_un_resultado_eliminado_no_aporta(self):
        self.avance(self.r_a, 100)
        self.avance(self.r_b, 100)
        self.r_b.eliminado = True
        self.r_b.save()
        self.proyecto.refresh_from_db()
        self.assertEqual(
            evm.calcular(self.proyecto, hoy=date(2026, 6, 1)).ev,
            Decimal("60000000"),
        )


class VentanaDelRespaldoTests(BaseEVMTest):
    """Sin reparto por resultado, ¿contra qué tramo se mide?

    El caso que lo motivó: un proyecto llega el 15 de octubre de 2025 pero
    declara que ejecuta desde 2026. Contando desde `fecha_inicio` acumulaba
    $7.100.000 de valor planificado antes de que empezara el Año 1, así que el
    SPI arrancaba castigado por dos meses y medio que nadie se comprometió a
    ejecutar.
    """

    def setUp(self):
        super().setUp()
        self.avance(self.r_a, 0)
        self.avance(self.r_b, 0)
        self.proyecto.fecha_inicio = date(2025, 10, 15)
        self.proyecto.fecha_fin = date(2028, 10, 14)
        self.proyecto.duracion_meses = 36
        self.proyecto.save()

    def test_antes_del_anio_1_declarado_no_hay_valor_planificado(self):
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        for cuando in (date(2025, 10, 15), date(2025, 11, 30), date(2025, 12, 31)):
            v = evm.calcular(self.proyecto, hoy=cuando)
            self.assertEqual(v.pv, 0, f"el {cuando} ya acumulaba PV")

    def test_el_tramo_va_de_enero_a_diciembre_de_los_anios_declarados(self):
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        # 2026-2028 son 1.096 días porque 2028 es bisiesto, así que a fin de
        # 2026 va 365/1096 y no exactamente un tercio. El tramo se mide en días
        # y no en años enteros justamente para no arrastrar ese error.
        v = evm.calcular(self.proyecto, hoy=date(2026, 12, 31))
        self.assertEqual(v.origen_pv, "anios_declarados")
        self.assertEqual(v.pv, Decimal("33302920"))
        # Al cierre del último año, el tramo completo.
        self.assertEqual(evm.calcular(self.proyecto, hoy=date(2028, 12, 31)).pv,
                         Decimal("100000000"))

    def test_sin_anio_declarado_sigue_usando_las_fechas(self):
        v = evm.calcular(self.proyecto, hoy=date(2025, 12, 31))
        self.assertEqual(v.origen_pv, "plazo_total")
        self.assertGreater(v.pv, 0)

    def test_el_anio_declarado_manda_sobre_las_fechas(self):
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        self.assertEqual(
            evm.calcular(self.proyecto, hoy=date(2025, 12, 31)).origen_pv,
            "anios_declarados")

    def test_funciona_con_anio_declarado_y_sin_fechas(self):
        """Un proyecto puede medir valor ganado sin cargar fechas: le basta
        con declarar su Año 1 y su duración."""
        self.proyecto.fecha_inicio = None
        self.proyecto.fecha_fin = None
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        v = evm.calcular(self.proyecto, hoy=date(2026, 12, 31))
        self.assertEqual(v.origen_pv, "anios_declarados")
        self.assertEqual(v.pv, Decimal("33302920"))

    def test_la_pantalla_dice_cual_de_las_tres_reglas_uso(self):
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        html = self.client.get(
            reverse("proyectos:valor_ganado", args=[self.proyecto.pk])
        ).content.decode()
        self.assertIn("años declarados del proyecto", html)
        self.assertNotIn("2.026", html)


class SinAvanceCargadoTests(BaseEVMTest):
    """Un proyecto sin avance cargado no está atrasado: le faltan datos.

    Con EV = 0 el SPI da 0,00 por construcción. Pintar eso de rojo acusa al
    equipo de algo que no hizo, y la primera alerta falsa hace dudar de todas
    las siguientes.
    """

    def setUp(self):
        super().setUp()
        self.proyecto.anio_inicial = 2026
        self.proyecto.duracion_meses = 24
        self.proyecto.save()

    def test_el_semaforo_no_se_pinta(self):
        self.avance(self.r_a, 0)
        self.avance(self.r_b, 0)
        v = evm.calcular(self.proyecto, hoy=date(2026, 12, 31))
        self.assertEqual(v.spi, Decimal("0.000"))
        self.assertEqual(v.estado_spi, evm.SIN_DATO)
        self.assertEqual(v.estado, evm.SIN_DATO)

    def test_el_aviso_habla_de_datos_y_no_de_atraso(self):
        self.avance(self.r_a, 0)
        self.avance(self.r_b, 0)
        v = evm.calcular(self.proyecto, hoy=date(2026, 12, 31))
        aviso = v.alertas[0]
        self.assertEqual(aviso["nivel"], evm.DATOS)
        self.assertIn("Nadie ha cargado avance", aviso["titulo"])
        self.assertIn("no por atraso", aviso["detalle"])
        self.assertFalse(any(a["indice"] == "SPI" for a in v.alertas))

    def test_dice_cuantas_actividades_estan_en_cero(self):
        self.avance(self.r_a, 0)
        self.avance(self.r_b, 0)
        v = evm.calcular(self.proyecto, hoy=date(2026, 12, 31))
        self.assertEqual(v.actividades, 2)
        self.assertIn("las 2 actividades", v.alertas[0]["detalle"])

    def test_sin_actividades_invita_a_definir_como_se_mide(self):
        """Sin actividades el camino no es cargarlas: es declararle a cada
        resultado si se mide por meta contable o por tramo."""
        v = evm.calcular(self.proyecto, hoy=date(2026, 12, 31))
        self.assertEqual(v.actividades, 0)
        self.assertIn("cómo se mide", v.alertas[0]["detalle"])

    def test_con_una_sola_actividad_avanzada_vuelve_el_semaforo(self):
        """Basta que alguien cargue algo para que el indicador vuelva a hablar
        del proyecto y no de sus datos."""
        self.avance(self.r_a, 5)
        self.avance(self.r_b, 0)
        v = evm.calcular(self.proyecto, hoy=date(2026, 12, 31))
        self.assertTrue(v.avance_cargado)
        self.assertEqual(v.estado_spi, evm.CRITICO)
        self.assertTrue(any(a["indice"] == "SPI" for a in v.alertas))

    def test_no_aparece_el_chip_rojo_en_la_lista(self):
        """Era el efecto peor: la lista entera en rojo desde el primer mes."""
        self.avance(self.r_a, 0)
        self.avance(self.r_b, 0)
        html = self.client.get(reverse("proyectos:lista_proyectos")).content.decode()
        self.assertNotIn("evm-chip", html)

    def test_el_panel_no_muestra_un_cero_que_parece_veredicto(self):
        self.avance(self.r_a, 0)
        self.avance(self.r_b, 0)
        html = self.client.get(
            reverse("proyectos:valor_ganado", args=[self.proyecto.pk])
        ).content.decode()
        # El HTML trae la frase partida en varias líneas por la indentación
        # de la plantilla, así que se compara sobre el texto normalizado.
        plano = " ".join(html.split())
        self.assertIn("las 2 actividades están en 0%", plano)
        self.assertIn("evm-datos", html)
        self.assertNotIn("evm-indice evm-critico", html)

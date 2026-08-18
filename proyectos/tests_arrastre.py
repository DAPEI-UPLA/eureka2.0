"""Pruebas del arrastre de actividades entre años.

Una actividad se hace una sola vez, pero si no alcanza a hacerse en su año pasa
al siguiente y alguien corre la fecha límite. Sin guardar la fecha original esa
corrida borra el compromiso: la actividad vuelve a estar «a tiempo» justo por
haberse atrasado. Aquí se cubre que la línea base no se mueva, que cada corrida
quede anotada, y que el año sepa qué le llegó heredado.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse

from .models import Actividad, PresupuestoAnual, ReprogramacionActividad
from .tests import BaseProyectoTest


class CompromisoOriginalTests(BaseProyectoTest):

    def setUp(self):
        super().setUp()
        objetivo = self.crear_objetivo(
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
        self.resultado = self.crear_resultado(
            objetivo,
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
        self.actividad = Actividad.objects.create(
            resultado=self.resultado,
            nombre="Diplomado de formación docente",
            fecha_limite=date(2026, 6, 30),
            presupuesto_corriente=Decimal("100000"),
        )

    def test_la_primera_fecha_queda_como_compromiso(self):
        self.assertEqual(self.actividad.fecha_limite_original, date(2026, 6, 30))

    def test_correr_la_fecha_no_mueve_el_compromiso(self):
        """El punto entero: la línea base no se toca al reprogramar."""
        self.actividad.fecha_limite = date(2027, 6, 30)
        self.actividad.save()
        self.actividad.refresh_from_db()

        self.assertEqual(self.actividad.fecha_limite, date(2027, 6, 30))
        self.assertEqual(self.actividad.fecha_limite_original, date(2026, 6, 30))

    def test_cada_corrida_queda_anotada(self):
        self.actividad.fecha_limite = date(2026, 12, 31)
        self.actividad.save()
        self.actividad.fecha_limite = date(2027, 6, 30)
        self.actividad.save()

        movidas = list(self.actividad.reprogramaciones.order_by("creado_en"))
        self.assertEqual(len(movidas), 2)
        self.assertEqual(movidas[0].fecha_anterior, date(2026, 6, 30))
        self.assertEqual(movidas[0].fecha_nueva, date(2026, 12, 31))
        self.assertFalse(movidas[0].cambia_de_anio)
        self.assertTrue(movidas[1].cambia_de_anio)

    def test_guardar_sin_mover_la_fecha_no_anota_nada(self):
        self.actividad.nombre = "Otro nombre"
        self.actividad.save()
        self.assertEqual(self.actividad.reprogramaciones.count(), 0)

    def test_la_actividad_sabe_que_viene_arrastrada(self):
        self.actividad.fecha_limite = date(2027, 6, 30)
        self.actividad.save()

        self.assertTrue(self.actividad.arrastrada)
        self.assertEqual(self.actividad.anio_comprometido, 2026)
        self.assertEqual(self.actividad.anio_planificado, 2027)
        self.assertEqual(self.actividad.anios_de_arrastre, 1)
        self.assertEqual(self.actividad.dias_reprogramados, 365)

    def test_arrastrarse_dos_anios_se_cuenta_como_dos(self):
        for destino in (date(2027, 6, 30), date(2028, 6, 30)):
            self.actividad.fecha_limite = destino
            self.actividad.save()

        self.assertEqual(self.actividad.anios_de_arrastre, 2)
        self.assertEqual(self.actividad.veces_reprogramada, 2)

    def test_moverla_dentro_del_mismo_anio_no_es_arrastre(self):
        self.actividad.fecha_limite = date(2026, 12, 31)
        self.actividad.save()
        self.assertFalse(self.actividad.arrastrada)
        self.assertEqual(self.actividad.anios_de_arrastre, 0)

    def test_la_desviacion_real_se_mide_contra_el_compromiso(self):
        """El defecto que esto corrige: una actividad reprogramada y cerrada el
        último día salía «a tiempo» porque se comparaba con la fecha ya corrida.
        """
        self.actividad.fecha_limite = date(2027, 6, 30)
        self.actividad.fecha_efectiva = date(2027, 6, 30)
        self.actividad.save()

        # Contra la fecha vigente parece impecable...
        self.assertEqual(self.actividad.desviacion_dias, 0)
        self.assertTrue(self.actividad.cerrada_a_tiempo)
        # ...pero llegó un año tarde respecto de lo comprometido.
        self.assertEqual(self.actividad.desviacion_vs_compromiso, 365)

    def test_una_actividad_sin_fecha_no_tiene_compromiso(self):
        suelta = Actividad.objects.create(
            resultado=self.resultado, nombre="Sin fecha",
        )
        self.assertIsNone(suelta.fecha_limite_original)
        self.assertFalse(suelta.arrastrada)
        self.assertEqual(suelta.anios_de_arrastre, 0)

    def test_ponerle_fecha_despues_la_fija_como_compromiso(self):
        suelta = Actividad.objects.create(
            resultado=self.resultado, nombre="Sin fecha",
        )
        suelta.fecha_limite = date(2027, 3, 31)
        suelta.save()
        suelta.refresh_from_db()

        self.assertEqual(suelta.fecha_limite_original, date(2027, 3, 31))
        # Estrenar fecha no es reprogramar.
        self.assertEqual(suelta.reprogramaciones.count(), 0)

    def test_el_motivo_llega_al_historial(self):
        self.actividad.actualizado_por = self.user
        self.actividad._motivo_reprogramacion = "No llegó el equipamiento"
        self.actividad.fecha_limite = date(2027, 6, 30)
        self.actividad.save()

        movida = self.actividad.reprogramaciones.first()
        self.assertEqual(movida.motivo, "No llegó el equipamiento")
        self.assertEqual(movida.creado_por, self.user)


class ArrastrePorAnioTests(BaseProyectoTest):
    """Lo que el año sabe de sus actividades: cuáles son suyas y cuáles heredó."""

    def setUp(self):
        super().setUp()
        objetivo = self.crear_objetivo(
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
        self.resultado = self.crear_resultado(
            objetivo,
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
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

        self.se_hizo = self._actividad("Diagnóstico", date(2026, 3, 31))
        self.se_corrio = self._actividad("Equipamiento", date(2026, 9, 30))
        self.nativa_2027 = self._actividad("Pasantías", date(2027, 5, 31))

        # La que no alcanzó a hacerse pasa al año siguiente.
        self.se_corrio.fecha_limite = date(2027, 3, 31)
        self.se_corrio.save()

    def _actividad(self, nombre, fecha):
        return Actividad.objects.create(
            resultado=self.resultado, nombre=nombre, fecha_limite=fecha,
            presupuesto_corriente=Decimal("50000"),
        )

    def test_el_anio_uno_conserva_solo_lo_que_sigue_en_el(self):
        self.assertEqual(
            [a.nombre for a in self.anio_1.actividades()], ["Diagnóstico"]
        )

    def test_el_anio_dos_recibe_la_arrastrada(self):
        nombres = sorted(a.nombre for a in self.anio_2.actividades())
        self.assertEqual(nombres, ["Equipamiento", "Pasantías"])

        arrastradas = [a.nombre for a in self.anio_2.actividades_arrastradas()]
        self.assertEqual(arrastradas, ["Equipamiento"])

        propias = [a.nombre for a in self.anio_2.actividades_propias()]
        self.assertEqual(propias, ["Pasantías"])

    def test_el_anio_uno_sabe_lo_que_prometio_y_no_cumplio(self):
        """La contracara: mirando 2026 hay que poder ver lo que se fue."""
        perdidas = [a.nombre for a in self.anio_1.actividades_perdidas()]
        self.assertEqual(perdidas, ["Equipamiento"])
        self.assertEqual(self.anio_2.actividades_perdidas().count(), 0)

    def test_el_dashboard_del_anio_muestra_el_arrastre(self):
        url = reverse("proyectos:dashboard_proyecto", args=[self.proyecto.pk])

        en_2027 = self.client.get(url, {"anio": 2027})
        self.assertEqual(len(en_2027.context["arrastre"]["arrastradas"]), 1)
        self.assertContains(en_2027, "Llegaron arrastradas")
        self.assertContains(en_2027, "Equipamiento")

        en_2026 = self.client.get(url, {"anio": 2026})
        self.assertEqual(len(en_2026.context["arrastre"]["perdidas"]), 1)
        self.assertContains(en_2026, "se fueron a otro año")

    def test_sin_anio_elegido_no_se_habla_de_arrastre(self):
        """En la vista del proyecto completo todas las actividades están."""
        url = reverse("proyectos:dashboard_proyecto", args=[self.proyecto.pk])
        respuesta = self.client.get(url)
        self.assertIsNone(respuesta.context["arrastre"])
        self.assertNotContains(respuesta, "Llegaron arrastradas")

    def test_la_edicion_por_pantalla_anota_el_motivo(self):
        respuesta = self.client.post(
            reverse("proyectos:editar_actividad", args=[self.nativa_2027.pk]),
            {
                "nombre": self.nativa_2027.nombre,
                "presupuesto_corriente": "50000",
                "presupuesto_capital": "0",
                "fecha_limite": "2028-05-31",
                "fecha_efectiva": "",
                "motivo_reprogramacion": "Se cayó el convenio",
            },
        )
        self.assertEqual(respuesta.status_code, 200)

        self.nativa_2027.refresh_from_db()
        self.assertEqual(self.nativa_2027.fecha_limite_original, date(2027, 5, 31))
        movida = self.nativa_2027.reprogramaciones.first()
        self.assertEqual(movida.motivo, "Se cayó el convenio")
        self.assertEqual(movida.creado_por, self.user)

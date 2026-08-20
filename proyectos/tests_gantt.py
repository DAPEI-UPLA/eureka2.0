"""Carta Gantt: ventana, filtros y qué se dibuja.

Todo el cálculo vive en `views/gantt.py` y llega al template como porcentajes,
así que se puede probar sin navegador. Lo que se cubre acá es lo que se rompe
en silencio: una ventana mal calculada deja las barras corridas y sigue
pareciendo una carta correcta.
"""

import re
from datetime import date

from django.urls import reverse

from .models import Actividad
from .tests import BaseProyectoTest


class BaseGanttTest(BaseProyectoTest):

    def setUp(self):
        super().setUp()
        self.objetivo = self.crear_objetivo()
        self.resultado = self.crear_resultado(self.objetivo)

    def crear_actividad(self, nombre="Actividad", **kwargs):
        return Actividad.objects.create(
            resultado=self.resultado, nombre=nombre, **kwargs
        )

    def gantt(self, **params):
        url = reverse("proyectos:gantt_proyecto", args=[self.proyecto.pk])
        return self.client.get(url, params)

    def filas(self, respuesta):
        return respuesta.context["filas"]

    def por_nombre(self, respuesta, nombre):
        for fila in self.filas(respuesta):
            if fila["actividad"].nombre == nombre:
                return fila
        return None


class VentanaTests(BaseGanttTest):

    def test_sin_actividades_la_carta_avisa_en_vez_de_reventar(self):
        r = self.gantt()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["vacia"])
        self.assertContains(r, "No hay nada que dibujar")

    def test_la_ventana_abarca_meses_completos(self):
        self.crear_actividad(
            fecha_inicio=date(2026, 3, 15), fecha_limite=date(2026, 7, 10)
        )
        r = self.gantt()
        self.assertEqual(r.context["ventana_ini"], date(2026, 3, 1))
        self.assertEqual(r.context["ventana_fin"], date(2026, 7, 31))

    def test_los_anchos_de_los_meses_suman_cien(self):
        self.crear_actividad(
            fecha_inicio=date(2026, 1, 5), fecha_limite=date(2027, 2, 20)
        )
        r = self.gantt()
        total = sum(m["ancho"] for m in r.context["meses"])
        self.assertAlmostEqual(total, 100.0, places=2)

    def test_febrero_es_mas_angosto_que_marzo(self):
        """Los anchos son proporcionales a los días, no 1/n.

        Con columnas iguales las barras dejan de coincidir con la grilla y el
        desfase crece hacia la derecha.
        """
        self.crear_actividad(
            fecha_inicio=date(2026, 2, 1), fecha_limite=date(2026, 3, 31)
        )
        meses = {m["mes"]: m["ancho"] for m in self.gantt().context["meses"]}
        self.assertLess(meses[2], meses[3])

    def test_la_cabecera_de_anios_agrupa_los_meses(self):
        self.crear_actividad(
            fecha_inicio=date(2026, 11, 1), fecha_limite=date(2027, 2, 28)
        )
        cabecera = self.gantt().context["anios_cabecera"]
        self.assertEqual([a["anio"] for a in cabecera], [2026, 2027])
        self.assertAlmostEqual(sum(a["ancho"] for a in cabecera), 100.0, places=2)


class BarraEHitoTests(BaseGanttTest):

    def test_con_fecha_de_inicio_se_dibuja_una_barra(self):
        self.crear_actividad(
            fecha_inicio=date(2026, 3, 1), fecha_limite=date(2026, 3, 31)
        )
        fila = self.filas(self.gantt())[0]
        self.assertIsNotNone(fila["barra"])
        self.assertIsNone(fila["hito"])

    def test_sin_fecha_de_inicio_se_dibuja_un_hito(self):
        """No se inventa un comienzo.

        Ésta es la decisión de fondo: una duración supuesta se lee igual que
        una declarada y nadie la vuelve a corregir.
        """
        self.crear_actividad(fecha_limite=date(2026, 6, 30))
        fila = self.filas(self.gantt())[0]
        self.assertIsNone(fila["barra"])
        self.assertIsNotNone(fila["hito"])

    def test_la_barra_de_un_solo_dia_tiene_ancho_visible(self):
        self.crear_actividad(
            fecha_inicio=date(2026, 3, 10), fecha_limite=date(2026, 3, 10)
        )
        fila = self.filas(self.gantt())[0]
        self.assertGreater(fila["barra"]["ancho"], 0)

    def test_la_barra_termina_en_la_fecha_efectiva_cuando_cerro(self):
        self.crear_actividad(
            fecha_inicio=date(2026, 3, 1),
            fecha_limite=date(2026, 3, 31),
            fecha_efectiva=date(2026, 5, 15),
        )
        r = self.gantt()
        self.assertEqual(r.context["ventana_fin"], date(2026, 5, 31))
        # La barra llega hasta mayo, no se corta en la fecha límite.
        self.assertGreater(self.filas(r)[0]["barra"]["ancho"], 50)

    def test_el_avance_viaja_como_numero(self):
        self.crear_actividad(
            fecha_inicio=date(2026, 3, 1), fecha_limite=date(2026, 3, 31),
            cumplimiento=40,
        )
        self.assertEqual(self.filas(self.gantt())[0]["avance"], 40.0)

    def test_una_actividad_vencida_sin_completar_sale_atrasada(self):
        self.crear_actividad(fecha_limite=date(2020, 1, 31), cumplimiento=20)
        self.assertEqual(self.filas(self.gantt())[0]["estado"], "atrasada")

    def test_una_actividad_cerrada_no_sale_atrasada(self):
        self.crear_actividad(
            fecha_limite=date(2020, 1, 31), fecha_efectiva=date(2020, 3, 1),
        )
        self.assertEqual(self.filas(self.gantt())[0]["estado"], "cerrada")


class ArrastreTests(BaseGanttTest):

    def _actividad_arrastrada(self):
        actividad = self.crear_actividad(fecha_limite=date(2026, 5, 31))
        actividad.fecha_limite = date(2027, 3, 31)
        actividad.save()
        return actividad

    def test_correr_la_fecha_deja_el_tramo_dibujado(self):
        self._actividad_arrastrada()
        fila = self.filas(self.gantt())[0]
        self.assertIsNotNone(fila["arrastre"])
        self.assertEqual(fila["arrastre_dias"], 304)

    def test_sin_reprogramacion_no_hay_tramo(self):
        self.crear_actividad(fecha_limite=date(2026, 5, 31))
        self.assertIsNone(self.filas(self.gantt())[0]["arrastre"])

    def test_la_ventana_incluye_el_compromiso_original(self):
        """Si sólo se mirara la fecha vigente, el atraso quedaría fuera de la
        carta justo en la actividad donde importa verlo."""
        self._actividad_arrastrada()
        r = self.gantt()
        self.assertEqual(r.context["ventana_ini"], date(2026, 5, 1))
        self.assertEqual(r.context["ventana_fin"], date(2027, 3, 31))


class FiltroAnioTests(BaseGanttTest):

    def setUp(self):
        super().setUp()
        self.crear_actividad(
            "De 2026", fecha_inicio=date(2026, 2, 1), fecha_limite=date(2026, 4, 30)
        )
        self.crear_actividad(
            "De 2027", fecha_inicio=date(2027, 6, 1), fecha_limite=date(2027, 8, 31)
        )

    def test_los_anios_disponibles_salen_de_las_fechas(self):
        self.assertEqual(self.gantt().context["anios"], [2026, 2027])

    def test_el_filtro_recorta_la_ventana_al_anio(self):
        r = self.gantt(anio=2026)
        self.assertEqual(r.context["ventana_ini"], date(2026, 1, 1))
        self.assertEqual(r.context["ventana_fin"], date(2026, 12, 31))

    def test_lo_que_queda_fuera_se_informa_y_no_se_esconde(self):
        r = self.gantt(anio=2026)
        self.assertEqual([f["actividad"].nombre for f in self.filas(r)], ["De 2026"])
        self.assertEqual(r.context["fuera_de_ventana"], 1)
        self.assertContains(r, "queda fuera del rango elegido")

    def test_un_anio_que_no_existe_se_ignora(self):
        """Mejor mostrar el proyecto completo que una carta en blanco."""
        r = self.gantt(anio=1999)
        self.assertIsNone(r.context["anio_sel"])
        self.assertEqual(len(self.filas(r)), 2)

    def test_un_anio_con_basura_no_revienta(self):
        r = self.gantt(anio="ayer")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["anio_sel"])


class FiltroMesesTests(BaseGanttTest):

    def setUp(self):
        super().setUp()
        self.crear_actividad(
            "Marzo", fecha_inicio=date(2026, 3, 1), fecha_limite=date(2026, 3, 31)
        )
        self.crear_actividad(
            "Octubre", fecha_inicio=date(2026, 10, 1), fecha_limite=date(2026, 10, 31)
        )

    def test_el_rango_de_meses_recorta_la_ventana(self):
        r = self.gantt(anio=2026, mes_desde=3, mes_hasta=6)
        self.assertEqual(r.context["ventana_ini"], date(2026, 3, 1))
        self.assertEqual(r.context["ventana_fin"], date(2026, 6, 30))
        self.assertEqual([f["actividad"].nombre for f in self.filas(r)], ["Marzo"])

    def test_meses_al_reves_se_ordenan_solos(self):
        r = self.gantt(anio=2026, mes_desde=6, mes_hasta=3)
        self.assertEqual(r.context["ventana_ini"], date(2026, 3, 1))
        self.assertEqual(r.context["ventana_fin"], date(2026, 6, 30))

    def test_sin_anio_los_meses_se_ignoran(self):
        """«Marzo a junio» de un proyecto de tres años no dice de cuál marzo."""
        r = self.gantt(mes_desde=3, mes_hasta=6)
        self.assertIsNone(r.context["mes_desde"])
        self.assertEqual(len(self.filas(r)), 2)

    def test_un_mes_fuera_de_rango_cae_al_ano_completo(self):
        r = self.gantt(anio=2026, mes_desde=0, mes_hasta=99)
        self.assertEqual(r.context["ventana_ini"], date(2026, 1, 1))
        self.assertEqual(r.context["ventana_fin"], date(2026, 12, 31))


class RecorteTests(BaseGanttTest):

    def test_una_barra_que_cruza_el_borde_se_marca_recortada(self):
        self.crear_actividad(
            fecha_inicio=date(2025, 11, 1), fecha_limite=date(2027, 2, 28)
        )
        fila = self.filas(self.gantt(anio=2026))[0]
        self.assertTrue(fila["barra"]["recorte_izq"])
        self.assertTrue(fila["barra"]["recorte_der"])
        self.assertEqual(fila["barra"]["izquierda"], 0.0)
        self.assertAlmostEqual(fila["barra"]["ancho"], 100.0, places=2)

    def test_ningun_porcentaje_se_sale_de_la_pista(self):
        self.crear_actividad(
            "Larga", fecha_inicio=date(2020, 1, 1), fecha_limite=date(2030, 1, 1)
        )
        self.crear_actividad("Hito", fecha_limite=date(2026, 6, 15))
        for fila in self.filas(self.gantt(anio=2026)):
            if fila["barra"]:
                self.assertGreaterEqual(fila["barra"]["izquierda"], 0)
                self.assertLessEqual(
                    fila["barra"]["izquierda"] + fila["barra"]["ancho"], 100.001
                )
            if fila["hito"] is not None:
                self.assertTrue(0 <= fila["hito"] <= 100)


class SinFechaTests(BaseGanttTest):

    def test_una_actividad_sin_fechas_se_lista_aparte(self):
        """No se esconde: la carta se vería completa estando incompleta."""
        self.crear_actividad("Sin fechas")
        r = self.gantt()
        self.assertEqual(len(r.context["sin_fecha"]), 1)
        self.assertContains(r, "sin ninguna fecha cargada")
        self.assertContains(r, "Sin fechas")

    def test_no_cuenta_como_fila_dibujada(self):
        self.crear_actividad("Sin fechas")
        self.crear_actividad("Con fecha", fecha_limite=date(2026, 4, 1))
        r = self.gantt()
        self.assertEqual(len(self.filas(r)), 1)
        self.assertEqual(r.context["total_actividades"], 2)


class EtiquetasYOrdenTests(BaseGanttTest):

    def test_la_etiqueta_ubica_la_actividad_en_el_arbol(self):
        self.crear_actividad("Primera", fecha_limite=date(2026, 4, 1))
        self.assertEqual(self.filas(self.gantt())[0]["etiqueta"], "OE1.R1.A1")

    def test_las_filas_van_en_orden_cronologico(self):
        self.crear_actividad("Tercera", fecha_limite=date(2026, 9, 1), orden=1)
        self.crear_actividad("Primera", fecha_limite=date(2026, 2, 1), orden=2)
        self.crear_actividad(
            "Segunda", fecha_inicio=date(2026, 5, 1), fecha_limite=date(2026, 12, 1),
            orden=3,
        )
        nombres = [f["actividad"].nombre for f in self.filas(self.gantt())]
        self.assertEqual(nombres, ["Primera", "Segunda", "Tercera"])


class RenderTests(BaseGanttTest):

    def test_los_porcentajes_salen_con_punto_decimal(self):
        """Con coma decimal el navegador descarta la regla y todas las barras
        se apilan en el borde izquierdo. Ya pasó una vez con «?anio=2 026»."""
        self.crear_actividad(
            fecha_inicio=date(2026, 2, 10), fecha_limite=date(2026, 8, 20),
            cumplimiento=35,
        )
        html = self.gantt().content.decode()
        estilos = re.findall(r'style="([^"]*)"', html)
        self.assertTrue(estilos)
        for estilo in estilos:
            self.assertNotRegex(
                estilo, r"\d,\d",
                msg=f"porcentaje localizado con coma: {estilo!r}",
            )

    def test_los_anios_del_filtro_no_llevan_separador_de_miles(self):
        self.crear_actividad(fecha_limite=date(2026, 4, 1))
        html = self.gantt().content.decode()
        self.assertNotIn("2.026", html)
        self.assertIn("?anio=2026", html)

    def test_el_detalle_enlaza_la_carta(self):
        url = reverse("proyectos:detalle_proyecto", args=[self.proyecto.pk])
        self.assertContains(
            self.client.get(url),
            reverse("proyectos:gantt_proyecto", args=[self.proyecto.pk]),
        )

    def test_el_boton_de_volver_no_carga_el_nombre_del_proyecto(self):
        """Los nombres reales pasan de cien caracteres y estiraban el enlace
        media pantalla. El nombre va de antetítulo, donde puede recortarse."""
        self.proyecto.nombre = (
            "Fortalecimiento de la vinculación con el medio y la transferencia "
            "tecnológica en la Facultad de Ingeniería, período 2026-2028"
        )
        self.proyecto.save()
        html = self.gantt().content.decode()

        enlace = re.search(
            r'<a[^>]*href="%s"[^>]*>(.*?)</a>'
            % reverse("proyectos:detalle_proyecto", args=[self.proyecto.pk]),
            html, re.S,
        )
        self.assertIsNotNone(enlace)
        self.assertIn("Volver", enlace.group(1))
        self.assertNotIn(self.proyecto.nombre, enlace.group(1))
        # Pero el nombre sí está en la página: no se pierde de dónde se viene.
        self.assertContains(self.gantt(), self.proyecto.nombre)

    def test_hay_que_estar_autenticado(self):
        self.client.logout()
        r = self.gantt()
        self.assertEqual(r.status_code, 302)

    def test_quien_no_es_responsable_igual_puede_mirarla(self):
        """La carta es de lectura: sigue la visibilidad de la lista, donde el
        equipo ve los proyectos de sus compañeros sin poder editarlos."""
        from django.contrib.auth.models import User
        self.client.force_login(User.objects.create_user("mirona", password="x"))
        self.crear_actividad(fecha_limite=date(2026, 4, 1))
        self.assertEqual(self.gantt().status_code, 200)


class FechaInicioTests(BaseGanttTest):

    def test_no_se_puede_empezar_despues_de_la_fecha_limite(self):
        from django.core.exceptions import ValidationError
        actividad = Actividad(
            resultado=self.resultado, nombre="Al revés",
            fecha_inicio=date(2026, 8, 1), fecha_limite=date(2026, 3, 1),
        )
        with self.assertRaises(ValidationError):
            actividad.full_clean()

    def test_el_formulario_guarda_la_fecha_de_inicio(self):
        r = self.client.post(
            reverse("proyectos:crear_actividad", args=[self.resultado.pk]),
            {"nombre": "Con inicio", "fecha_inicio": "2026-03-01",
             "fecha_limite": "2026-06-30"},
        )
        self.assertEqual(r.status_code, 200)
        actividad = Actividad.objects.get(nombre="Con inicio")
        self.assertEqual(actividad.fecha_inicio, date(2026, 3, 1))

    def test_el_formulario_de_edicion_la_muestra_precargada(self):
        actividad = self.crear_actividad(
            fecha_inicio=date(2026, 3, 1), fecha_limite=date(2026, 6, 30)
        )
        r = self.client.get(
            reverse("proyectos:editar_actividad_form", args=[actividad.pk])
        )
        self.assertContains(r, 'name="fecha_inicio"')
        self.assertContains(r, 'value="2026-03-01"')

    def test_se_puede_dejar_vacia(self):
        r = self.client.post(
            reverse("proyectos:crear_actividad", args=[self.resultado.pk]),
            {"nombre": "Sin inicio", "fecha_limite": "2026-06-30"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(Actividad.objects.get(nombre="Sin inicio").fecha_inicio)


class EstructuraTests(BaseGanttTest):
    """La geometría que el CSS da por supuesta, leída del HTML.

    Un Gantt se desalinea en silencio: si la rejilla de una fila deja de tener
    las mismas columnas que la cabecera, las barras siguen dibujándose y el
    desfase sólo se nota comparando con un calendario. Ninguna prueba de texto
    lo ve, igual que pasó con el `<form>` dentro del `<tr>`.
    """

    def setUp(self):
        super().setUp()
        self.crear_actividad(
            "Con barra", fecha_inicio=date(2026, 2, 1), fecha_limite=date(2026, 9, 30)
        )
        self.crear_actividad("Con hito", fecha_limite=date(2026, 5, 15))

    def _anchos(self, html, clase):
        bloque = re.findall(
            r'class="[^"]*\b%s\b[^"]*"[^>]*style="width: ([\d.]+)%%"' % clase, html
        )
        return [float(x) for x in bloque]

    def test_cada_fila_tiene_una_sola_pista(self):
        html = self.gantt().content.decode()
        self.assertEqual(
            html.count('class="gantt-fila"'), html.count('class="gantt-pista"')
        )

    def test_la_rejilla_de_cada_fila_calza_con_la_cabecera(self):
        r = self.gantt()
        html = r.content.decode()
        meses = len(r.context["meses"])
        columnas = re.findall(
            r'<div class="gantt-rejilla"[^>]*>(.*?)</div>', html, re.S
        )
        self.assertEqual(len(columnas), len(self.filas(r)))
        for rejilla in columnas:
            self.assertEqual(rejilla.count("<span"), meses)

    def test_los_anchos_de_la_cabecera_suman_cien_en_el_html(self):
        html = self.gantt().content.decode()
        self.assertAlmostEqual(sum(self._anchos(html, "gantt-cab-mes")), 100.0, places=1)
        self.assertAlmostEqual(sum(self._anchos(html, "gantt-cab-anio")), 100.0, places=1)

    def test_las_etiquetas_no_se_desalinean_de_las_pistas(self):
        """Etiqueta y pista van en el mismo flex: una fila con una sola de las
        dos correría todo lo de abajo medio renglón."""
        html = self.gantt().content.decode()
        self.assertEqual(
            html.count('class="gantt-etiqueta"'), html.count('class="gantt-pista"')
        )

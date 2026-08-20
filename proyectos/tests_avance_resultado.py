"""Cómo se mide el avance de un resultado.

El problema que resuelve: si cada equipo pone «como un 60%», los números no se
pueden comparar ni auditar. Ahora cada resultado declara con qué regla se mide
—meta contable, escala de tramos, o el promedio de sus actividades— y la
pantalla dice cuál se usó.

Importa más que de costumbre porque de acá sale el valor ganado del proyecto
entero: EV = Σ(presupuesto del resultado × su avance).
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse

from .models import Actividad, Resultado
from .tests import BaseProyectoTest


class BaseAvanceTest(BaseProyectoTest):

    def setUp(self):
        super().setUp()
        self.objetivo = self.crear_objetivo(
            presupuesto_corriente=Decimal("1000000"))
        self.resultado = self.crear_resultado(
            self.objetivo, descripcion="Convenios firmados",
            presupuesto_corriente=Decimal("1000000"))

    def actividad(self, cumplimiento):
        return Actividad.objects.create(
            resultado=self.resultado, nombre="A",
            cumplimiento=Decimal(cumplimiento))


class MetaContableTests(BaseAvanceTest):

    def medir(self, meta, alcanzado, unidad="convenios"):
        self.resultado.metodo_avance = Resultado.METODO_META
        self.resultado.unidad_meta = unidad
        self.resultado.meta = meta
        self.resultado.alcanzado = alcanzado
        self.resultado.save()
        return self.resultado.cumplimiento

    def test_el_avance_es_alcanzado_sobre_meta(self):
        self.assertEqual(self.medir(12, 7), Decimal("58.33"))

    def test_cero_alcanzado_es_cero(self):
        self.assertEqual(self.medir(12, 0), Decimal("0"))

    def test_la_meta_cumplida_es_cien(self):
        self.assertEqual(self.medir(12, 12), Decimal("100"))

    def test_superar_la_meta_se_topa_en_cien(self):
        """Sin tope, un resultado sobrecumplido aportaría al valor ganado más
        presupuesto del que tiene asignado y el EV podría pasarse del BAC.
        Quince convenios de doce es una buena noticia, no 125% de trabajo."""
        self.assertEqual(self.medir(12, 15), Decimal("100"))

    def test_sin_meta_no_hay_avance_en_vez_de_reventar(self):
        self.resultado.metodo_avance = Resultado.METODO_META
        self.resultado.meta = None
        self.resultado.save()
        self.assertEqual(self.resultado.cumplimiento, Decimal("0"))

    def test_las_actividades_dejan_de_mandar(self):
        """Declarar una meta reemplaza el promedio de actividades: si siguiera
        mandando el promedio, la meta sería decorativa."""
        self.actividad(100)
        self.assertEqual(self.medir(10, 2), Decimal("20"))

    def test_la_fila_dice_de_donde_sale_el_numero(self):
        self.medir(12, 7)
        self.assertEqual(self.resultado.avance_explicacion, "7 de 12 convenios")


class EscalaDeTramosTests(BaseAvanceTest):

    def medir(self, tramo):
        self.resultado.metodo_avance = Resultado.METODO_TRAMOS
        self.resultado.tramo = tramo
        self.resultado.save()
        return self.resultado.cumplimiento

    def test_el_avance_es_el_tramo(self):
        for tramo in (0, 25, 50, 75, 100):
            self.assertEqual(self.medir(tramo), Decimal(tramo))

    def test_la_escala_tiene_cinco_escalones_con_criterio(self):
        """Que todos usen los mismos cinco es lo que hace comparables los
        resultados que no se pueden contar."""
        self.assertEqual([v for v, _ in Resultado.TRAMOS], [0, 25, 50, 75, 100])
        for _, etiqueta in Resultado.TRAMOS:
            self.assertIn("—", etiqueta)

    def test_la_fila_explica_el_tramo_en_palabras(self):
        self.medir(50)
        self.assertEqual(
            self.resultado.avance_explicacion, "En ejecución, primera mitad")


class PromedioDeActividadesTests(BaseAvanceTest):

    def test_sigue_siendo_el_metodo_de_los_que_no_declaran(self):
        """Retrocompatibilidad: los resultados que ya existían no cambian de
        número al desplegar."""
        self.actividad(100)
        self.actividad(50)
        self.assertEqual(self.resultado.metodo_avance, "")
        self.assertEqual(self.resultado.cumplimiento, Decimal("75"))

    def test_sin_actividades_da_cero_y_se_avisa_que_falta_definirlo(self):
        self.assertEqual(self.resultado.cumplimiento, Decimal("0"))
        self.assertFalse(self.resultado.avance_definido)
        self.assertIn("sin actividades", self.resultado.avance_explicacion)

    def test_elegirlo_explicitamente_se_distingue_de_no_haber_elegido(self):
        self.actividad(60)
        self.resultado.metodo_avance = Resultado.METODO_ACTIVIDADES
        self.resultado.save()
        self.assertTrue(self.resultado.avance_definido)
        self.assertEqual(self.resultado.cumplimiento, Decimal("60"))


class PantallaTests(BaseAvanceTest):

    def form(self):
        return self.client.get(
            reverse("proyectos:avance_resultado_form", args=[self.resultado.pk]))

    def guardar(self, **datos):
        return self.client.post(
            reverse("proyectos:guardar_avance_resultado", args=[self.resultado.pk]),
            datos)

    def test_el_formulario_ofrece_los_tres_metodos(self):
        html = self.form().content.decode()
        for texto in ("Meta contable", "Escala de tramos",
                      "Promedio de sus actividades"):
            self.assertIn(texto, html)

    def test_la_meta_va_primero(self):
        """Con la escala arriba casi todos se quedarían en ella por ser más
        rápida de llenar, y se perdería el único método verificable."""
        html = self.form().content.decode()
        self.assertLess(html.index("Meta contable"), html.index("Escala de tramos"))

    def test_guarda_una_meta(self):
        self.guardar(metodo_avance="META", unidad_meta="convenios",
                     meta="12", alcanzado="7")
        self.resultado.refresh_from_db()
        self.assertEqual(self.resultado.metodo_avance, Resultado.METODO_META)
        self.assertEqual(self.resultado.cumplimiento, Decimal("58.33"))

    def test_guarda_un_tramo(self):
        self.guardar(metodo_avance="TRAMOS", tramo="75")
        self.resultado.refresh_from_db()
        self.assertEqual(self.resultado.cumplimiento, Decimal("75"))

    def test_una_meta_sin_unidad_se_rechaza_y_lo_explica(self):
        r = self.guardar(metodo_avance="META", unidad_meta="", meta="12")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Di qué se cuenta", r.content.decode())
        self.resultado.refresh_from_db()
        self.assertEqual(self.resultado.metodo_avance, "")

    def test_una_meta_en_cero_se_rechaza(self):
        r = self.guardar(metodo_avance="META", unidad_meta="convenios", meta="0")
        self.assertEqual(r.status_code, 400)
        self.assertIn("mayor que cero", r.content.decode())

    def test_un_tramo_inventado_cae_a_cero(self):
        self.guardar(metodo_avance="TRAMOS", tramo="63")
        self.resultado.refresh_from_db()
        self.assertEqual(self.resultado.tramo, 0)

    def test_un_metodo_inventado_se_ignora(self):
        self.guardar(metodo_avance="LO_QUE_SEA")
        self.resultado.refresh_from_db()
        self.assertEqual(self.resultado.metodo_avance, "")

    def test_los_numeros_no_se_localizan_en_el_formulario(self):
        """Un `value="1.200"` en un input numérico lo deja vacío al abrirlo."""
        self.resultado.metodo_avance = Resultado.METODO_META
        self.resultado.unidad_meta = "convenios"
        self.resultado.meta = 1200
        self.resultado.alcanzado = 1100
        self.resultado.save()
        html = self.form().content.decode()
        self.assertIn('value="1200"', html)
        self.assertNotIn('value="1.200"', html)

    def test_la_fila_marca_los_que_no_tienen_metodo(self):
        html = self.client.get(
            reverse("proyectos:fila_resultado", args=[self.resultado.pk])
        ).content.decode()
        self.assertIn("sin método definido", html)

    def test_quien_no_lleva_el_proyecto_no_puede_tocarlo(self):
        self.client.force_login(User.objects.create_user("ajena", password="x"))
        self.assertEqual(self.form().status_code, 403)
        self.assertEqual(
            self.guardar(metodo_avance="TRAMOS", tramo="100").status_code, 403)


class EfectoEnElValorGanadoTests(BaseAvanceTest):
    """El avance del resultado es lo que el valor ganado convierte en pesos."""

    def test_el_ev_toma_el_metodo_elegido(self):
        from datetime import date
        from . import evm

        self.proyecto.presupuesto_total = Decimal("1000000")
        self.proyecto.presupuesto_corriente = Decimal("1000000")
        self.proyecto.anio_inicial = 2026
        self.proyecto.duracion_meses = 12
        self.proyecto.save()

        # Con actividades al 100% pero meta a medias, manda la meta.
        self.actividad(100)
        self.resultado.metodo_avance = Resultado.METODO_META
        self.resultado.unidad_meta = "convenios"
        self.resultado.meta = 10
        self.resultado.alcanzado = 3
        self.resultado.save()

        v = evm.calcular(self.proyecto, hoy=date(2026, 6, 30))
        self.assertEqual(v.ev, Decimal("300000"))

    def test_el_avance_por_meta_cuenta_como_avance_cargado(self):
        """Si no, un proyecto que mide por metas quedaría marcado como «nadie
        cargó avance» aunque tenga sus metas al día."""
        from datetime import date
        from . import evm

        self.proyecto.anio_inicial = 2026
        self.proyecto.duracion_meses = 12
        self.proyecto.save()
        self.resultado.metodo_avance = Resultado.METODO_META
        self.resultado.unidad_meta = "convenios"
        self.resultado.meta = 10
        self.resultado.alcanzado = 4
        self.resultado.save()

        v = evm.calcular(self.proyecto, hoy=date(2026, 6, 30))
        self.assertGreater(v.ev, 0)
        self.assertTrue(v.avance_cargado)

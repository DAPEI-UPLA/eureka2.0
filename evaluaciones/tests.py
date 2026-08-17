from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from . import perfiles as perf
from .estructura import ARBOL, recorrer
from .models import NivelRequerido, guardar_niveles, niveles_de
from .motor import (
    Config, DatosAsistencia, asistencia_t2, evaluar, evaluar_asistencia,
    evaluar_generico, perfil_t2,
)

RUTA_T2 = "VAF/finanzas-presupuestos/tesoreria/t2"
RUTA_D3 = "VAF/finanzas-presupuestos/presupuesto/d3"
RUTA_A1 = "VAF/finanzas-presupuestos/presupuesto/a1"


class MotorContraElExcelTests(TestCase):
    """El motor debe dar exactamente lo que daba Instrumento_T2_automatico.xlsx.

    Esta comparación existía como un bloque `__main__` que había que acordarse
    de ejecutar. Acá corre sola: si alguien ajusta un peso o un umbral de la
    escala, la prueba dice qué valor dejó de calzar con el archivo original.
    """

    ESPERADO = {
        "nota_funciones": 7.394871794871795,
        "nota_competencias": 9.236363636363636,
        "nota_conocimientos": 8.8,
        "nota_asistencia": 10.0,
        "nota_final": 8.288344988344988,
    }
    ESPERADO_FACTORES = {
        "1A": 8.470955652717052,
        "1B": 7.960419091967403,
        "2A": 9.251682368775235,
        "2B": 9.285714285714286,
        "3A": 7.8982423681776135,
    }

    def setUp(self):
        self.resultado = evaluar(perfil_t2(), asistencia_t2())

    def test_las_cuatro_notas_y_la_final_calzan_con_el_excel(self):
        for campo, esperado in self.ESPERADO.items():
            with self.subTest(campo=campo):
                self.assertAlmostEqual(getattr(self.resultado, campo), esperado, places=9)

    def test_las_notas_por_factor_calzan_con_el_excel(self):
        for factor, esperado in self.ESPERADO_FACTORES.items():
            with self.subTest(factor=factor):
                self.assertAlmostEqual(
                    self.resultado.notas_por_factor[factor], esperado, places=9)

    def test_el_factor_3b_es_la_nota_de_asistencia(self):
        self.assertEqual(self.resultado.notas_por_factor["3B"],
                         self.resultado.nota_asistencia)

    def test_la_interpretacion_del_ejemplo_es_muy_bueno(self):
        self.assertEqual(self.resultado.interpretacion, "Muy Bueno")

    def test_la_categoria_de_la_brecha_sale_escrita_para_leer(self):
        categorias = {b["categoria"] for b in self.resultado.brechas_prioritarias}
        self.assertTrue(categorias <= {"Función", "Competencia", "Conocimiento"})

    def test_las_brechas_vienen_de_mayor_a_menor(self):
        brechas = [b["brecha"] for b in self.resultado.brechas_prioritarias]
        self.assertEqual(brechas, sorted(brechas, reverse=True))
        self.assertTrue(all(b >= 1 for b in brechas))


class AsistenciaTests(TestCase):
    """La asistencia tiene dos reglas del Excel que no son obvias."""

    def test_las_inasistencias_justificadas_no_penalizan(self):
        cfg = Config()
        base = dict(dias_habiles=20, dias_asistidos=20, atrasos=0, salidas_anticipadas=0)
        sin_justificar = evaluar_asistencia(
            DatosAsistencia(**base, inasistencias_justificadas=0), cfg)
        con_justificadas = evaluar_asistencia(
            DatosAsistencia(**base, inasistencias_justificadas=5), cfg)
        self.assertEqual(sin_justificar["nota"], con_justificadas["nota"])

    def test_atrasos_y_salidas_bajan_la_nota(self):
        cfg = Config()
        # 7 atrasos = 3,5% de incumplimiento: cruza el primer umbral (3%)
        limpio = evaluar_asistencia(
            DatosAsistencia(dias_habiles=20, dias_asistidos=20), cfg)
        con_atrasos = evaluar_asistencia(
            DatosAsistencia(dias_habiles=20, dias_asistidos=20, atrasos=7), cfg)
        self.assertEqual(limpio["nota"], 10.0)
        self.assertEqual(con_atrasos["nota"], 8.0)

    def test_marca_inconsistencia_cuando_los_dias_no_cuadran(self):
        # Faltó 3 días pero no se registró ninguna inasistencia injustificada
        resultado = evaluar_asistencia(
            DatosAsistencia(dias_habiles=20, dias_asistidos=17), Config())
        self.assertFalse(resultado["consistente"])
        self.assertEqual(resultado["dias_no_asistidos"], 3)

    def test_sin_dias_habiles_no_divide_por_cero(self):
        resultado = evaluar_asistencia(
            DatosAsistencia(dias_habiles=0, dias_asistidos=0,
                            inasistencias_injustificadas=2), Config())
        self.assertEqual(resultado["pct_incumplimiento"], 0.0)


class TroceoDelPerfilTests(TestCase):
    """El perfil viene como prosa; hay que partirlo en ítems evaluables."""

    def test_las_funciones_numeradas_se_separan(self):
        items = perf.partir_funciones(
            "1.- Ejecutar los pagos. 2.- Verificar la documentación. 3.- Archivar respaldos.")
        self.assertEqual(len(items), 3)
        self.assertTrue(items[0].startswith("Ejecutar"))

    def test_los_encabezados_de_categoria_no_quedan_como_items(self):
        items = perf.partir_funciones("1.- Revisar cuentas. Funciones de apoyo: 2.- Archivar.")
        self.assertNotIn("Funciones de apoyo:", items)
        self.assertEqual(items[0], "Revisar cuentas.")

    def test_una_lista_por_comas_se_parte_en_items(self):
        items = perf.partir_lista("Proactividad, trabajo en equipo, comunicación efectiva")
        self.assertEqual(items, ["Proactividad", "trabajo en equipo", "comunicación efectiva"])

    def test_un_campo_vacio_no_genera_items(self):
        self.assertEqual(perf.partir_funciones(""), [])
        self.assertEqual(perf.partir_lista(None), [])

    def test_los_perfiles_piloto_producen_secciones(self):
        datos = perf.perfil_de(["tesoreria", "D3"])
        self.assertIsNotNone(datos)
        secciones = perf.secciones_evaluables(datos)
        self.assertTrue(secciones)
        self.assertTrue(all(s["items"] for s in secciones))

    def test_las_claves_de_item_no_se_repiten(self):
        secciones = perf.secciones_evaluables(perf.perfil_de(["tesoreria", "D3"]))
        claves = perf.claves(secciones)
        self.assertEqual(len(claves), len(set(claves)))


class EstructuraTests(TestCase):
    def test_recorrer_arma_el_breadcrumb_completo(self):
        nodo, breadcrumb, color = recorrer(RUTA_T2)
        self.assertTrue(nodo["cargo"])
        self.assertEqual([b["nombre"] for b in breadcrumb][0],
                         ARBOL["VAF"]["nombre"])
        self.assertEqual(len(breadcrumb), 4)
        self.assertEqual(color, ARBOL["VAF"]["color"])

    def test_una_ruta_inventada_da_404(self):
        from django.http import Http404
        with self.assertRaises(Http404):
            recorrer("VAF/no-existe/nada")

    def test_toda_referencia_de_perfil_del_arbol_existe_en_los_datos(self):
        """Un typo en el árbol dejaría el cargo sin ficha, sin decir nada."""
        faltantes = []

        def revisar(nodos, ruta):
            for nid, nodo in nodos.items():
                actual = f"{ruta}/{nid}" if ruta else nid
                if nodo.get("perfil") and perf.perfil_de(nodo["perfil"]) is None:
                    faltantes.append((actual, nodo["perfil"]))
                revisar(nodo.get("hijos") or {}, actual)

        revisar(ARBOL, "")
        self.assertEqual(faltantes, [])


class NivelRequeridoTests(TestCase):
    def test_guardar_dos_veces_actualiza_en_vez_de_duplicar(self):
        # Cargo sin niveles heredados del prototipo, para contar filas limpio
        guardar_niveles(RUTA_A1, {"fun-0": 3, "fun-1": 2})
        guardar_niveles(RUTA_A1, {"fun-0": 4, "fun-1": 2})
        self.assertEqual(NivelRequerido.objects.filter(ruta=RUTA_A1).count(), 2)
        self.assertEqual(niveles_de(RUTA_A1)["fun-0"], 4)

    def test_los_niveles_de_un_cargo_no_se_mezclan_con_los_de_otro(self):
        guardar_niveles(RUTA_D3, {"fun-0": 4})
        guardar_niveles(RUTA_T2, {"fun-0": 1})
        self.assertEqual(niveles_de(RUTA_D3)["fun-0"], 4)
        self.assertEqual(niveles_de(RUTA_T2)["fun-0"], 1)

    def test_la_migracion_trajo_lo_editado_en_el_prototipo(self):
        """El único nivel que el prototipo tenía fuera del valor por defecto."""
        self.assertEqual(niveles_de(RUTA_D3).get("hi-9"), 4)


class EvaluacionGenericaTests(TestCase):
    SECCIONES = [
        {"id": "fun", "titulo": "Funciones críticas", "items": ["Uno", "Dos"]},
        {"id": "hc", "titulo": "Conductuales", "items": ["Tres"]},
    ]

    def test_sin_brechas_la_nota_es_diez(self):
        req = {"fun-0": 3, "fun-1": 3, "hc-0": 3}
        resultado = evaluar_generico(self.SECCIONES, req, dict(req))
        self.assertEqual(resultado["final"], 10.0)
        self.assertEqual(resultado["brechas"], [])
        self.assertEqual(resultado["interpretacion"], "Sobresaliente")

    def test_observar_por_encima_de_lo_requerido_no_sube_la_nota(self):
        req = {"fun-0": 2, "fun-1": 2, "hc-0": 2}
        obs = {"fun-0": 4, "fun-1": 4, "hc-0": 4}
        self.assertEqual(evaluar_generico(self.SECCIONES, req, obs)["final"], 10.0)

    def test_la_nota_por_item_tiene_piso(self):
        # Brecha de 4 daría 10 - 2*4 = 2; el piso es justamente 2, no negativo
        req = {"fun-0": 4, "fun-1": 4, "hc-0": 4}
        obs = {"fun-0": 0, "fun-1": 0, "hc-0": 0}
        self.assertEqual(evaluar_generico(self.SECCIONES, req, obs)["final"], 2.0)

    def test_el_promedio_de_cada_seccion_es_de_esa_seccion(self):
        req = {"fun-0": 3, "fun-1": 3, "hc-0": 3}
        obs = {"fun-0": 1, "fun-1": 1, "hc-0": 3}
        resultado = evaluar_generico(self.SECCIONES, req, obs)
        por_titulo = {s["titulo"]: s["promedio"] for s in resultado["secciones"]}
        self.assertEqual(por_titulo["Funciones críticas"], 6.0)
        self.assertEqual(por_titulo["Conductuales"], 10.0)

    def test_sin_items_no_revienta(self):
        resultado = evaluar_generico([], {}, {})
        self.assertEqual(resultado["final"], 0)
        self.assertEqual(resultado["n_items"], 0)


class VistasTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("evaluador", password="clave-de-prueba")
        self.client.force_login(self.usuario)

    def test_todas_las_pantallas_exigen_sesion(self):
        self.client.logout()
        for url in [reverse("evaluaciones:home"),
                    reverse("evaluaciones:nodo", args=["VAF"]),
                    reverse("evaluaciones:evaluar_cargo", args=[RUTA_D3]),
                    reverse("evaluaciones:instrumento")]:
            with self.subTest(url=url):
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn("/?next=", respuesta["Location"])

    def test_la_portada_lista_las_vicerrectorias(self):
        respuesta = self.client.get(reverse("evaluaciones:home"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Vicerrectoría de Administración y Finanzas")

    def test_una_rama_muestra_sus_hijos(self):
        respuesta = self.client.get(
            reverse("evaluaciones:nodo", args=["VAF/finanzas-presupuestos"]))
        self.assertContains(respuesta, "Departamento de Tesorería")

    def test_un_cargo_muestra_la_ficha_del_perfil(self):
        respuesta = self.client.get(reverse("evaluaciones:nodo", args=[RUTA_D3]))
        self.assertContains(respuesta, "Propósito del cargo")

    def test_un_cargo_sin_perfil_lo_dice_en_vez_de_fallar(self):
        respuesta = self.client.get(
            reverse("evaluaciones:nodo", args=["VAF/rrhh/secretaria"]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Perfil por definir")

    def test_una_ruta_inventada_da_404(self):
        respuesta = self.client.get(reverse("evaluaciones:nodo", args=["VAF/inventada"]))
        self.assertEqual(respuesta.status_code, 404)

    def test_evaluar_un_cargo_guarda_los_niveles_requeridos(self):
        url = reverse("evaluaciones:evaluar_cargo", args=[RUTA_D3])
        secciones = perf.secciones_evaluables(perf.perfil_de(["presupuesto", "D3"]))
        claves = perf.claves(secciones)

        datos = {"accion": "calcular"}
        for clave in claves:
            datos[f"req_{clave}"] = 4
            datos[f"obs_{clave}"] = 2

        respuesta = self.client.post(url, datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Niveles requeridos guardados")

        guardados = niveles_de(RUTA_D3)
        self.assertEqual(set(guardados), set(claves))
        self.assertTrue(all(v == 4 for v in guardados.values()))

    def test_un_nivel_fuera_de_escala_se_acota(self):
        """El <select> ofrece 0-4, pero el POST se puede escribir a mano."""
        url = reverse("evaluaciones:evaluar_cargo", args=[RUTA_D3])
        self.client.post(url, {"accion": "guardar", "req_fun-0": 99, "obs_fun-0": -5})
        self.assertEqual(niveles_de(RUTA_D3)["fun-0"], 4)

    def test_guardar_no_calcula(self):
        url = reverse("evaluaciones:evaluar_cargo", args=[RUTA_D3])
        respuesta = self.client.post(url, {"accion": "guardar", "req_fun-0": 3, "obs_fun-0": 0})
        self.assertIsNone(respuesta.context["resultado"])

    def test_el_instrumento_oficial_calcula_la_nota_del_excel(self):
        datos = {"accion": "calcular"}
        for e in perfil_t2():
            datos[f"obs_{e.id}"] = e.nivel_observado
        for campo, valor in [("dias_habiles", 22), ("dias_asistidos", 21), ("atrasos", 1),
                             ("salidas_anticipadas", 1), ("inasistencias_justificadas", 1),
                             ("inasistencias_injustificadas", 0)]:
            datos[campo] = valor

        respuesta = self.client.post(reverse("evaluaciones:instrumento"), datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertAlmostEqual(
            respuesta.context["resultado"].nota_final, 8.288344988344988, places=9)
        self.assertContains(respuesta, "Muy Bueno")

    def test_el_informe_sale_con_los_datos_de_identificacion(self):
        datos = {"accion": "informe", "funcionario": "Ana Pérez",
                 "evaluador": "Jefatura de Tesorería", "periodo": "2026",
                 "dias_habiles": 22, "dias_asistidos": 22}
        for e in perfil_t2():
            datos[f"obs_{e.id}"] = e.nivel_observado

        respuesta = self.client.post(reverse("evaluaciones:informe"), datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ana Pérez")
        self.assertContains(respuesta, "Jefatura de Tesorería")
        # El informe se pidió con el botón, así que se abre imprimiendo
        self.assertContains(respuesta, "window.print()")

    def test_el_informe_no_se_puede_abrir_por_url(self):
        """Sin el POST del formulario no hay evaluación que informar."""
        respuesta = self.client.get(reverse("evaluaciones:informe"))
        self.assertEqual(respuesta.status_code, 404)

    def test_el_panel_principal_enlaza_el_modulo(self):
        respuesta = self.client.get(reverse("home"))
        self.assertContains(respuesta, reverse("evaluaciones:home"))

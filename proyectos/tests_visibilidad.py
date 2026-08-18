"""Todos ven todos los proyectos; sólo el responsable edita el suyo.

El equipo pidió ver los proyectos de sus compañeros —para saber qué se está
haciendo y no repetir gestiones— pero sin poder tocarlos, y con los propios
primero en la lista.

Lo importante de estas pruebas no es el orden sino lo otro: que abrir la vista
no abra la escritura. Cada endpoint que muta sigue exigiendo ser responsable.
"""

from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.urls import reverse

from .models import Actividad, ObjetivoEspecifico, Proyecto, Resultado
from .tests import BaseProyectoTest


class BaseVisibilidadTest(BaseProyectoTest):
    """Dos personas con un proyecto cada una."""

    def setUp(self):
        super().setUp()
        self.colega = User.objects.create_user("colega", password="x")
        self.ajeno = Proyecto.objects.create(
            nombre="Proyecto del colega",
            responsable=self.colega,
            presupuesto_total=Decimal("500000"),
            presupuesto_corriente=Decimal("500000"),
            presupuesto_capital=Decimal("0"),
        )
        self.objetivo_ajeno = ObjetivoEspecifico.objects.create(
            proyecto=self.ajeno, descripcion="Objetivo ajeno",
        )
        self.resultado_ajeno = Resultado.objects.create(
            objetivo=self.objetivo_ajeno, descripcion="Resultado ajeno",
        )


class TodosVenTodoTests(BaseVisibilidadTest):

    def test_la_lista_trae_tambien_los_de_los_demas(self):
        respuesta = self.client.get(reverse("proyectos:lista_proyectos"))
        nombres = [p.nombre for p in respuesta.context["proyectos"]]
        self.assertIn(self.proyecto.nombre, nombres)
        self.assertIn("Proyecto del colega", nombres)

    def test_los_propios_van_primero(self):
        # Un tercer proyecto ajeno, creado después: sin el orden nuevo quedaría
        # arriba por ser el más reciente.
        Proyecto.objects.create(
            nombre="Otro ajeno", responsable=self.colega,
            presupuesto_total=Decimal("1"), presupuesto_corriente=Decimal("1"),
        )
        respuesta = self.client.get(reverse("proyectos:lista_proyectos"))
        proyectos = list(respuesta.context["proyectos"])

        mios = [p.responsable_id == self.user.id for p in proyectos]
        # Todos los True tienen que venir antes que cualquier False.
        self.assertEqual(mios, sorted(mios, reverse=True), [p.nombre for p in proyectos])
        self.assertEqual(proyectos[0].responsable_id, self.user.id)

    def test_se_informa_cuantos_son_propios(self):
        respuesta = self.client.get(reverse("proyectos:lista_proyectos"))
        self.assertEqual(respuesta.context["mios"], 1)

    def test_el_ajeno_se_marca_como_solo_lectura(self):
        respuesta = self.client.get(reverse("proyectos:lista_proyectos"))
        self.assertContains(respuesta, "Solo lectura")
        self.assertContains(respuesta, "Tuyo")

    def test_se_puede_abrir_el_detalle_de_un_ajeno(self):
        respuesta = self.client.get(
            reverse("proyectos:detalle_proyecto", args=[self.ajeno.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context["es_encargado"])

    def test_se_ven_las_secciones_de_lectura_de_un_ajeno(self):
        for nombre, args in (
            ("proyectos:dashboard_proyecto", [self.ajeno.pk]),
            ("proyectos:graficos_proyecto", [self.ajeno.pk]),
            ("proyectos:listar_objetivos", [self.ajeno.pk]),
            ("proyectos:listar_presupuesto_anual", [self.ajeno.pk]),
            ("proyectos:listar_planes_gasto", [self.ajeno.pk]),
            ("proyectos:listar_egresos", [self.ajeno.pk]),
            ("proyectos:listar_resultados", [self.objetivo_ajeno.pk]),
            ("proyectos:detalle_presupuesto_resultado", [self.resultado_ajeno.pk]),
        ):
            with self.subTest(vista=nombre):
                respuesta = self.client.get(reverse(nombre, args=args))
                self.assertEqual(respuesta.status_code, 200)


class VerNoEsEditarTests(BaseVisibilidadTest):
    """Lo que importa: abrir la vista no abre la escritura."""

    def test_no_puede_crear_nada_en_un_proyecto_ajeno(self):
        casos = [
            ("proyectos:crear_objetivo", [self.ajeno.pk], {}),
            ("proyectos:crear_anio", [self.ajeno.pk], {}),
            ("proyectos:guardar_anios", [self.ajeno.pk], {}),
            ("proyectos:crear_resultado", [self.objetivo_ajeno.pk], {}),
            ("proyectos:crear_actividad", [self.resultado_ajeno.pk], {"nombre": "X"}),
            ("proyectos:eliminar_objetivo", [self.objetivo_ajeno.pk], {}),
            ("proyectos:guardar_presupuesto", [self.resultado_ajeno.pk],
             {"presupuesto_corriente": "1"}),
            ("proyectos:guardar_presupuesto_objetivo_anual", [self.objetivo_ajeno.pk], {}),
            ("proyectos:guardar_presupuesto_resultado_anual", [self.resultado_ajeno.pk], {}),
        ]
        for nombre, args, datos in casos:
            with self.subTest(vista=nombre):
                respuesta = self.client.post(reverse(nombre, args=args), datos)
                self.assertEqual(respuesta.status_code, 403, nombre)

    def test_no_puede_editar_el_proyecto_ajeno(self):
        """Editar y eliminar el proyecto son de jefatura; un par no lo es."""
        for nombre in ("proyectos:editar_proyecto", "proyectos:eliminar_proyecto"):
            with self.subTest(vista=nombre):
                respuesta = self.client.post(reverse(nombre, args=[self.ajeno.pk]))
                self.assertEqual(respuesta.status_code, 403)

    def test_nada_del_ajeno_cambio(self):
        self.client.post(reverse("proyectos:crear_objetivo", args=[self.ajeno.pk]))
        self.client.post(reverse("proyectos:crear_anio", args=[self.ajeno.pk]))
        self.ajeno.refresh_from_db()

        self.assertEqual(self.ajeno.objetivos.count(), 1)   # el del setUp
        self.assertEqual(self.ajeno.presupuestos_anuales.count(), 0)

    def test_los_formularios_de_edicion_siguen_cerrados(self):
        for nombre, args in (
            ("proyectos:editar_objetivo_form", [self.objetivo_ajeno.pk]),
            ("proyectos:editar_presupuesto_objetivo", [self.objetivo_ajeno.pk]),
            ("proyectos:presupuesto_objetivo_anual", [self.objetivo_ajeno.pk]),
            ("proyectos:presupuesto_resultado_anual", [self.resultado_ajeno.pk]),
            ("proyectos:crear_actividad_form", [self.resultado_ajeno.pk]),
        ):
            with self.subTest(vista=nombre):
                self.assertEqual(self.client.get(reverse(nombre, args=args)).status_code, 403)

    def test_la_pantalla_ajena_no_ofrece_el_boton_de_asignar(self):
        respuesta = self.client.get(
            reverse("proyectos:detalle_presupuesto_resultado",
                    args=[self.resultado_ajeno.pk])
        )
        self.assertFalse(respuesta.context["puede_editar"])
        self.assertNotContains(respuesta, "Asignar presupuesto")

    def test_en_el_propio_si_aparece(self):
        objetivo = self.crear_objetivo()
        resultado = self.crear_resultado(objetivo)
        respuesta = self.client.get(
            reverse("proyectos:detalle_presupuesto_resultado", args=[resultado.pk])
        )
        self.assertTrue(respuesta.context["puede_editar"])
        self.assertContains(respuesta, "Asignar presupuesto")


class JefaturaTests(BaseVisibilidadTest):
    """La jefatura sí puede sobre cualquiera; nada de esto se lo quita."""

    def setUp(self):
        super().setUp()
        grupo, _ = Group.objects.get_or_create(name="JefeProyectos")
        self.user.groups.add(grupo)

    def test_la_jefatura_puede_editar_un_proyecto_ajeno(self):
        respuesta = self.client.post(
            reverse("proyectos:crear_anio", args=[self.ajeno.pk])
        )
        self.assertNotEqual(respuesta.status_code, 403)
        self.assertEqual(self.ajeno.presupuestos_anuales.count(), 1)


class SoloMiraTests(BaseVisibilidadTest):
    """Alguien sin rol y sin proyectos propios: entra sólo a mirar.

    No hace falta un rol de «visor»: la ausencia de rol ya es solo lectura.
    Lo que hay que cuidar es que la pantalla no le ofrezca lo que no puede
    hacer, y que ningún endpoint se le abra por descuido.
    """

    def setUp(self):
        super().setUp()
        self.miron = User.objects.create_user("miron", password="x")
        self.client.force_login(self.miron)

    def test_no_tiene_rol_ni_proyectos(self):
        self.assertFalse(self.miron.groups.exists())
        self.assertFalse(Proyecto.objects.filter(responsable=self.miron).exists())

    def test_ve_todos_los_proyectos(self):
        respuesta = self.client.get(reverse("proyectos:lista_proyectos"))
        self.assertEqual(len(respuesta.context["proyectos"]), Proyecto.objects.count())
        self.assertEqual(respuesta.context["mios"], 0)

    def test_la_pantalla_no_le_promete_proyectos_propios(self):
        """Con cero propios, «los tuyos primero» no significa nada."""
        respuesta = self.client.get(reverse("proyectos:lista_proyectos"))
        self.assertContains(respuesta, "solo lectura")
        self.assertNotContains(respuesta, "los tuyos primero")

    def test_no_aparece_el_separador_de_companeros(self):
        """Sin propios no hay nada que separar."""
        respuesta = self.client.get(reverse("proyectos:lista_proyectos"))
        self.assertNotContains(respuesta, "De tus compañeros")

    def test_no_se_le_ofrece_crear_un_proyecto(self):
        respuesta = self.client.get(reverse("proyectos:lista_proyectos"))
        self.assertNotContains(respuesta, "Crear proyecto")
        self.assertFalse(respuesta.context["es_jefe"])

    def test_ninguna_tarjeta_le_ofrece_editar_ni_eliminar(self):
        respuesta = self.client.get(reverse("proyectos:lista_proyectos"))
        cuerpo = respuesta.content.decode()
        self.assertNotIn("editar_proyecto", cuerpo)
        self.assertNotIn("eliminar_proyecto", cuerpo)

    def test_puede_recorrer_un_proyecto_entero(self):
        objetivo = ObjetivoEspecifico.objects.create(
            proyecto=self.proyecto, descripcion="OE",
        )
        resultado = Resultado.objects.create(objetivo=objetivo, descripcion="R")
        Actividad.objects.create(resultado=resultado, nombre="A")

        for nombre, args in (
            ("proyectos:detalle_proyecto", [self.proyecto.pk]),
            ("proyectos:dashboard_proyecto", [self.proyecto.pk]),
            ("proyectos:graficos_proyecto", [self.proyecto.pk]),
            ("proyectos:graficos_proyectos", []),
            ("proyectos:listar_objetivos", [self.proyecto.pk]),
            ("proyectos:listar_resultados", [objetivo.pk]),
            ("proyectos:listar_actividades", [resultado.pk]),
            ("proyectos:listar_presupuesto_anual", [self.proyecto.pk]),
            ("proyectos:selector_anios", [self.proyecto.pk]),
            ("proyectos:listar_planes_gasto", [self.proyecto.pk]),
            ("proyectos:listar_egresos", [self.proyecto.pk]),
            ("proyectos:detalle_presupuesto_resultado", [resultado.pk]),
        ):
            with self.subTest(vista=nombre):
                self.assertEqual(
                    self.client.get(reverse(nombre, args=args)).status_code, 200
                )

    def test_no_puede_escribir_en_ningun_proyecto(self):
        objetivo = ObjetivoEspecifico.objects.create(
            proyecto=self.proyecto, descripcion="OE",
        )
        for nombre, args in (
            ("proyectos:crear_objetivo", [self.proyecto.pk]),
            ("proyectos:crear_anio", [self.proyecto.pk]),
            ("proyectos:guardar_anios", [self.proyecto.pk]),
            ("proyectos:crear_resultado", [objetivo.pk]),
            ("proyectos:eliminar_objetivo", [objetivo.pk]),
            ("proyectos:editar_proyecto", [self.proyecto.pk]),
            ("proyectos:eliminar_proyecto", [self.proyecto.pk]),
        ):
            with self.subTest(vista=nombre):
                self.assertEqual(
                    self.client.post(reverse(nombre, args=args)).status_code, 403
                )

    def test_puede_exportar_e_imprimir(self):
        """Mirar incluye llevarse el informe: no muta nada."""
        for nombre, args in (
            ("proyectos:exportar_proyecto_excel", [self.proyecto.pk]),
            ("proyectos:informe_proyecto", [self.proyecto.pk]),
            ("proyectos:exportar_cartera_excel", []),
        ):
            with self.subTest(vista=nombre):
                self.assertEqual(
                    self.client.get(reverse(nombre, args=args)).status_code, 200
                )

    def test_sin_sesion_no_ve_nada(self):
        """La lectura es para gente con cuenta, no para cualquiera."""
        self.client.logout()
        respuesta = self.client.get(reverse("proyectos:lista_proyectos"))
        self.assertEqual(respuesta.status_code, 302)
        # El login vive en la raíz, no en /login.
        self.assertIn("next=/proyectos/", respuesta.url)

"""El «Año 1 del presupuesto» se declara, no se deduce de la fecha de inicio.

La regla que NO se puede escribir en código: un proyecto que llega en octubre
no alcanza a ejecutar ese año, así que su Año 1 es el siguiente. Cuándo se
corre depende de la resolución y de cuándo se transfiere, y varía de un
proyecto a otro. Por eso lo declara quien crea el proyecto.

Estos tests fijan las consecuencias de esa decisión: de dónde sale el año, qué
pasa cuando falta, y que la corrección de los proyectos viejos no arrastre un
POA a un año que dejó de existir.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group
from django.urls import reverse

from .models import PlanDeGasto, PresupuestoAnual, Proyecto
from .tests import BaseProyectoTest


class BaseAnioInicialTest(BaseProyectoTest):

    def setUp(self):
        super().setUp()
        grupo, _ = Group.objects.get_or_create(name="JefeProyectos")
        self.user.groups.add(grupo)
        self.proyecto.duracion_meses = 36
        self.proyecto.save()

    def crear_anio(self, numero, calendario, **extra):
        return PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=numero,
            anio_calendario=calendario, **extra)


class DeDondeSaleElAnioTests(BaseAnioInicialTest):

    def test_manda_lo_declarado_por_sobre_la_fecha_de_inicio(self):
        """El caso que motivó todo: llega en octubre, ejecuta desde enero."""
        self.proyecto.fecha_inicio = date(2025, 10, 15)
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        self.assertEqual(self.proyecto.anio_calendario_inicial, 2026)

    def test_sin_declarar_cae_a_la_fecha_de_inicio(self):
        """Respaldo para los proyectos viejos. Puede errar por uno, y por eso
        existe el campo."""
        self.proyecto.fecha_inicio = date(2025, 10, 15)
        self.proyecto.save()
        self.assertEqual(self.proyecto.anio_calendario_inicial, 2025)

    def test_sin_nada_cae_al_anio_en_curso(self):
        self.assertEqual(
            self.proyecto.anio_calendario_inicial, date.today().year)


class CuantosAniosTests(BaseAnioInicialTest):

    def test_con_anio_declarado_manda_la_duracion(self):
        """Llega en octubre de 2025 y dura 36 meses: toca cuatro años
        calendario pero tiene TRES años de presupuesto, porque 2025 no se
        ejecuta. Contar por fechas agregaría un año de más."""
        self.proyecto.fecha_inicio = date(2025, 10, 1)
        self.proyecto.fecha_fin = date(2028, 9, 30)
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        self.assertEqual(self.proyecto.cantidad_anios_sugerida, 3)
        self.assertEqual(
            self.proyecto.anios_calendario_esperados, [2026, 2027, 2028])

    def test_sin_anio_declarado_manda_el_rango_de_fechas(self):
        self.proyecto.fecha_inicio = date(2025, 10, 1)
        self.proyecto.fecha_fin = date(2028, 9, 30)
        self.proyecto.save()
        self.assertEqual(self.proyecto.cantidad_anios_sugerida, 4)

    def test_sin_anio_declarado_no_se_proponen_anios(self):
        """No se deduce de la fecha: un año de partida inventado se ve tan
        legítimo como uno declarado y nadie lo vuelve a mirar."""
        self.proyecto.fecha_inicio = date(2025, 10, 1)
        self.proyecto.save()
        self.assertEqual(self.proyecto.anios_calendario_esperados, [])
        self.assertEqual(self.proyecto.anios_faltantes, [])
        self.assertFalse(self.proyecto.anios_desalineados)


class FormularioTests(BaseAnioInicialTest):

    def test_el_modal_de_crear_pide_el_anio_1(self):
        html = self.client.get(reverse("proyectos:lista_proyectos")).content.decode()
        self.assertIn('name="anio_inicial"', html)
        self.assertIn("Año 1 del presupuesto", html)

    def test_se_guarda_al_crear(self):
        self.client.post(reverse("proyectos:lista_proyectos"), {
            "nombre": "Llega en octubre", "codigo": "UPA 2599", "descripcion": "",
            "tipo": self.proyecto.tipo, "responsable": self.user.pk,
            "duracion_meses": 36, "prioridad": "MEDIA", "estado": "PLANIFICADO",
            "fecha_inicio": "2025-10-15", "fecha_fin": "2028-10-14",
            "anio_inicial": "2026",
        })
        proyecto = Proyecto.objects.get(nombre="Llega en octubre")
        self.assertEqual(proyecto.fecha_inicio, date(2025, 10, 15))
        self.assertEqual(proyecto.anio_inicial, 2026)

    def test_el_boton_de_editar_lo_lleva_para_precargarlo(self):
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        html = self.client.get(reverse("proyectos:lista_proyectos")).content.decode()
        self.assertIn('data-anio-inicial="2026"', html)
        self.assertIn("edit_id_anio_inicial', d.anioInicial", html)

    def test_editar_sin_tocarlo_no_lo_borra(self):
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        self.client.post(
            reverse("proyectos:editar_proyecto", args=[self.proyecto.pk]), {
                "nombre": self.proyecto.nombre, "codigo": "", "descripcion": "",
                "tipo": self.proyecto.tipo, "responsable": self.user.pk,
                "duracion_meses": 36, "prioridad": "ALTA",
                "estado": self.proyecto.estado, "anio_inicial": "2026",
            })
        self.proyecto.refresh_from_db()
        self.assertEqual(self.proyecto.prioridad, "ALTA")
        self.assertEqual(self.proyecto.anio_inicial, 2026)

    def test_sigue_siendo_opcional(self):
        r = self.client.post(reverse("proyectos:lista_proyectos"), {
            "nombre": "Sin año", "codigo": "", "descripcion": "",
            "tipo": self.proyecto.tipo, "responsable": self.user.pk,
            "duracion_meses": 24, "prioridad": "MEDIA", "estado": "PLANIFICADO",
        })
        self.assertEqual(r.status_code, 302)
        self.assertIsNone(Proyecto.objects.get(nombre="Sin año").anio_inicial)


class CrearTodosLosAniosTests(BaseAnioInicialTest):

    def url(self):
        return reverse("proyectos:crear_anios_del_proyecto", args=[self.proyecto.pk])

    def test_crea_los_anios_desde_el_declarado(self):
        self.proyecto.fecha_inicio = date(2025, 10, 1)
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()

        self.client.post(self.url())

        anios = self.proyecto.presupuestos_anuales.order_by("numero_anio")
        self.assertEqual(
            [(a.numero_anio, a.anio_calendario) for a in anios],
            [(1, 2026), (2, 2027), (3, 2028)],
        )

    def test_nacen_en_cero(self):
        """El monto lo sabe el equipo. Repartir en partes iguales sólo lograría
        que aceptaran la cifra sin mirarla."""
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        self.client.post(self.url())
        for anio in self.proyecto.presupuestos_anuales.all():
            self.assertEqual(anio.presupuesto_total, Decimal("0"))

    def test_completa_sin_duplicar_los_que_ya_estan(self):
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        self.crear_anio(1, 2026, presupuesto_corriente=Decimal("500000"))

        self.client.post(self.url())

        anios = self.proyecto.presupuestos_anuales.order_by("anio_calendario")
        self.assertEqual([a.anio_calendario for a in anios], [2026, 2027, 2028])
        self.assertEqual(anios[0].presupuesto_corriente, Decimal("500000"))

    def test_sin_anio_declarado_se_niega_y_explica(self):
        self.proyecto.fecha_inicio = date(2025, 10, 1)
        self.proyecto.save()
        html = self.client.post(self.url()).content.decode()
        self.assertIn("Año 1 del presupuesto", html)
        self.assertEqual(self.proyecto.presupuestos_anuales.count(), 0)

    def test_avisa_cuando_ya_estan_todos(self):
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        self.client.post(self.url())
        html = self.client.post(self.url()).content.decode()
        self.assertIn("ya tiene sus", html)
        self.assertEqual(self.proyecto.presupuestos_anuales.count(), 3)

    def test_quien_no_lleva_el_proyecto_no_puede(self):
        from django.contrib.auth.models import User
        self.proyecto.anio_inicial = 2026
        self.proyecto.save()
        self.client.force_login(User.objects.create_user("ajena", password="x"))
        self.assertEqual(self.client.post(self.url()).status_code, 403)


class RealinearTests(BaseAnioInicialTest):
    """Los proyectos viejos quedaron con «Año 1 → año en curso»."""

    def setUp(self):
        super().setUp()
        self.proyecto.duracion_meses = 24
        self.proyecto.anio_inicial = 2024
        self.proyecto.save()
        self.a1 = self.crear_anio(1, 2026, presupuesto_corriente=Decimal("600000"))
        self.a2 = self.crear_anio(2, 2027, presupuesto_corriente=Decimal("400000"))

    def url(self):
        return reverse("proyectos:realinear_anios", args=[self.proyecto.pk])

    def test_detecta_el_desalineo(self):
        self.assertTrue(self.proyecto.anios_desalineados)
        self.assertEqual(self.proyecto.anios_calendario_esperados, [2024, 2025])

    def test_la_pantalla_lo_avisa(self):
        html = self.client.get(
            reverse("proyectos:listar_presupuesto_anual", args=[self.proyecto.pk])
        ).content.decode()
        self.assertIn("no calzan con el Año 1", html)

    def test_mueve_los_anios_conservando_los_montos(self):
        self.client.post(self.url())
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.assertEqual(self.a1.anio_calendario, 2024)
        self.assertEqual(self.a2.anio_calendario, 2025)
        self.assertEqual(self.a1.presupuesto_corriente, Decimal("600000"))

    def test_puede_mover_hacia_adelante_sin_chocar_consigo_mismo(self):
        """El año calendario es único por proyecto: mover 2026->2027 mientras
        2027 existe rompe la restricción si se hace de una pasada."""
        self.proyecto.anio_inicial = 2027
        self.proyecto.save()
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 200)
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.assertEqual(
            sorted([self.a1.anio_calendario, self.a2.anio_calendario]),
            [2027, 2028])

    def test_se_niega_si_algun_anio_tiene_poa(self):
        """`PlanDeGasto.anio` es un año suelto: mover el PresupuestoAnual no
        arrastra su POA y lo dejaría respaldando un año inexistente."""
        from .models import CORRIENTE, GastoElegible
        objetivo = self.crear_objetivo(presupuesto_corriente=Decimal("600000"))
        resultado = self.crear_resultado(
            objetivo, presupuesto_corriente=Decimal("600000"))
        PlanDeGasto.objects.create(
            resultado=resultado, anio=2026, monto=Decimal("100000"),
            gasto_elegible=GastoElegible.objects.filter(
                gasto__tipo_gasto__transferencia__naturaleza=CORRIENTE).first(),
        )

        html = self.client.post(self.url()).content.decode()
        self.assertIn("ya tiene planes de gasto", html)
        self.a1.refresh_from_db()
        self.assertEqual(self.a1.anio_calendario, 2026)

    def test_sin_anio_declarado_no_hay_nada_que_realinear(self):
        self.proyecto.anio_inicial = None
        self.proyecto.save()
        html = self.client.post(self.url()).content.decode()
        self.assertIn("Falta el «Año 1", html)
        self.a1.refresh_from_db()
        self.assertEqual(self.a1.anio_calendario, 2026)

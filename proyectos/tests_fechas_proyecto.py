"""Fecha de inicio y término del proyecto en los modales de crear y editar.

Sin estas dos fechas hay tres cosas que quedan apagadas sin decirlo:
`Proyecto.atrasado` devuelve siempre False, `dias_restantes` devuelve None, y
el valor ganado no encuentra línea base. Los diez proyectos cargados hasta hoy
las tienen vacías, así que la insignia «Atrasado» nunca se ha encendido.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group
from django.urls import reverse

from .models import Proyecto
from .tests import BaseProyectoTest


class BaseFechasTest(BaseProyectoTest):

    def setUp(self):
        super().setUp()
        # Crear y editar proyectos es de jefatura.
        grupo, _ = Group.objects.get_or_create(name="JefeProyectos")
        self.user.groups.add(grupo)

    def datos(self, **extra):
        datos = {
            "nombre": "Proyecto nuevo",
            "codigo": "UPA 2601",
            "descripcion": "",
            "tipo": self.proyecto.tipo,
            "responsable": self.user.pk,
            "duracion_meses": 36,
            "prioridad": "MEDIA",
            "estado": "PLANIFICADO",
        }
        datos.update(extra)
        return datos


class CrearConFechasTests(BaseFechasTest):

    def test_el_modal_de_crear_ofrece_las_dos_fechas(self):
        html = self.client.get(reverse("proyectos:lista_proyectos")).content.decode()
        self.assertIn('name="fecha_inicio"', html)
        self.assertIn('name="fecha_fin"', html)
        self.assertIn("Fecha de inicio", html)
        self.assertIn("Fecha de término", html)

    def test_son_campos_de_fecha_del_navegador(self):
        """Un input de texto obligaría a escribir el formato a mano y cada
        persona lo escribiría distinto."""
        html = self.client.get(reverse("proyectos:lista_proyectos")).content.decode()
        campo = [l for l in html.splitlines() if 'name="fecha_inicio"' in l][0]
        self.assertIn('type="date"', campo)

    def test_se_guardan_al_crear(self):
        self.client.post(reverse("proyectos:lista_proyectos"), self.datos(
            fecha_inicio="2026-03-01", fecha_fin="2029-02-28"))
        proyecto = Proyecto.objects.get(nombre="Proyecto nuevo")
        self.assertEqual(proyecto.fecha_inicio, date(2026, 3, 1))
        self.assertEqual(proyecto.fecha_fin, date(2029, 2, 28))

    def test_siguen_siendo_opcionales(self):
        """No se vuelven obligatorias: hay proyectos que se cargan antes de
        tener resolución con fechas, y bloquear la creación por eso empujaría
        a inventarlas."""
        r = self.client.post(reverse("proyectos:lista_proyectos"), self.datos())
        self.assertEqual(r.status_code, 302)
        self.assertIsNone(Proyecto.objects.get(nombre="Proyecto nuevo").fecha_inicio)

    def test_no_acepta_un_termino_anterior_al_inicio(self):
        self.client.post(reverse("proyectos:lista_proyectos"), self.datos(
            fecha_inicio="2029-01-01", fecha_fin="2026-01-01"))
        self.assertFalse(Proyecto.objects.filter(nombre="Proyecto nuevo").exists())


class EditarConFechasTests(BaseFechasTest):

    def setUp(self):
        super().setUp()
        self.proyecto.fecha_inicio = date(2026, 3, 1)
        self.proyecto.fecha_fin = date(2029, 2, 28)
        self.proyecto.save()

    def test_el_boton_de_editar_lleva_las_fechas_en_iso(self):
        """El campo de fecha del navegador sólo acepta ISO. Con el formato
        localizado el valor se descarta en silencio y el campo aparece vacío,
        que es justo el camino a borrarlas sin querer."""
        html = self.client.get(reverse("proyectos:lista_proyectos")).content.decode()
        self.assertIn('data-inicio="2026-03-01"', html)
        self.assertIn('data-fin="2029-02-28"', html)

    def test_editar_sin_tocar_las_fechas_no_las_borra(self):
        """El riesgo real de este cambio.

        El modal de edición se rellena por JavaScript desde los `data-*` del
        botón. Si se agregan los campos al formulario pero no al botón, llegan
        vacíos al POST y el ModelForm los guarda como nulos: editar la
        prioridad de un proyecto le borraría las fechas.
        """
        self.client.post(
            reverse("proyectos:editar_proyecto", args=[self.proyecto.pk]),
            {
                "nombre": self.proyecto.nombre,
                "codigo": self.proyecto.codigo or "",
                "descripcion": "",
                "tipo": self.proyecto.tipo,
                "responsable": self.user.pk,
                "duracion_meses": 36,
                "prioridad": "ALTA",
                "estado": self.proyecto.estado,
                # Lo que el JS precarga desde los data-*.
                "fecha_inicio": "2026-03-01",
                "fecha_fin": "2029-02-28",
            },
        )
        self.proyecto.refresh_from_db()
        self.assertEqual(self.proyecto.prioridad, "ALTA")
        self.assertEqual(self.proyecto.fecha_inicio, date(2026, 3, 1))
        self.assertEqual(self.proyecto.fecha_fin, date(2029, 2, 28))

    def test_el_modal_de_edicion_tiene_los_campos_con_su_id_propio(self):
        """El JS los busca por `edit_id_*`; si el `auto_id` cambiara, la
        precarga fallaría en silencio y volvería el borrado."""
        html = self.client.get(reverse("proyectos:lista_proyectos")).content.decode()
        self.assertIn('id="edit_id_fecha_inicio"', html)
        self.assertIn('id="edit_id_fecha_fin"', html)

    def test_el_javascript_precarga_los_dos_campos(self):
        html = self.client.get(reverse("proyectos:lista_proyectos")).content.decode()
        self.assertIn("edit_id_fecha_inicio', d.inicio", html)
        self.assertIn("edit_id_fecha_fin', d.fin", html)


class LoQueSeEnciendeTests(BaseFechasTest):
    """Las tres cosas que hoy están apagadas por falta de fechas."""

    def test_sin_fecha_fin_un_proyecto_vencido_no_sale_atrasado(self):
        self.proyecto.fecha_fin = None
        self.proyecto.save()
        self.assertFalse(self.proyecto.atrasado)
        self.assertIsNone(self.proyecto.dias_restantes)

    def test_con_fecha_fin_pasada_si_sale_atrasado(self):
        self.proyecto.fecha_inicio = date(2020, 1, 1)
        self.proyecto.fecha_fin = date(2021, 1, 1)
        self.proyecto.estado = "EN_EJECUCION"
        self.proyecto.save()
        self.assertTrue(self.proyecto.atrasado)
        self.assertLess(self.proyecto.dias_restantes, 0)

    def test_las_fechas_habilitan_el_valor_ganado(self):
        from . import evm
        from .models import Actividad
        objetivo = self.crear_objetivo(presupuesto_corriente=Decimal("1000000"))
        resultado = self.crear_resultado(
            objetivo, presupuesto_corriente=Decimal("1000000"))
        Actividad.objects.create(
            resultado=resultado, nombre="A", cumplimiento=Decimal("50"))

        self.proyecto.fecha_inicio = None
        self.proyecto.fecha_fin = None
        self.proyecto.save()
        self.assertIsNone(evm.calcular(self.proyecto, hoy=date(2026, 6, 1)).spi)

        self.proyecto.fecha_inicio = date(2026, 1, 1)
        self.proyecto.fecha_fin = date(2027, 12, 31)
        self.proyecto.save()
        self.assertIsNotNone(evm.calcular(self.proyecto, hoy=date(2026, 6, 1)).spi)

    def test_los_anios_sugeridos_salen_de_las_fechas_y_no_de_la_duracion(self):
        """Un proyecto de 36 meses que parte en julio toca CUATRO años
        calendario. Con sólo la duración el sistema propone tres y el último
        año se queda sin dónde cargar presupuesto."""
        self.proyecto.duracion_meses = 36
        self.proyecto.fecha_inicio = None
        self.proyecto.fecha_fin = None
        self.proyecto.save()
        self.assertEqual(self.proyecto.cantidad_anios_sugerida, 3)

        self.proyecto.fecha_inicio = date(2026, 7, 1)
        self.proyecto.fecha_fin = date(2029, 6, 30)
        self.proyecto.save()
        self.assertEqual(self.proyecto.cantidad_anios_sugerida, 4)

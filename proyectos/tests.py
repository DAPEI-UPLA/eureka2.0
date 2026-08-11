"""
Pruebas de las correcciones reportadas sobre la app de proyectos:
objetivos sin texto de relleno, presupuesto de actividad sin tope imposible,
borrado que se refleja solo (sin F5) y reordenamiento de las filas.
"""

import re
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import (
    CAPITAL,
    CORRIENTE,
    Actividad,
    Egreso,
    GastoElegible,
    ObjetivoEspecifico,
    PlanDeGasto,
    Proyecto,
    Resultado,
)


class BaseProyectoTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("responsable", password="x")
        self.proyecto = Proyecto.objects.create(
            nombre="Proyecto de prueba",
            responsable=self.user,
            presupuesto_total=Decimal("1000000"),
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
        self.client.force_login(self.user)

    def crear_objetivo(self, **kwargs):
        datos = {
            "proyecto": self.proyecto,
            "descripcion": "Objetivo",
            "presupuesto_corriente": Decimal("0"),
            "presupuesto_capital": Decimal("0"),
        }
        datos.update(kwargs)
        return ObjetivoEspecifico.objects.create(**datos)

    def crear_resultado(self, objetivo, **kwargs):
        datos = {"objetivo": objetivo, "descripcion": "Resultado"}
        datos.update(kwargs)
        return Resultado.objects.create(**datos)


class ObjetivoTests(BaseProyectoTest):
    def test_objetivo_nuevo_nace_sin_texto_de_relleno(self):
        self.client.post(reverse("proyectos:crear_objetivo", args=[self.proyecto.pk]))
        objetivo = self.proyecto.objetivos.get()
        self.assertEqual(objetivo.descripcion, "")

    def test_formulario_de_edicion_llega_vacio(self):
        objetivo = self.crear_objetivo(descripcion="")
        html = self.client.get(
            reverse("proyectos:editar_objetivo_form", args=[objetivo.pk])
        ).content.decode()
        self.assertIn("<textarea", html)
        self.assertIn("></textarea>", html)

    def test_eliminar_objetivo_responde_con_cuerpo_y_evento(self):
        objetivo = self.crear_objetivo()
        r = self.client.post(reverse("proyectos:eliminar_objetivo", args=[objetivo.pk]))
        # 204 haría que HTMX no intercambiara nada y la fila seguiría en pantalla.
        self.assertEqual(r.status_code, 200)
        self.assertIn("objetivosActualizados", r["HX-Trigger"])
        objetivo.refresh_from_db()
        self.assertTrue(objetivo.eliminado)


class PresupuestoActividadTests(BaseProyectoTest):
    def setUp(self):
        super().setUp()
        self.objetivo = self.crear_objetivo(presupuesto_corriente=Decimal("300000"))
        self.resultado = self.crear_resultado(
            self.objetivo, presupuesto_corriente=Decimal("300000")
        )

    def test_formulario_no_impone_maximo_bloqueante(self):
        vacio = self.crear_resultado(self.objetivo, descripcion="Sin plata")
        html = self.client.get(
            reverse("proyectos:crear_actividad_form", args=[vacio.pk])
        ).content.decode()
        self.assertNotIn('max="0"', html)

    def test_los_montos_van_en_campos_de_texto(self):
        """Un `type="number"` vacía el campo al recibir "3.000.000".

        El separador de miles lo pone el JS de `base.html` mientras se escribe,
        y un input numérico descarta cualquier valor con dos puntos: por eso el
        monto se reiniciaba justo al pasar del millón.
        """
        html = self.client.get(
            reverse("proyectos:crear_actividad_form", args=[self.resultado.pk])
        ).content.decode()
        for campo in ("presupuesto_corriente", "presupuesto_capital"):
            with self.subTest(campo=campo):
                self.assertNotIn(f'type="number" name="{campo}"', html)
                self.assertIn(f'type="text" name="{campo}"', html)

    def test_se_puede_cargar_presupuesto_a_la_actividad(self):
        r = self.client.post(
            reverse("proyectos:crear_actividad", args=[self.resultado.pk]),
            {"nombre": "Taller", "presupuesto_corriente": "150000", "fecha_limite": ""},
        )
        self.assertEqual(r.status_code, 200)
        actividad = Actividad.objects.get()
        self.assertEqual(actividad.presupuesto, Decimal("150000"))

    def test_montos_en_millones_escritos_con_separador(self):
        """El caso reportado: 300 millones, tal como los deja la pantalla.

        El JS agrupa con puntos y Django con espacio duro; ambas formas tienen
        que entrar, porque el campo reenvía el texto que tenga a la vista.
        """
        grande = self.crear_resultado(
            self.objetivo,
            descripcion="Con plata",
            presupuesto_corriente=Decimal("300000000"),
            presupuesto_capital=Decimal("150000000"),
        )
        r = self.client.post(
            reverse("proyectos:crear_actividad", args=[grande.pk]),
            {
                "nombre": "Equipamiento",
                "presupuesto_corriente": "300.000.000",
                "presupuesto_capital": "150\xa0000\xa0000",
                "fecha_limite": "",
            },
        )
        self.assertEqual(r.status_code, 200, r.content.decode()[:300])
        actividad = Actividad.objects.get()
        self.assertEqual(actividad.presupuesto_corriente, Decimal("300000000"))
        self.assertEqual(actividad.presupuesto_capital, Decimal("150000000"))

        # Y al reabrirla, el monto vuelve agrupado y no como "300000000".
        html = self.client.get(
            reverse("proyectos:editar_actividad_form", args=[actividad.pk])
        ).content.decode()
        self.assertIn("300\xa0000\xa0000", html)

    def test_actividad_sin_monto_es_valida(self):
        r = self.client.post(
            reverse("proyectos:crear_actividad", args=[self.resultado.pk]),
            {"nombre": "Por definir", "presupuesto_corriente": "0", "fecha_limite": ""},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Actividad.objects.get().presupuesto, Decimal("0"))

    def test_exceso_devuelve_el_formulario_con_lo_escrito(self):
        r = self.client.post(
            reverse("proyectos:crear_actividad", args=[self.resultado.pk]),
            {"nombre": "Cara", "presupuesto_corriente": "999999999", "fecha_limite": ""},
        )
        self.assertEqual(r.status_code, 400)
        html = r.content.decode()
        self.assertIn("disponible", html.lower())
        self.assertIn("Cara", html)


class BorradoEnVivoTests(BaseProyectoTest):
    def setUp(self):
        super().setUp()
        self.objetivo = self.crear_objetivo(presupuesto_corriente=Decimal("300000"))
        self.resultado = self.crear_resultado(
            self.objetivo, presupuesto_corriente=Decimal("300000")
        )
        self.actividad = Actividad.objects.create(
            resultado=self.resultado, nombre="A", presupuesto_corriente=Decimal("1000")
        )

    def test_eliminar_resultado_dispara_refresco(self):
        r = self.client.delete(
            reverse("proyectos:eliminar_resultado", args=[self.resultado.pk])
        )
        self.assertEqual(r.status_code, 200)
        eventos = r["HX-Trigger"]
        self.assertIn("resultadosActualizados", eventos)
        self.assertIn("estructuraActualizada", eventos)

    def test_eliminar_actividad_dispara_refresco(self):
        r = self.client.delete(
            reverse("proyectos:eliminar_actividad", args=[self.actividad.pk])
        )
        self.assertEqual(r.status_code, 200)
        eventos = r["HX-Trigger"]
        self.assertIn("actividadActualizada", eventos)
        self.assertIn("resultadoActualizado", eventos)
        self.assertFalse(Actividad.objects.filter(pk=self.actividad.pk).exists())

    def test_fila_resultado_refleja_totales_al_dia(self):
        html = self.client.get(
            reverse("proyectos:fila_resultado", args=[self.resultado.pk])
        ).content.decode()
        self.assertIn(f'id="resultado-{self.resultado.pk}"', html)
        # Sólo la fila principal: la de actividades no debe venir duplicada.
        self.assertNotIn(f'id="actividades-row-{self.resultado.pk}"', html)


class OrdenTests(BaseProyectoTest):
    def setUp(self):
        super().setUp()
        self.o1 = self.crear_objetivo(descripcion="Primero", orden=1)
        self.o2 = self.crear_objetivo(descripcion="Segundo", orden=2)
        self.o3 = self.crear_objetivo(descripcion="Tercero", orden=3)

    def orden_actual(self):
        return list(self.proyecto.objetivos.values_list("descripcion", flat=True))

    def test_subir_intercambia_con_el_anterior(self):
        self.client.post(reverse("proyectos:mover_objetivo", args=[self.o3.pk, "subir"]))
        self.assertEqual(self.orden_actual(), ["Primero", "Tercero", "Segundo"])

    def test_bajar_intercambia_con_el_siguiente(self):
        self.client.post(reverse("proyectos:mover_objetivo", args=[self.o1.pk, "bajar"]))
        self.assertEqual(self.orden_actual(), ["Segundo", "Primero", "Tercero"])

    def test_en_los_extremos_no_pasa_nada(self):
        self.client.post(reverse("proyectos:mover_objetivo", args=[self.o1.pk, "subir"]))
        self.assertEqual(self.orden_actual(), ["Primero", "Segundo", "Tercero"])
        self.client.post(reverse("proyectos:mover_objetivo", args=[self.o3.pk, "bajar"]))
        self.assertEqual(self.orden_actual(), ["Primero", "Segundo", "Tercero"])

    def test_direccion_invalida_es_rechazada(self):
        r = self.client.post(reverse("proyectos:mover_objetivo", args=[self.o1.pk, "saltar"]))
        self.assertEqual(r.status_code, 400)

    def test_resultados_y_actividades_tambien_se_reordenan(self):
        r1 = self.crear_resultado(self.o1, descripcion="R1", orden=1)
        r2 = self.crear_resultado(self.o1, descripcion="R2", orden=2)
        self.client.post(reverse("proyectos:mover_resultado", args=[r2.pk, "subir"]))
        self.assertEqual(
            list(self.o1.resultados.values_list("descripcion", flat=True)), ["R2", "R1"]
        )

        a1 = Actividad.objects.create(resultado=r1, nombre="A1", orden=1)
        a2 = Actividad.objects.create(resultado=r1, nombre="A2", orden=2)
        self.client.post(reverse("proyectos:mover_actividad", args=[a2.pk, "subir"]))
        self.assertEqual(list(r1.actividades.values_list("nombre", flat=True)), ["A2", "A1"])
        self.assertEqual(a1.pk, r1.actividades.last().pk)

    def test_orden_repetido_se_normaliza(self):
        ObjetivoEspecifico.objects.update(orden=0)
        self.client.post(reverse("proyectos:mover_objetivo", args=[self.o1.pk, "bajar"]))
        ordenes = list(self.proyecto.objetivos.values_list("orden", flat=True))
        self.assertEqual(ordenes, [1, 2, 3])


class DetalleProyectoRenderTests(BaseProyectoTest):
    def test_la_pagina_de_detalle_se_arma_completa(self):
        objetivo = self.crear_objetivo(presupuesto_corriente=Decimal("100000"))
        resultado = self.crear_resultado(objetivo, presupuesto_corriente=Decimal("100000"))
        Actividad.objects.create(resultado=resultado, nombre="A", presupuesto_corriente=Decimal("500"))

        html = self.client.get(
            reverse("proyectos:detalle_proyecto", args=[self.proyecto.pk])
        ).content.decode()
        self.assertIn("contenedor-objetivos", html)
        self.assertIn(f'id="objetivo-{objetivo.pk}"', html)
        self.assertIn(f'id="resultado-{resultado.pk}"', html)
        self.assertIn("+ Objetivo", html)


class MontosConSeparadorTests(BaseProyectoTest):
    """El formato con que se muestra un monto tiene que poder volver a entrar.

    Con `USE_THOUSAND_SEPARATOR = True` y `LANGUAGE_CODE = 'es-cl'`, Django
    agrupa los miles con un espacio duro (U+00A0). El input del formulario
    reenvía ese texto tal cual —el JS que reformatea con puntos solo actúa sobre
    el campo que el usuario toca—, así que asignar un monto y después el otro
    devolvía «Formato numérico inválido».
    """

    def test_parser_acepta_todas_las_formas_de_escribir_un_monto(self):
        from .numeros import a_decimal

        equivalentes = [
            "50\xa0000\xa0000",   # lo que renderiza Django (espacio duro)
            "50 000 000",  # espacio duro estrecho
            "50 000 000",
            "50.000.000",         # lo que deja el JS de la pantalla
            "$50.000.000",
            "50000000",
        ]
        for texto in equivalentes:
            with self.subTest(texto=texto):
                self.assertEqual(a_decimal(texto), Decimal("50000000"))

        self.assertEqual(a_decimal("1.234.567,89"), Decimal("1234567.89"))
        self.assertEqual(a_decimal("1234.50"), Decimal("1234.50"))
        self.assertEqual(a_decimal(""), Decimal("0"))
        self.assertEqual(a_decimal(None), Decimal("0"))

    def test_asignar_corriente_y_despues_capital(self):
        objetivo = self.crear_objetivo()
        url = reverse("proyectos:editar_presupuesto_objetivo", args=[objetivo.pk])

        r = self.client.post(url, {
            "presupuesto_corriente": "500000",
            "presupuesto_capital": "0",
        })
        self.assertEqual(r.status_code, 200)

        # El formulario vuelve con el corriente ya formateado; el usuario solo
        # escribe el capital y reenvía el resto sin tocarlo.
        campos = self.client.get(url).content.decode()
        self.assertIn("\xa0", campos, "el input debería traer el separador de miles de Django")

        r = self.client.post(url, {
            "presupuesto_corriente": "500\xa0000",
            "presupuesto_capital": "300000",
        })
        self.assertEqual(r.status_code, 200, r.content.decode()[:200])

        objetivo.refresh_from_db()
        self.assertEqual(objetivo.presupuesto_corriente, Decimal("500000"))
        self.assertEqual(objetivo.presupuesto_capital, Decimal("300000"))

    def test_asignar_capital_y_despues_corriente(self):
        objetivo = self.crear_objetivo()
        url = reverse("proyectos:editar_presupuesto_objetivo", args=[objetivo.pk])

        self.client.post(url, {"presupuesto_corriente": "0", "presupuesto_capital": "400000"})
        r = self.client.post(url, {
            "presupuesto_corriente": "250000",
            "presupuesto_capital": "400\xa0000",
        })
        self.assertEqual(r.status_code, 200, r.content.decode()[:200])

        objetivo.refresh_from_db()
        self.assertEqual(objetivo.presupuesto_corriente, Decimal("250000"))
        self.assertEqual(objetivo.presupuesto_capital, Decimal("400000"))

    def test_los_topes_del_proyecto_se_siguen_respetando(self):
        objetivo = self.crear_objetivo()
        url = reverse("proyectos:editar_presupuesto_objetivo", args=[objetivo.pk])

        r = self.client.post(url, {
            "presupuesto_corriente": "999\xa0999\xa0999",
            "presupuesto_capital": "0",
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("Excede presupuesto corriente", r.content.decode())

        r = self.client.post(url, {"presupuesto_corriente": "no es un numero", "presupuesto_capital": "0"})
        self.assertEqual(r.status_code, 400)


class PresupuestoProyectoFormTests(BaseProyectoTest):
    """El modal de edición deja los montos en blanco y muestra el actual como
    placeholder, así que hay que ser explícito sobre qué falta y no descartar
    en silencio lo que el usuario sí escribió."""

    def _datos(self, **extra):
        datos = {
            "nombre": self.proyecto.nombre,
            "tipo": self.proyecto.tipo,
            "responsable": self.user.pk,
            "duracion_meses": self.proyecto.duracion_meses or 12,
            "prioridad": self.proyecto.prioridad,
            "estado": self.proyecto.estado,
        }
        datos.update(extra)
        return datos

    def test_un_solo_mensaje_cuando_no_cuadra(self):
        from .forms import ProyectoForm

        form = ProyectoForm(self._datos(
            presupuesto_total="1000000",
            presupuesto_corriente="600000",
            presupuesto_capital="300000",
        ), instance=self.proyecto)
        self.assertFalse(form.is_valid())
        # La regla vive en el form y en Proyecto.clean(): antes salía repetida.
        self.assertEqual(sum(len(v) for v in form.errors.values()), 1)

    def test_escribir_solo_el_total_no_se_descarta_en_silencio(self):
        from .forms import ProyectoForm

        form = ProyectoForm(self._datos(presupuesto_total="5000000"), instance=self.proyecto)
        self.assertFalse(form.is_valid(), "antes se guardaba sin el monto y avisaba «actualizado»")

    def test_dejar_todo_en_blanco_conserva_el_presupuesto(self):
        from .forms import ProyectoForm

        form = ProyectoForm(self._datos(
            presupuesto_total="", presupuesto_corriente="", presupuesto_capital="",
        ), instance=self.proyecto)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["presupuesto_corriente"], Decimal("600000"))


class CadenaDePresupuestoTests(BaseProyectoTest):
    """El presupuesto baja por proyecto → objetivo → resultado → actividad.

    Cada nivel reparte lo que recibió del de arriba. La pantalla de asignar
    presupuesto a un resultado consultaba el disponible del **proyecto**, que
    queda en $0 en cuanto se reparte todo entre los objetivos —el estado normal—,
    así que no dejaba asignar nada aunque el objetivo tuviera fondos.
    """

    def setUp(self):
        super().setUp()
        # Todo el presupuesto del proyecto se reparte entre dos objetivos:
        # el proyecto queda con $0 disponible.
        self.oe1 = self.crear_objetivo(
            presupuesto_corriente=Decimal("400000"), presupuesto_capital=Decimal("300000"))
        self.oe2 = self.crear_objetivo(
            presupuesto_corriente=Decimal("200000"), presupuesto_capital=Decimal("100000"))

    def _asignar(self, resultado, monto, tipo="COR"):
        """Deja el resultado en ese monto. El formulario edita ambos montos a la
        vez, así que se reenvía el otro tal como está para no pisarlo."""
        actual_cor = resultado.presupuesto_corriente
        actual_cap = resultado.presupuesto_capital
        datos = {
            "presupuesto_corriente": monto if tipo == "COR" else actual_cor,
            "presupuesto_capital": monto if tipo == "CAP" else actual_cap,
        }
        respuesta = self.client.post(
            reverse("proyectos:guardar_presupuesto", args=[resultado.pk]), datos
        )
        resultado.refresh_from_db()
        return respuesta

    def test_el_resultado_se_financia_del_objetivo_no_del_proyecto(self):
        self.assertEqual(self.proyecto.corriente_disponible, Decimal("0"),
                         "el proyecto ya repartió todo entre sus objetivos")

        resultado = self.crear_resultado(self.oe1)
        r = self._asignar(resultado, "300000")

        self.assertEqual(r.status_code, 200, r.content.decode()[:200])
        resultado.refresh_from_db()
        self.assertEqual(resultado.presupuesto_corriente, Decimal("300000"))

    def test_el_tope_es_lo_que_le_queda_al_objetivo(self):
        r1 = self.crear_resultado(self.oe1)
        r2 = self.crear_resultado(self.oe1)

        self.assertEqual(self._asignar(r1, "300000").status_code, 200)
        self.assertEqual(self._asignar(r2, "100000").status_code, 200)

        # OE1 ya repartió sus $400.000 entre r1 y r2: r2 no puede subir a
        # $150.000 porque con los $300.000 de r1 se pasaría del objetivo.
        rechazo = self._asignar(r2, "150000")
        self.assertEqual(rechazo.status_code, 400)
        self.assertIn("objetivo", rechazo.content.decode())

        self.oe1.refresh_from_db()
        self.assertEqual(self.oe1.corriente_disponible, Decimal("0"))

    def test_cada_objetivo_tiene_su_propia_bolsa(self):
        r1 = self.crear_resultado(self.oe1)
        r3 = self.crear_resultado(self.oe2)

        self.assertEqual(self._asignar(r1, "400000").status_code, 200)
        # OE1 quedó agotado, pero OE2 conserva lo suyo.
        self.assertEqual(self._asignar(r3, "200000").status_code, 200)
        self.assertEqual(self._asignar(r3, "210000").status_code, 400)

    def test_el_mensaje_dice_el_tope_y_en_cuanto_quedaria(self):
        resultado = self.crear_resultado(self.oe1)
        cuerpo = self._asignar(resultado, "600000").content.decode()

        self.assertIn("400,000", cuerpo)   # tope del objetivo
        self.assertIn("600,000", cuerpo)   # en cuánto quedaría

    def test_se_puede_bajar_el_presupuesto_de_un_resultado(self):
        """Antes solo se podía sumar: un monto puesto de más no había cómo
        corregirlo desde la pantalla."""
        resultado = self.crear_resultado(self.oe1)
        self._asignar(resultado, "300000")

        self.assertEqual(self._asignar(resultado, "120000").status_code, 200)
        self.assertEqual(resultado.presupuesto_corriente, Decimal("120000"))

        # Y hasta dejarlo en cero, devolviéndole el saldo al objetivo.
        self.assertEqual(self._asignar(resultado, "0").status_code, 200)
        self.oe1.refresh_from_db()
        self.assertEqual(self.oe1.corriente_disponible, Decimal("400000"))

    def test_no_se_puede_bajar_por_debajo_de_lo_repartido_a_actividades(self):
        resultado = self.crear_resultado(self.oe1)
        self._asignar(resultado, "300000")
        Actividad.objects.create(
            resultado=resultado, nombre="A", presupuesto_corriente=Decimal("250000"))

        rechazo = self._asignar(resultado, "100000")
        self.assertEqual(rechazo.status_code, 400)
        self.assertIn("250,000", rechazo.content.decode())
        self.assertEqual(resultado.presupuesto_corriente, Decimal("300000"))

    def test_la_pantalla_muestra_el_disponible_del_objetivo(self):
        resultado = self.crear_resultado(self.oe1)
        html = self.client.get(
            reverse("proyectos:form_asignar_presupuesto", args=[resultado.pk])
        ).content.decode()

        self.assertIn("Disponible en el objetivo", html)
        self.assertNotIn("Disponible en el proyecto", html)

    def test_la_actividad_se_financia_de_su_resultado(self):
        resultado = self.crear_resultado(self.oe1)
        self._asignar(resultado, "300000")
        resultado.refresh_from_db()

        actividad = Actividad(resultado=resultado, nombre="A1", presupuesto_corriente=Decimal("250000"))
        actividad.full_clean()
        actividad.save()

        excedida = Actividad(resultado=resultado, nombre="A2", presupuesto_corriente=Decimal("100000"))
        with self.assertRaises(ValidationError):
            excedida.full_clean()


class EdicionActividadTests(BaseProyectoTest):
    """La actividad solo permitía guardar el % de avance: nombre, montos y
    fechas quedaban fijos desde su creación."""

    def setUp(self):
        super().setUp()
        self.objetivo = self.crear_objetivo(
            presupuesto_corriente=Decimal("400000"), presupuesto_capital=Decimal("300000"))
        self.resultado = self.crear_resultado(
            self.objetivo,
            presupuesto_corriente=Decimal("300000"), presupuesto_capital=Decimal("200000"))
        self.actividad = Actividad.objects.create(
            resultado=self.resultado, nombre="Original",
            presupuesto_corriente=Decimal("100000"))

    def _editar(self, **campos):
        datos = {
            "nombre": "Original",
            "presupuesto_corriente": "100000",
            "presupuesto_capital": "0",
            "fecha_limite": "",
            "fecha_efectiva": "",
        }
        datos.update(campos)
        return self.client.post(
            reverse("proyectos:editar_actividad", args=[self.actividad.pk]), datos)

    def test_se_puede_cambiar_nombre_montos_y_fechas(self):
        r = self._editar(
            nombre="Renombrada",
            presupuesto_corriente="150000",
            presupuesto_capital="50000",
            fecha_limite="2026-09-30",
            fecha_efectiva="2026-10-05",
        )
        self.assertEqual(r.status_code, 200, r.content.decode()[:300])

        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.nombre, "Renombrada")
        self.assertEqual(self.actividad.presupuesto_corriente, Decimal("150000"))
        self.assertEqual(self.actividad.presupuesto_capital, Decimal("50000"))
        self.assertEqual(str(self.actividad.fecha_limite), "2026-09-30")
        self.assertEqual(str(self.actividad.fecha_efectiva), "2026-10-05")

    def test_se_puede_bajar_el_monto(self):
        self._editar(presupuesto_corriente="20000")
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.presupuesto_corriente, Decimal("20000"))

    def test_el_formulario_de_edicion_llega_con_los_valores_actuales(self):
        self.actividad.fecha_limite = date(2026, 9, 30)
        self.actividad.save()

        html = self.client.get(
            reverse("proyectos:editar_actividad_form", args=[self.actividad.pk])
        ).content.decode()

        self.assertIn("Editar actividad", html)
        # Agrupado, igual que los montos del objetivo y del resultado.
        self.assertIn('value="100\xa0000"', html)
        self.assertIn('value="2026-09-30"', html)

    def test_su_propio_monto_no_cuenta_como_ocupado_al_editar(self):
        # El resultado tiene 300.000 y la actividad ya usa 100.000: debe poder
        # subir a 300.000 sin que su propio monto se cuente dos veces.
        r = self._editar(presupuesto_corriente="300000")
        self.assertEqual(r.status_code, 200, r.content.decode()[:300])

    def test_no_puede_exceder_la_bolsa_del_resultado(self):
        r = self._editar(presupuesto_corriente="400000")
        self.assertEqual(r.status_code, 400)
        self.assertIn("corriente", r.content.decode())

    def test_capital_y_corriente_son_bolsas_separadas(self):
        # El resultado tiene 200.000 de capital: pedir 250.000 no cabe aunque
        # sobre corriente.
        r = self._editar(presupuesto_corriente="0", presupuesto_capital="250000")
        self.assertEqual(r.status_code, 400)
        self.assertIn("capital", r.content.decode())


class FechaEfectivaTests(BaseProyectoTest):
    def setUp(self):
        super().setUp()
        objetivo = self.crear_objetivo(presupuesto_corriente=Decimal("100000"))
        self.resultado = self.crear_resultado(objetivo, presupuesto_corriente=Decimal("100000"))

    def _actividad(self, limite, efectiva):
        return Actividad.objects.create(
            resultado=self.resultado, nombre="A",
            fecha_limite=limite, fecha_efectiva=efectiva)

    def test_desviacion_positiva_cuando_termina_tarde(self):
        a = self._actividad(date(2026, 8, 12), date(2026, 8, 20))
        self.assertEqual(a.desviacion_dias, 8)
        self.assertFalse(a.cerrada_a_tiempo)

    def test_desviacion_negativa_cuando_termina_antes(self):
        a = self._actividad(date(2026, 9, 30), date(2026, 9, 28))
        self.assertEqual(a.desviacion_dias, -2)
        self.assertTrue(a.cerrada_a_tiempo)

    def test_sin_fecha_efectiva_no_hay_desviacion(self):
        a = self._actividad(date(2026, 10, 15), None)
        self.assertIsNone(a.desviacion_dias)
        self.assertIsNone(a.cerrada_a_tiempo)


class PlanDeGastoTests(BaseProyectoTest):
    def setUp(self):
        super().setUp()
        objetivo = self.crear_objetivo(presupuesto_corriente=Decimal("500000"))
        self.resultado = self.crear_resultado(objetivo, presupuesto_corriente=Decimal("500000"))
        self.actividad = Actividad.objects.create(
            resultado=self.resultado, nombre="A", presupuesto_corriente=Decimal("400000"))

    def test_la_seccion_del_proyecto_ofrece_el_boton_para_agregar(self):
        """Faltaba el botón: el formulario existía pero no había cómo abrirlo.
        Vive en «Planes de gasto del proyecto», que es donde se administran."""
        html = self.client.get(
            reverse("proyectos:listar_planes_gasto", args=[self.proyecto.pk])
        ).content.decode()

        self.assertIn("Plan de gasto", html)
        self.assertIn(
            reverse("proyectos:crear_plan_gasto_form", args=[self.proyecto.pk]),
            html,
        )

    def test_el_boton_no_aparece_para_quien_no_es_responsable(self):
        otro = User.objects.create_user("mirona", password="x")
        self.client.force_login(otro)
        html = self.client.get(
            reverse("proyectos:listar_planes_gasto", args=[self.proyecto.pk])
        ).content.decode()

        self.assertNotIn(
            reverse("proyectos:crear_plan_gasto_form", args=[self.proyecto.pk]),
            html,
        )

    def test_el_formulario_llega_con_la_actividad_elegida(self):
        url = reverse("proyectos:crear_plan_gasto_form",
                      args=[self.resultado.objetivo.proyecto_id])
        html = self.client.get(f"{url}?actividad={self.actividad.pk}").content.decode()

        self.assertIn("Nuevo plan de gasto", html)
        # Los tres selects encadenados llegan resueltos, no vacíos esperando
        # que se recorra otra vez objetivo → resultado → actividad.
        compacto = " ".join(html.split())
        self.assertIn(f'<option value="{self.actividad.pk}" selected>', compacto)
        self.assertIn(f'<option value="{self.resultado.pk}" selected>', compacto)
        self.assertIn(f'<option value="{self.resultado.objetivo_id}" selected>', compacto)


# ===========================================================================
# GASTOS: documentos del trámite y ejecución del resultado
# ===========================================================================

class BaseGastosTest(BaseProyectoTest):
    """Un resultado con presupuesto en las dos bolsas y un plan de gasto en cada
    una, que es el mínimo para poder cargarle gastos."""

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
            nombre="Actividad",
            presupuesto_corriente=Decimal("600000"),
            presupuesto_capital=Decimal("400000"),
        )
        # El catálogo lo siembra la migración 0007, con «Corriente» y «Capital»
        # como transferencias.
        self.elegible_corriente = GastoElegible.objects.filter(
            gasto__tipo_gasto__transferencia__naturaleza=CORRIENTE
        ).first()
        self.elegible_capital = GastoElegible.objects.filter(
            gasto__tipo_gasto__transferencia__naturaleza=CAPITAL
        ).first()
        self.plan_corriente = PlanDeGasto.objects.create(
            actividad=self.actividad,
            gasto_elegible=self.elegible_corriente,
            anio=2026,
            monto=Decimal("600000"),
        )
        self.plan_capital = PlanDeGasto.objects.create(
            actividad=self.actividad,
            gasto_elegible=self.elegible_capital,
            anio=2026,
            monto=Decimal("400000"),
        )

    def compra(self, plan=None, estado=Egreso.ESTADO_COMPROMETIDO, neto="100000", **extra):
        """Una compra por `neto` sin IVA (el total queda 19% arriba)."""
        datos = {
            "proyecto": self.proyecto,
            "tipo": Egreso.TIPO_COMPRA,
            "subtipo_compra": Egreso.SUB_BIENES_INSUMOS,
            "estado": estado,
            "plan_de_gasto": plan or self.plan_corriente,
            "gasto_elegible": (plan or self.plan_corriente).gasto_elegible,
            "cantidad": 1,
            "valor_sin_iva": Decimal(neto),
        }
        datos.update(extra)
        return Egreso.objects.create(**datos)


class EjecucionDelResultadoTests(BaseGastosTest):
    """El defecto reportado: un gasto marcado «Pagado» no aparecía en el
    ejecutado del resultado. La causa era que el resultado leía la columna
    `PlanDeGasto.ejecutado`, que ningún formulario escribía nunca."""

    def test_un_gasto_pagado_aparece_en_el_ejecutado(self):
        self.compra(estado=Egreso.ESTADO_PAGADO, neto="100000")
        self.assertEqual(self.resultado.ejecutado, Decimal("119000"))

    def test_un_gasto_comprometido_no_cuenta_como_ejecutado(self):
        self.compra(estado=Egreso.ESTADO_COMPROMETIDO, neto="100000")
        self.assertEqual(self.resultado.ejecutado, Decimal("0"))
        self.assertEqual(self.resultado.comprometido, Decimal("119000"))

    def test_el_saldo_descuenta_lo_pagado_y_lo_comprometido(self):
        self.compra(estado=Egreso.ESTADO_PAGADO, neto="100000")
        self.compra(estado=Egreso.ESTADO_COMPROMETIDO, neto="200000")
        # 1.000.000 − 119.000 − 238.000
        self.assertEqual(self.resultado.saldo, Decimal("643000"))

    def test_un_gasto_eliminado_deja_de_contar(self):
        gasto = self.compra(estado=Egreso.ESTADO_PAGADO)
        gasto.soft_delete()
        self.assertEqual(Resultado.objects.get(pk=self.resultado.pk).ejecutado,
                         Decimal("0"))

    def test_los_gastos_de_otro_resultado_no_se_mezclan(self):
        otro_objetivo = self.crear_objetivo(presupuesto_corriente=Decimal("0"))
        otro = self.crear_resultado(otro_objetivo, descripcion="Otro")
        self.compra(estado=Egreso.ESTADO_PAGADO)
        self.assertEqual(otro.ejecutado, Decimal("0"))

    def test_un_honorario_a_medio_pagar_se_reparte(self):
        """Las cuotas ya pagadas son ejecutado; las que faltan siguen tomadas."""
        Egreso.objects.create(
            proyecto=self.proyecto,
            tipo=Egreso.TIPO_HONORARIO,
            estado=Egreso.ESTADO_COMPROMETIDO,
            plan_de_gasto=self.plan_corriente,
            gasto_elegible=self.plan_corriente.gasto_elegible,
            nombre_persona="Ana", apellido_persona="Pérez",
            meses=4, cuota_mensual=Decimal("50000"),
            monto_total=Decimal("200000"), cuotas_pagadas=3,
        )
        self.assertEqual(self.resultado.ejecutado, Decimal("150000"))
        self.assertEqual(self.resultado.comprometido, Decimal("50000"))

    def test_el_resumen_por_tipo_cuenta_los_honorarios(self):
        """Sumaba cantidad × valor unitario, columnas que un honorario no usa:
        un contrato de millones aparecía como «Honorario: $0»."""
        Egreso.objects.create(
            proyecto=self.proyecto,
            tipo=Egreso.TIPO_HONORARIO,
            plan_de_gasto=self.plan_corriente,
            gasto_elegible=self.plan_corriente.gasto_elegible,
            nombre_persona="Ana", apellido_persona="Pérez",
            meses=4, cuota_mensual=Decimal("50000"),
            monto_total=Decimal("200000"),
        )
        html = self.client.get(
            reverse("proyectos:listar_egresos", args=[self.proyecto.pk])
        ).content.decode()
        compacto = " ".join(html.split())

        self.assertIn("Honorario: <strong>$200 000</strong>", compacto)

    def test_la_fila_del_resultado_muestra_lo_ejecutado(self):
        self.compra(estado=Egreso.ESTADO_PAGADO, neto="100000")
        html = self.client.get(
            reverse("proyectos:fila_resultado", args=[self.resultado.pk])
        ).content.decode()
        # El locale es-CL de Django separa los miles con espacio duro.
        self.assertIn("119 000", html)

    def test_la_lista_de_resultados_se_recarga_al_cargar_un_gasto(self):
        """Si la sección no escucha el evento, el número correcto queda escrito
        pero en pantalla sigue el viejo hasta apretar F5."""
        html = self.client.get(
            reverse("proyectos:detalle_proyecto", args=[self.proyecto.pk])
        ).content.decode()
        self.assertIn("egresoUpdated from:body", html)


class BolsasDelResultadoTests(BaseGastosTest):
    """Corriente y capital son bolsas separadas: gastar de una no puede
    aparecer descontando de la otra."""

    def test_cada_gasto_cae_en_la_bolsa_de_su_transferencia(self):
        self.compra(plan=self.plan_corriente, estado=Egreso.ESTADO_PAGADO, neto="100000")
        self.compra(plan=self.plan_capital, estado=Egreso.ESTADO_PAGADO, neto="200000")

        self.assertEqual(self.resultado.ejecutado_corriente, Decimal("119000"))
        self.assertEqual(self.resultado.ejecutado_capital, Decimal("238000"))
        self.assertEqual(self.resultado.ejecutado, Decimal("357000"))

    def test_el_saldo_de_cada_bolsa_sale_de_su_propio_presupuesto(self):
        self.compra(plan=self.plan_capital, estado=Egreso.ESTADO_PAGADO, neto="200000")

        self.assertEqual(self.resultado.saldo_corriente, Decimal("600000"))
        self.assertEqual(self.resultado.saldo_capital, Decimal("162000"))

    def test_una_bolsa_en_rojo_no_se_esconde_tras_el_total(self):
        """Justo el caso que motivó el desglose: el total sigue en verde."""
        self.compra(plan=self.plan_capital, estado=Egreso.ESTADO_PAGADO, neto="400000")

        self.assertGreater(self.resultado.saldo, 0)
        self.assertLess(self.resultado.saldo_capital, 0)

    def test_la_fila_del_resultado_desglosa_las_dos_bolsas(self):
        self.compra(plan=self.plan_corriente, estado=Egreso.ESTADO_PAGADO, neto="100000")
        self.compra(plan=self.plan_capital, estado=Egreso.ESTADO_PAGADO, neto="200000")
        html = self.client.get(
            reverse("proyectos:fila_resultado", args=[self.resultado.pk])
        ).content.decode()
        compacto = " ".join(html.split())
        # compacto ya normalizó el espacio duro del separador de miles.
        self.assertIn("C $119 000", compacto)
        self.assertIn("K $238 000", compacto)

    def test_con_una_sola_bolsa_se_nombra_en_vez_de_repetir_ceros(self):
        self.compra(plan=self.plan_capital, estado=Egreso.ESTADO_PAGADO, neto="200000")
        html = self.client.get(
            reverse("proyectos:fila_resultado", args=[self.resultado.pk])
        ).content.decode()
        self.assertIn("capital", html)
        self.assertNotIn("C $0", html)

    def test_el_detalle_muestra_las_cuatro_cifras_desglosadas(self):
        self.compra(plan=self.plan_corriente, estado=Egreso.ESTADO_PAGADO, neto="100000")
        html = self.client.get(
            reverse("proyectos:detalle_presupuesto_resultado", args=[self.resultado.pk])
        ).content.decode()
        for etiqueta in ("Presupuesto", "Comprometido", "Ejecutado", "Saldo"):
            self.assertIn(etiqueta, html)
        self.assertEqual(html.count("Corriente"), 4)
        self.assertEqual(html.count("Capital"), 4)


class DocumentosDelGastoTests(BaseGastosTest):
    """SC, OC y factura: los folios del trámite del gasto."""

    def _datos_compra(self, **extra):
        datos = {
            "tipo": Egreso.TIPO_COMPRA,
            "subtipo_compra": Egreso.SUB_BIENES_INSUMOS,
            "estado": Egreso.ESTADO_COMPROMETIDO,
            "centro_responsabilidad": "12345",
            "gasto_elegible": self.elegible_corriente.pk,
            "plan_de_gasto": self.plan_corriente.pk,
            "cantidad": 1,
            "valor_sin_iva": "100000",
        }
        datos.update(extra)
        return datos

    def test_se_guardan_al_crear_el_gasto(self):
        r = self.client.post(
            reverse("proyectos:crear_egreso", args=[self.proyecto.pk]),
            self._datos_compra(solicitud_compra="SC-100",
                               orden_compra="OC-200",
                               factura="F-300"),
        )
        self.assertEqual(r.status_code, 200)
        gasto = Egreso.objects.get()
        self.assertEqual(gasto.solicitud_compra, "SC-100")
        self.assertEqual(gasto.orden_compra, "OC-200")
        self.assertEqual(gasto.factura, "F-300")

    def test_son_opcionales_y_se_completan_despues(self):
        """Casi nunca están los tres el día que se registra el gasto."""
        self.client.post(
            reverse("proyectos:crear_egreso", args=[self.proyecto.pk]),
            self._datos_compra(solicitud_compra="SC-100"),
        )
        gasto = Egreso.objects.get()
        self.assertEqual(gasto.orden_compra, "")
        self.assertEqual([s for s, _ in gasto.documentos], ["SC"])

        self.client.post(
            reverse("proyectos:editar_egreso", args=[gasto.pk]),
            self._datos_compra(solicitud_compra="SC-100", orden_compra="OC-200"),
        )
        gasto.refresh_from_db()
        self.assertEqual([s for s, _ in gasto.documentos], ["SC", "OC"])

    def test_el_formulario_de_edicion_llega_con_los_folios(self):
        gasto = self.compra(solicitud_compra="SC-100", factura="F-300")
        html = self.client.get(
            reverse("proyectos:editar_egreso_form", args=[gasto.pk])
        ).content.decode()
        self.assertIn('name="solicitud_compra"', html)
        self.assertIn('value="SC-100"', html)
        self.assertIn('value="F-300"', html)

    def test_la_lista_de_gastos_los_muestra(self):
        self.compra(solicitud_compra="SC-100", orden_compra="OC-200")
        html = self.client.get(
            reverse("proyectos:listar_egresos", args=[self.proyecto.pk])
        ).content.decode()
        self.assertIn("SC SC-100", " ".join(html.split()))
        self.assertIn("OC OC-200", " ".join(html.split()))

    def test_un_gasto_sin_folios_no_ensucia_la_lista(self):
        self.compra()
        html = self.client.get(
            reverse("proyectos:listar_egresos", args=[self.proyecto.pk])
        ).content.decode()
        self.assertNotIn("SC ", html)

    def test_aparecen_en_los_movimientos_del_resultado(self):
        self.compra(estado=Egreso.ESTADO_PAGADO, factura="F-300")
        html = self.client.get(
            reverse("proyectos:detalle_presupuesto_resultado", args=[self.resultado.pk])
        ).content.decode()
        self.assertIn("Factura F-300", " ".join(html.split()))


class PlanDeGastoEjecutadoTests(BaseGastosTest):
    """El plan también leía la columna muerta; ahora suma sus propios gastos."""

    def test_el_plan_suma_los_gastos_que_tiene_cargados(self):
        self.compra(plan=self.plan_corriente, estado=Egreso.ESTADO_PAGADO, neto="100000")
        self.compra(plan=self.plan_corriente, estado=Egreso.ESTADO_COMPROMETIDO, neto="50000")
        plan = PlanDeGasto.objects.get(pk=self.plan_corriente.pk)

        self.assertEqual(plan.ejecutado, Decimal("119000"))
        self.assertEqual(plan.comprometido, Decimal("59500"))
        self.assertEqual(plan.saldo, Decimal("421500"))

    def test_el_gasto_de_otro_plan_no_le_cuenta(self):
        self.compra(plan=self.plan_capital, estado=Egreso.ESTADO_PAGADO)
        self.assertEqual(
            PlanDeGasto.objects.get(pk=self.plan_corriente.pk).ejecutado, Decimal("0")
        )

    def test_el_proyecto_suma_lo_mismo_que_sus_resultados(self):
        self.compra(plan=self.plan_corriente, estado=Egreso.ESTADO_PAGADO, neto="100000")
        self.compra(plan=self.plan_capital, estado=Egreso.ESTADO_COMPROMETIDO, neto="200000")
        proyecto = Proyecto.objects.get(pk=self.proyecto.pk)

        self.assertEqual(proyecto.gastos_pagados, self.resultado.ejecutado)
        self.assertEqual(proyecto.gastos_comprometidos, self.resultado.comprometido)
        self.assertEqual(proyecto.gastos_capital, Decimal("238000"))


class CupoDelPlanTests(BaseGastosTest):
    """Un gasto no puede pasarse del plan al que se carga.

    Se podía cargar $15.300.000 a un plan de $15.000.000: el sistema lo
    aceptaba y recién después mostraba el disponible en rojo.
    """

    def setUp(self):
        super().setUp()
        # Un plan redondo para que los montos del mensaje se lean solos.
        self.plan_corriente.monto = Decimal("15000000")
        self.plan_corriente.save(update_fields=["monto"])

    def _postear(self, neto, cantidad=1, **extra):
        datos = {
            "tipo": Egreso.TIPO_COMPRA,
            "subtipo_compra": Egreso.SUB_BIENES_INSUMOS,
            "estado": Egreso.ESTADO_COMPROMETIDO,
            "centro_responsabilidad": "12345",
            "gasto_elegible": self.plan_corriente.gasto_elegible_id,
            "plan_de_gasto": self.plan_corriente.pk,
            "cantidad": cantidad,
            "valor_sin_iva": str(neto),
        }
        datos.update(extra)
        return self.client.post(
            reverse("proyectos:crear_egreso", args=[self.proyecto.pk]), datos
        )

    def test_no_deja_cargar_un_gasto_mayor_que_el_plan(self):
        r = self._postear("15300000")

        self.assertEqual(r.status_code, 400)
        self.assertFalse(Egreso.objects.exists())

    def test_el_aviso_dice_cuanto_cabe(self):
        html = self._postear("15300000").content.decode()
        compacto = " ".join(html.split())

        # Con IVA son $18.207.000 contra $15.000.000 disponibles.
        self.assertIn("$18.207.000", compacto)
        self.assertIn("$15.000.000", compacto)

    def test_el_formulario_vuelve_con_lo_escrito(self):
        """El aviso no sirve de nada si borra lo que se acababa de escribir."""
        html = self._postear("15300000", cantidad=1,
                             solicitud_compra="SC-77").content.decode()

        self.assertIn('name="valor_sin_iva"', html)
        self.assertIn('value="15300000"', html)
        self.assertIn('value="SC-77"', html)
        # Y sigue siendo un alta, no se convierte en edición de un gasto que no existe.
        self.assertIn(reverse("proyectos:crear_egreso", args=[self.proyecto.pk]), html)

    def test_lo_que_cabe_justo_se_acepta(self):
        # 12.605.042 × 1,19 = 14.999.999,98 — entra por dos centavos.
        r = self._postear("12605042")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(Egreso.objects.count(), 1)

    def test_los_gastos_ya_cargados_ocupan_cupo(self):
        """Cada uno cabe por separado ($8.330.000 con IVA); los dos juntos no."""
        self.assertEqual(self._postear("7000000").status_code, 200)
        r = self._postear("7000000")

        self.assertEqual(r.status_code, 400)
        self.assertEqual(Egreso.objects.count(), 1)

    def test_editar_un_gasto_no_lo_cuenta_contra_si_mismo(self):
        self._postear("12000000")
        gasto = Egreso.objects.get()

        r = self.client.post(
            reverse("proyectos:editar_egreso", args=[gasto.pk]),
            {
                "tipo": Egreso.TIPO_COMPRA,
                "subtipo_compra": Egreso.SUB_BIENES_INSUMOS,
                "estado": Egreso.ESTADO_PAGADO,
                "centro_responsabilidad": "12345",
                "gasto_elegible": self.plan_corriente.gasto_elegible_id,
                "plan_de_gasto": self.plan_corriente.pk,
                "cantidad": 1,
                "valor_sin_iva": "12000000",
            },
        )

        self.assertEqual(r.status_code, 200)
        gasto.refresh_from_db()
        self.assertEqual(gasto.estado, Egreso.ESTADO_PAGADO)

    def test_un_gasto_eliminado_libera_el_cupo(self):
        self._postear("12000000")
        Egreso.objects.get().soft_delete()

        self.assertEqual(self._postear("12000000").status_code, 200)

    def test_el_honorario_tambien_esta_topado(self):
        r = self.client.post(
            reverse("proyectos:crear_egreso", args=[self.proyecto.pk]),
            {
                "tipo": Egreso.TIPO_HONORARIO,
                "estado": Egreso.ESTADO_COMPROMETIDO,
                "centro_responsabilidad": "12345",
                "gasto_elegible": self.plan_corriente.gasto_elegible_id,
                "plan_de_gasto": self.plan_corriente.pk,
                "nombre_persona": "Ana", "apellido_persona": "Pérez",
                "meses": 12, "cuota_mensual": "1500000",
                "monto_total": "18000000",
            },
        )

        self.assertEqual(r.status_code, 400)
        self.assertFalse(Egreso.objects.exists())

    def test_el_selector_de_planes_muestra_lo_que_queda(self):
        self._postear("6000000")
        url = reverse("proyectos:egreso_planes_por_elegible", args=[self.proyecto.pk])
        html = self.client.get(
            f"{url}?gasto_elegible={self.plan_corriente.gasto_elegible_id}"
        ).content.decode()

        self.assertIn("quedan $7 860 000", " ".join(html.split()))


class GastoYaPasadoTests(BaseGastosTest):
    """Los gastos cargados antes de que existiera el tope.

    El tope no puede dejarlos congelados: cualquier guardado volvía a chocar
    contra él, así que no había forma de corregirlos ni de anotarles la factura.
    """

    def setUp(self):
        super().setUp()
        self.plan_corriente.monto = Decimal("15000000")
        self.plan_corriente.save(update_fields=["monto"])
        # $17.850.000 con IVA en un plan de $15.000.000.
        self.gasto = self.compra(neto="15000000")

    def _editar(self, neto, **extra):
        datos = {
            "tipo": Egreso.TIPO_COMPRA,
            "subtipo_compra": Egreso.SUB_BIENES_INSUMOS,
            "estado": Egreso.ESTADO_COMPROMETIDO,
            "centro_responsabilidad": "12345",
            "gasto_elegible": self.plan_corriente.gasto_elegible_id,
            "plan_de_gasto": self.plan_corriente.pk,
            "cantidad": 1,
            "valor_sin_iva": str(neto),
        }
        datos.update(extra)
        return self.client.post(
            reverse("proyectos:editar_egreso", args=[self.gasto.pk]), datos
        )

    def test_se_puede_seguir_editando_sin_cambiar_el_monto(self):
        r = self._editar("15000000", factura="F-300")

        self.assertEqual(r.status_code, 200)
        self.gasto.refresh_from_db()
        self.assertEqual(self.gasto.factura, "F-300")

    def test_bajarlo_se_puede_aunque_siga_pasado(self):
        r = self._editar("14000000")

        self.assertEqual(r.status_code, 200)
        self.gasto.refresh_from_db()
        self.assertEqual(self.gasto.valor_sin_iva, Decimal("14000000"))

    def test_pero_no_se_puede_aumentar(self):
        r = self._editar("16000000")

        self.assertEqual(r.status_code, 400)
        self.gasto.refresh_from_db()
        self.assertEqual(self.gasto.valor_sin_iva, Decimal("15000000"))

    def test_tampoco_se_puede_mudar_a_otro_plan_que_no_lo_aguanta(self):
        self.plan_capital.monto = Decimal("1000000")
        self.plan_capital.save(update_fields=["monto"])

        r = self._editar(
            "15000000",
            gasto_elegible=self.plan_capital.gasto_elegible_id,
            plan_de_gasto=self.plan_capital.pk,
        )

        self.assertEqual(r.status_code, 400)

    def test_el_elegible_actual_no_se_pierde_al_editar(self):
        """Si el filtro por subtipo no alcanza al elegible que el gasto ya
        tiene, el <select> volvía sin nada marcado y al guardar se perdía."""
        ajeno = GastoElegible.objects.exclude(
            gasto__nombre__iexact="Bienes"
        ).first()
        Egreso.all_objects.filter(pk=self.gasto.pk).update(
            gasto_elegible=ajeno, gasto=ajeno.gasto
        )

        html = self.client.get(
            reverse("proyectos:editar_egreso_form", args=[self.gasto.pk])
        ).content.decode()

        self.assertIn(f'<option value="{ajeno.pk}" selected>',
                      " ".join(html.split()))


class HonorarioTests(BaseGastosTest):
    """Contratos por cuotas: el total casi nunca se divide en pesos enteros.

    Exigir que meses × cuota fuera exactamente el total hacía imposible guardar
    $5.000.000 en 6 meses, y dejaba congelado —sin poder anotarle ni la
    factura— cualquier honorario que ya estuviera guardado así.
    """

    def setUp(self):
        super().setUp()
        self.elegible_honorarios = GastoElegible.objects.get(nombre__iexact="Honorarios")
        # El plan del catálogo corriente puede ser ya el de honorarios.
        self.plan, _ = PlanDeGasto.objects.get_or_create(
            actividad=self.actividad,
            gasto_elegible=self.elegible_honorarios,
            anio=2026,
            defaults={"monto": Decimal("20000000")},
        )
        self.plan.monto = Decimal("20000000")
        self.plan.save(update_fields=["monto"])

    def _datos(self, **extra):
        datos = {
            "tipo": Egreso.TIPO_HONORARIO,
            "estado": Egreso.ESTADO_COMPROMETIDO,
            "centro_responsabilidad": "12345",
            "gasto_elegible": self.elegible_honorarios.pk,
            "plan_de_gasto": self.plan.pk,
            "nombre_persona": "Ana",
            "apellido_persona": "Pérez",
            "meses": "6",
            "cuota_mensual": "900000",
            "monto_total": "5400000",
        }
        datos.update(extra)
        return datos

    def _crear(self, **extra):
        return self.client.post(
            reverse("proyectos:crear_egreso", args=[self.proyecto.pk]),
            self._datos(**extra),
        )

    def _honorario(self, **campos):
        datos = {
            "proyecto": self.proyecto,
            "tipo": Egreso.TIPO_HONORARIO,
            "estado": Egreso.ESTADO_COMPROMETIDO,
            "plan_de_gasto": self.plan,
            "gasto_elegible": self.elegible_honorarios,
            "nombre_persona": "Ana",
            "apellido_persona": "Pérez",
            "meses": 6,
            "cuota_mensual": Decimal("833333"),
            "monto_total": Decimal("5000000"),
        }
        datos.update(campos)
        return Egreso.objects.create(**datos)

    # --- El monto que no divide ---

    def test_un_total_que_no_da_cuotas_enteras_se_puede_guardar(self):
        """$5.000.000 en 6 meses son $833.333,33: la cuota se redondea."""
        r = self._crear(cuota_mensual="833333", monto_total="5000000")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(Egreso.objects.get().monto_total, Decimal("5000000"))

    def test_se_puede_subir_y_bajar_el_monto(self):
        self._crear()
        honorario = Egreso.objects.get()
        url = reverse("proyectos:editar_egreso", args=[honorario.pk])

        for total, cuota in (("5000000", "833333"), ("7000000", "1166667")):
            with self.subTest(total=total):
                r = self.client.post(
                    url, self._datos(monto_total=total, cuota_mensual=cuota))
                self.assertEqual(r.status_code, 200)
                honorario.refresh_from_db()
                self.assertEqual(honorario.monto_total, Decimal(total))

    def test_el_total_se_guarda_aunque_no_cuadre_con_las_cuotas(self):
        """El contrato se anota como sea: lo que pesa contra el presupuesto es
        el monto total, y ése es el que tiene techo."""
        r = self._crear(monto_total="9000000", cuota_mensual="900000", meses="6")

        self.assertEqual(r.status_code, 200)
        honorario = Egreso.objects.get()
        self.assertEqual(honorario.monto_total, Decimal("9000000"))
        self.assertEqual(honorario.montos[0], Decimal("9000000"))

    def test_un_honorario_descuadrado_se_puede_seguir_editando(self):
        honorario = self._honorario()

        r = self.client.post(
            reverse("proyectos:editar_egreso", args=[honorario.pk]),
            self._datos(cuota_mensual="833333", monto_total="5000000",
                        solicitud_compra="SC-99", factura="F-300"),
        )

        self.assertEqual(r.status_code, 200)
        honorario.refresh_from_db()
        self.assertEqual(honorario.solicitud_compra, "SC-99")
        self.assertEqual(honorario.factura, "F-300")

    # --- Lo pagado y lo pendiente cuadran con el total ---

    def test_pagado_y_pendiente_suman_el_total(self):
        honorario = self._honorario(cuotas_pagadas=3)

        self.assertEqual(
            honorario.monto_pagado_honorario + honorario.monto_pendiente_honorario,
            honorario.monto_total,
        )

    def test_la_ultima_cuota_cierra_el_contrato(self):
        """Con cuotas redondeadas, 6 × 833.333 se queda a $2 del total."""
        honorario = self._honorario(cuotas_pagadas=6)

        self.assertEqual(honorario.monto_pagado_honorario, Decimal("5000000"))
        self.assertEqual(honorario.monto_pendiente_honorario, Decimal("0"))

    def test_el_resultado_no_hereda_esos_pesos_sueltos(self):
        self._honorario(cuotas_pagadas=6, estado=Egreso.ESTADO_PAGADO)

        self.assertEqual(self.resultado.ejecutado, Decimal("5000000"))
        self.assertEqual(self.resultado.comprometido, Decimal("0"))

    # --- El honorario sin gasto elegible ---

    def test_un_honorario_sin_elegible_no_pierde_su_plan(self):
        """El modelo sólo le exige el plan. Sin elegible, el <select> de plan
        se dibujaba deshabilitado: no viajaba al guardar y el gasto se rechazaba
        por no tener plan."""
        honorario = self._honorario(gasto_elegible=None)

        html = self.client.get(
            reverse("proyectos:editar_egreso_form", args=[honorario.pk])
        ).content.decode()
        compacto = " ".join(html.split())

        self.assertIn(f'<option value="{self.plan.pk}" selected>', compacto)
        self.assertNotIn("Seleccione primero un gasto elegible", compacto)


class EdicionLibreTests(BaseGastosTest):
    """Los datos del gasto se guardan como se escriban.

    El único bloqueo es el tope de lo disponible en el plan (CupoDelPlanTests);
    el resto de las reglas sólo dejaba gastos imposibles de editar.
    """

    def _crear(self, **extra):
        datos = {
            "tipo": Egreso.TIPO_COMPRA,
            "estado": Egreso.ESTADO_COMPROMETIDO,
            "gasto_elegible": self.plan_corriente.gasto_elegible_id,
            "plan_de_gasto": self.plan_corriente.pk,
            "cantidad": "1",
            "valor_sin_iva": "100000",
        }
        datos.update(extra)
        return self.client.post(
            reverse("proyectos:crear_egreso", args=[self.proyecto.pk]), datos
        )

    def test_una_compra_sin_subtipo_ni_centro_se_guarda(self):
        r = self._crear(subtipo_compra="", centro_responsabilidad="")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(Egreso.objects.count(), 1)

    def test_una_compra_en_cero_se_guarda(self):
        """Sirve para dejar anotado un gasto cuyo monto todavía no se sabe."""
        r = self._crear(cantidad="0", valor_sin_iva="0")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(Egreso.objects.get().total_con_iva, Decimal("0"))

    def test_un_honorario_sin_nombre_ni_meses_se_guarda(self):
        r = self._crear(
            tipo=Egreso.TIPO_HONORARIO, nombre_persona="", apellido_persona="",
            meses="", cuota_mensual="", monto_total="300000",
        )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(Egreso.objects.get().monto_total, Decimal("300000"))

    def test_bajar_los_meses_por_debajo_de_lo_pagado_no_bloquea(self):
        self._crear(tipo=Egreso.TIPO_HONORARIO, meses="6",
                    cuota_mensual="50000", monto_total="300000")
        honorario = Egreso.objects.get()
        Egreso.all_objects.filter(pk=honorario.pk).update(cuotas_pagadas=6)

        r = self.client.post(
            reverse("proyectos:editar_egreso", args=[honorario.pk]),
            {
                "tipo": Egreso.TIPO_HONORARIO,
                "estado": Egreso.ESTADO_COMPROMETIDO,
                "gasto_elegible": self.plan_corriente.gasto_elegible_id,
                "plan_de_gasto": self.plan_corriente.pk,
                "meses": "2", "cuota_mensual": "50000", "monto_total": "100000",
            },
        )

        self.assertEqual(r.status_code, 200)
        honorario.refresh_from_db()
        self.assertEqual(honorario.meses, 2)

    def test_el_gasto_elegible_se_alinea_con_el_plan(self):
        """Un elegible que no corresponde al plan ya no rechaza el gasto: sale
        de un formulario a medio recargar, no de una decisión."""
        r = self._crear(gasto_elegible=self.plan_capital.gasto_elegible_id,
                        plan_de_gasto=self.plan_corriente.pk)

        self.assertEqual(r.status_code, 200)
        gasto = Egreso.objects.get()
        self.assertEqual(gasto.gasto_elegible_id,
                         self.plan_corriente.gasto_elegible_id)
        self.assertEqual(gasto.gasto_id, self.plan_corriente.gasto_elegible.gasto_id)

    def test_el_plan_sigue_siendo_obligatorio(self):
        """Sin plan el gasto no se descuenta de ninguna parte ni aparece en el
        resultado, y no habría techo contra el cual medirlo."""
        r = self._crear(plan_de_gasto="")

        self.assertEqual(r.status_code, 400)
        self.assertIn("plan de gasto", r.content.decode().lower())
        self.assertFalse(Egreso.objects.exists())


class ValidacionDelNavegadorTests(BaseGastosTest):
    """El formulario tiene que poder enviarse desde el navegador.

    Este fue el defecto que hacía parecer muerto el botón Guardar: compra y
    honorario comparten formulario, y el bloque que no aplica queda escondido
    con sus montos en 0. Con `min="1"`, ese 0 invisible bastaba para que el
    navegador se negara a enviar — y, al no poder enfocar un campo que no se
    ve, no mostraba ningún aviso. Ninguna prueba de servidor podía verlo,
    porque el POST del cliente de pruebas se salta esa validación.
    """

    NUMERICOS = re.compile(r"<input\b[^>]*type=\"number\"[^>]*>")
    SCRIPTS = re.compile(r"<script\b.*?</script>", re.S)

    def _campos_que_bloquearian(self, html):
        # Sin los <script>: adentro hay campos que el JS arma en el navegador,
        # con marcadores en vez de valores.
        problemas = []
        for etiqueta in self.NUMERICOS.findall(self.SCRIPTS.sub("", html)):
            nombre = re.search(r'(?:name|id)="([^"]+)"', etiqueta)
            minimo = re.search(r'min="([^"]+)"', etiqueta)
            valor = re.search(r'value="([^"]*)"', etiqueta)
            texto = valor.group(1) if valor else ""
            if not (minimo and texto):
                continue
            if Decimal(texto) < Decimal(minimo.group(1)):
                problemas.append(
                    f"{nombre.group(1) if nombre else '?'}"
                    f" vale {texto} y su mínimo es {minimo.group(1)}"
                )
        return problemas

    def _formulario(self, gasto):
        return self.client.get(
            reverse("proyectos:editar_egreso_form", args=[gasto.pk])
        ).content.decode()

    def test_editar_una_compra_no_deja_campos_fuera_de_rango(self):
        html = self._formulario(self.compra())

        self.assertEqual(self._campos_que_bloquearian(html), [])

    def test_editar_un_honorario_no_deja_campos_fuera_de_rango(self):
        honorario = Egreso.objects.create(
            proyecto=self.proyecto, tipo=Egreso.TIPO_HONORARIO,
            plan_de_gasto=self.plan_corriente,
            gasto_elegible=self.plan_corriente.gasto_elegible,
            nombre_persona="Ana", apellido_persona="Pérez",
            meses=6, cuota_mensual=Decimal("50000"),
            monto_total=Decimal("300000"),
        )

        html = self._formulario(honorario)

        self.assertEqual(self._campos_que_bloquearian(html), [])

    def test_el_formulario_no_delega_la_decision_al_navegador(self):
        """`novalidate`: lo que se acepta lo decide el servidor, que siempre
        responde algo. El navegador sólo sabía negarse en silencio."""
        html = self._formulario(self.compra())

        self.assertIn("<form novalidate", " ".join(html.split()))


class CuotasDelHonorarioTests(BaseGastosTest):
    """Un monto por cuota.

    Con una sola cuota mensual no había forma de repartir un total que no se
    divide en pesos exactos, ni de dejar una cuota distinta de las otras.
    """

    def setUp(self):
        super().setUp()
        self.elegible_honorarios = GastoElegible.objects.get(nombre__iexact="Honorarios")
        self.plan, _ = PlanDeGasto.objects.get_or_create(
            actividad=self.actividad,
            gasto_elegible=self.elegible_honorarios,
            anio=2026,
            defaults={"monto": Decimal("20000000")},
        )
        self.plan.monto = Decimal("20000000")
        self.plan.save(update_fields=["monto"])

    def _guardar(self, cuotas, **extra):
        datos = {
            "tipo": Egreso.TIPO_HONORARIO,
            "estado": Egreso.ESTADO_COMPROMETIDO,
            "gasto_elegible": self.elegible_honorarios.pk,
            "plan_de_gasto": self.plan.pk,
            "nombre_persona": "Ana", "apellido_persona": "Pérez",
            "meses": str(len(cuotas)),
            "cuota_monto": [str(c) for c in cuotas],
        }
        datos.update(extra)
        return self.client.post(
            reverse("proyectos:crear_egreso", args=[self.proyecto.pk]), datos
        )

    def test_nueve_cuotas_iguales_se_guardan_como_nueve(self):
        r = self._guardar([555556] * 8 + [555552])

        self.assertEqual(r.status_code, 200)
        honorario = Egreso.objects.get()
        self.assertEqual(honorario.meses, 9)
        self.assertEqual(len(honorario.montos_de_cuotas), 9)

    def test_el_total_es_lo_que_suman_las_cuotas(self):
        """Ya no hay un total aparte que pueda contradecirlas."""
        self._guardar([555556] * 8 + [555552], monto_total="1")
        honorario = Egreso.objects.get()

        self.assertEqual(honorario.monto_total, Decimal("5000000"))
        self.assertEqual(honorario.montos[0], Decimal("5000000"))

    def test_las_cuotas_pueden_ser_distintas(self):
        """Un anticipo mayor y el resto parejo."""
        self._guardar([2000000, 500000, 500000, 500000])
        honorario = Egreso.objects.get()

        self.assertFalse(honorario.cuotas_son_iguales)
        self.assertEqual(honorario.monto_proxima_cuota, Decimal("2000000"))
        self.assertEqual(honorario.monto_total, Decimal("3500000"))

    def test_lo_pagado_sigue_el_monto_de_cada_cuota(self):
        self._guardar([2000000, 500000, 500000, 500000])
        honorario = Egreso.objects.get()
        Egreso.all_objects.filter(pk=honorario.pk).update(cuotas_pagadas=2)
        honorario.refresh_from_db()

        self.assertEqual(honorario.monto_pagado_honorario, Decimal("2500000"))
        self.assertEqual(honorario.monto_pendiente_honorario, Decimal("1000000"))
        self.assertEqual(honorario.monto_proxima_cuota, Decimal("500000"))

    def test_la_retencion_sale_de_la_cuota_que_toca(self):
        self._guardar([2000000, 500000])
        honorario = Egreso.objects.get()

        self.assertEqual(honorario.impuesto_por_cuota,
                         Decimal("2000000") * Egreso.IMPUESTO_HONORARIOS)

    def test_un_honorario_viejo_sin_detalle_sigue_andando(self):
        """No se migró nada: la lista vacía significa cuotas parejas."""
        viejo = Egreso.objects.create(
            proyecto=self.proyecto, tipo=Egreso.TIPO_HONORARIO,
            plan_de_gasto=self.plan, gasto_elegible=self.elegible_honorarios,
            meses=3, cuota_mensual=Decimal("100000"),
            monto_total=Decimal("300000"),
        )

        self.assertEqual(viejo.cuotas, [])
        self.assertEqual(viejo.montos_de_cuotas, [Decimal("100000")] * 3)
        self.assertTrue(viejo.cuotas_son_iguales)

    def test_el_formulario_llega_con_una_cuota_por_campo(self):
        self._guardar([2000000, 500000, 500000])
        honorario = Egreso.objects.get()

        html = self.client.get(
            reverse("proyectos:editar_egreso_form", args=[honorario.pk])
        ).content.decode()

        self.assertIn('id="hon-cuotas-iniciales"', html)
        self.assertIn('["2000000", "500000", "500000"]', html)

    def test_sin_cuotas_detalladas_manda_el_total_escrito(self):
        """Cargar sólo el total sigue funcionando: es un contrato parejo."""
        r = self.client.post(
            reverse("proyectos:crear_egreso", args=[self.proyecto.pk]),
            {
                "tipo": Egreso.TIPO_HONORARIO,
                "estado": Egreso.ESTADO_COMPROMETIDO,
                "gasto_elegible": self.elegible_honorarios.pk,
                "plan_de_gasto": self.plan.pk,
                "meses": "3", "cuota_mensual": "100000",
                "monto_total": "300000",
            },
        )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(Egreso.objects.get().monto_total, Decimal("300000"))

    def test_las_cuotas_tampoco_pueden_pasarse_del_plan(self):
        self.plan.monto = Decimal("1000000")
        self.plan.save(update_fields=["monto"])

        r = self._guardar([900000, 900000])

        self.assertEqual(r.status_code, 400)
        self.assertFalse(Egreso.objects.exists())

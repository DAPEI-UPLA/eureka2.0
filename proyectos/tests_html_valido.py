"""Comprueba que los formularios estén donde el navegador puede usarlos.

El defecto que motivó estas pruebas: los editores de reparto anual tenían el
`<form>` como hijo directo de `<tr>`. Eso es HTML inválido — dentro de una fila
sólo caben `<td>` y `<th>` —, así que el navegador descarta la etiqueta al
parsear: los inputs quedan sin formulario y el botón de guardar no envía nada.

En pantalla se veía perfecto y el botón no hacía absolutamente nada. Los tests
que había no lo detectaron porque buscaban texto en el HTML, y el texto estaba;
lo que fallaba era la estructura, que sólo importa cuando un navegador la parsea.
"""

from decimal import Decimal
from html.parser import HTMLParser

from django.urls import reverse

from .models import PresupuestoAnual, PresupuestoObjetivoAnual
from .tests import BaseProyectoTest


class BuscadorDeFormsMalUbicados(HTMLParser):
    """Encuentra `<form>` cuyo padre inmediato sea `<tr>`, `<table>` o `<tbody>`."""

    PADRES_PROHIBIDOS = {"tr", "table", "tbody", "thead", "tfoot"}
    SIN_CIERRE = {"input", "br", "hr", "img", "meta", "link", "col"}

    def __init__(self):
        super().__init__()
        self.pila = []
        self.mal_ubicados = []

    def handle_starttag(self, tag, attrs):
        if tag == "form" and self.pila and self.pila[-1] in self.PADRES_PROHIBIDOS:
            self.mal_ubicados.append(self.pila[-1])
        if tag not in self.SIN_CIERRE:
            self.pila.append(tag)

    def handle_endtag(self, tag):
        if tag in self.pila:
            while self.pila and self.pila.pop() != tag:
                pass


def formularios_mal_ubicados(html):
    buscador = BuscadorDeFormsMalUbicados()
    buscador.feed(html)
    return buscador.mal_ubicados


class FormulariosUsablesTests(BaseProyectoTest):

    def setUp(self):
        super().setUp()
        self.a1 = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=1, anio_calendario=2026,
            presupuesto_corriente=Decimal("300000"),
            presupuesto_capital=Decimal("200000"),
        )
        self.a2 = PresupuestoAnual.objects.create(
            proyecto=self.proyecto, numero_anio=2, anio_calendario=2027,
            presupuesto_corriente=Decimal("300000"),
            presupuesto_capital=Decimal("200000"),
        )
        self.objetivo = self.crear_objetivo()
        PresupuestoObjetivoAnual.objects.create(
            objetivo=self.objetivo, anio=self.a1,
            presupuesto_corriente=Decimal("100000"),
        )
        self.resultado = self.crear_resultado(self.objetivo)

    def _revisar(self, url):
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200)
        malos = formularios_mal_ubicados(respuesta.content.decode())
        self.assertEqual(
            malos, [],
            f"Hay <form> dentro de {malos}: el navegador los descarta al "
            f"parsear y el botón de guardar no envía nada.",
        )

    def test_el_reparto_del_proyecto_tiene_su_form_usable(self):
        self._revisar(
            reverse("proyectos:listar_presupuesto_anual", args=[self.proyecto.pk])
        )

    def test_el_reparto_del_objetivo_tiene_su_form_usable(self):
        self._revisar(
            reverse("proyectos:presupuesto_objetivo_anual", args=[self.objetivo.pk])
        )

    def test_el_reparto_del_resultado_tiene_su_form_usable(self):
        self._revisar(
            reverse("proyectos:presupuesto_resultado_anual", args=[self.resultado.pk])
        )

    def test_el_detalle_completo_no_tiene_forms_mal_ubicados(self):
        self._revisar(
            reverse("proyectos:detalle_proyecto", args=[self.proyecto.pk])
        )

    def test_el_buscador_detecta_el_caso_que_fallaba(self):
        """El detector tiene que reconocer la forma exacta del defecto."""
        malo = "<table><tbody><tr><form><td><input></td></form></tr></tbody></table>"
        self.assertEqual(formularios_mal_ubicados(malo), ["tr"])

        bueno = "<form><table><tbody><tr><td><input></td></tr></tbody></table></form>"
        self.assertEqual(formularios_mal_ubicados(bueno), [])

from decimal import Decimal

from django import forms

from .models import (
    Actividad,
    Contacto,
    CostoActividad,
    CostoDirecto,
    CostoTransversal,
    GastoExtra,
    Institucion,
    LineaFinanciera,
    MetaAnual,
    Propuesta,
    Relator,
    SalaZoom,
    SesionClase,
    SupuestosFinancieros,
    equipo_otec,
    rol_otec,
)

MAX_MB = 20

CONTROL = {"class": "form-control"}
SELECT = {"class": "form-select"}
FECHA = {"class": "form-control", "type": "date"}


def _estilizar(form):
    """Aplica las clases de Bootstrap sin repetirlas campo por campo."""
    for nombre, campo in form.fields.items():
        widget = campo.widget
        if isinstance(widget, forms.Select):
            widget.attrs.setdefault("class", "form-select")
        elif isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", "form-check-input")
        elif isinstance(widget, forms.Textarea):
            widget.attrs.setdefault("class", "form-control")
            widget.attrs.setdefault("rows", 3)
        else:
            widget.attrs.setdefault("class", "form-control")


class _FilaOpcional(forms.ModelForm):
    """Fila de formset que se ignora cuando sus campos clave vienen vacíos.

    El formset siempre ofrece una fila de más para agregar. Sin esto esa fila
    exigiría completarse, porque basta con que un campo traiga valor por
    defecto para que Django la dé por llenada.
    """

    CAMPOS_CLAVE = ()

    def _crudo(self, campo):
        nombre = self.add_prefix(campo)
        if hasattr(self.data, "getlist"):
            return [v for v in self.data.getlist(nombre) if v]
        return self.data.get(nombre)

    def has_changed(self):
        if not any(self._crudo(campo) for campo in self.CAMPOS_CLAVE):
            return False
        return super().has_changed()


class SesionClaseForm(forms.ModelForm):
    """Una clase concreta: qué día, a qué hora, cuánto dura y dónde."""

    class Meta:
        model = SesionClase
        fields = ["fecha", "hora_inicio", "duracion_horas", "sala", "grupo"]
        widgets = {
            "fecha": forms.DateInput(attrs=FECHA, format="%Y-%m-%d"),
            "hora_inicio": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}, format="%H:%M"
            ),
        }
        labels = {
            "fecha": "Día de la clase",
            "hora_inicio": "Hora de inicio",
            "duracion_horas": "Duración (h)",
            "sala": "Sala Zoom",
            "grupo": "Grupo (opcional)",
        }
        help_texts = {
            "sala": "Vacío si la clase no ocupa sala.",
            "grupo": "Solo si el curso dicta dos grupos en paralelo.",
        }

    def __init__(self, *args, actividad=None, **kwargs):
        super().__init__(*args, **kwargs)
        _estilizar(self)
        self.actividad = actividad
        self.fields["sala"].queryset = SalaZoom.objects.filter(activa=True)
        self.fields["sala"].required = False
        self.fields["grupo"].required = False

    def _post_clean(self):
        # La actividad se fija antes de validar el modelo: `clean` necesita
        # saber de qué curso es la clase para buscar los choques de sala.
        if self.actividad is not None:
            self.instance.actividad = self.actividad
        super()._post_clean()


class PropuestaForm(forms.ModelForm):
    """Expediente comercial y de tramitación."""

    class Meta:
        model = Propuesta
        fields = [
            "codigo", "institucion", "contacto", "canal", "estado_comercial",
            "fecha_envio", "anio",
            "estado_convenio", "observacion_convenio",
            "estado_decretacion", "memo_decretacion", "fecha_memo", "cr",
            "n_decreto", "fecha_resolucion",
        ]
        widgets = {
            "fecha_envio": forms.DateInput(attrs=FECHA, format="%Y-%m-%d"),
            "fecha_memo": forms.DateInput(attrs=FECHA, format="%Y-%m-%d"),
            "fecha_resolucion": forms.DateInput(attrs=FECHA, format="%Y-%m-%d"),
            "observacion_convenio": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "codigo": "ID de propuesta",
            "cr": "CR",
            "n_decreto": "N° de decreto",
            "anio": "Año",
        }
        help_texts = {
            "codigo": "Como en la planilla, p. ej. PROP-2026-010-SERPAT.",
            "contacto": "Debe pertenecer a la institución elegida.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilizar(self)
        self.fields["institucion"].queryset = Institucion.objects.filter(activa=True)
        self.fields["contacto"].required = False

        # El desplegable de contactos se limita a la institución elegida; HTMX
        # lo repuebla al cambiarla.
        institucion = self.data.get("institucion") or getattr(
            self.instance, "institucion_id", None
        )
        if institucion:
            self.fields["contacto"].queryset = Contacto.objects.filter(
                institucion_id=institucion
            )
        else:
            self.fields["contacto"].queryset = Contacto.objects.none()

    def clean_codigo(self):
        codigo = (self.cleaned_data["codigo"] or "").strip()
        existente = Propuesta.objects.filter(codigo__iexact=codigo)
        if self.instance.pk:
            existente = existente.exclude(pk=self.instance.pk)
        if existente.exists():
            raise forms.ValidationError(
                "Ya hay una propuesta con ese ID. Los ID no se pueden repetir: "
                "el importador los usa para reconocer el expediente."
            )
        return codigo

    def clean(self):
        datos = super().clean()
        contacto, institucion = datos.get("contacto"), datos.get("institucion")
        if contacto and institucion and contacto.institucion_id != institucion.pk:
            self.add_error(
                "contacto", "Ese contacto pertenece a otra institución."
            )
        memo, resolucion = datos.get("fecha_memo"), datos.get("fecha_resolucion")
        if memo and resolucion and resolucion < memo:
            self.add_error(
                "fecha_resolucion", "La resolución no puede ser anterior al memo."
            )
        return datos


class ActividadForm(forms.ModelForm):
    """Un curso dentro de una propuesta."""

    class Meta:
        model = Actividad
        fields = [
            "propuesta", "nombre", "modalidad", "prioridad",
            "n_participantes", "horas", "horas_asincronicas",
            "tipo_relator", "relator", "fecha_confirmacion_relator",
            "fecha_inicio", "fecha_termino", "proxima_fecha_critica",
            "estado_ejecucion", "n_participantes_ejecucion", "n_becados", "n_aprobados",
            "valor_ofertado", "monto_adjudicado",
            "n_factura", "fecha_factura", "monto_facturado",
            "fecha_pago", "monto_pagado",
            "observaciones", "responsables", "responsable_seguimiento", "actualizado_al",
        ]
        widgets = {
            f: forms.DateInput(attrs=FECHA, format="%Y-%m-%d")
            for f in (
                "fecha_confirmacion_relator", "fecha_inicio", "fecha_termino",
                "proxima_fecha_critica", "fecha_factura", "fecha_pago",
                "actualizado_al",
            )
        } | {
            "nombre": forms.TextInput(attrs={"maxlength": 500}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "nombre": "Nombre del curso",
            "horas": "Horas totales",
            "n_participantes": "N° de participantes comprometidos",
            "n_participantes_ejecucion": "N° de participantes en ejecución",
            "n_becados": "N° de becados",
            "n_aprobados": "N° de aprobados",
            "n_factura": "N° de factura",
        }

    def __init__(self, *args, propuesta=None, **kwargs):
        super().__init__(*args, **kwargs)
        _estilizar(self)
        self.fields["relator"].required = False
        self.fields["relator"].queryset = Relator.objects.filter(activo=True)
        self.fields["propuesta"].queryset = Propuesta.objects.select_related("institucion")

        # Solo el equipo OTEC puede ser responsable de una actividad.
        equipo = self.fields["responsables"]
        equipo.required = False
        equipo.queryset = equipo_otec()
        equipo.label_from_instance = lambda u: (
            f"{u.get_full_name() or u.username} · {rol_otec(u)}"
        )
        equipo.widget = forms.CheckboxSelectMultiple(
            choices=[(u.pk, equipo.label_from_instance(u)) for u in equipo.queryset]
        )
        if not equipo.queryset.exists():
            equipo.help_text = (
                "Todavía no hay nadie en los grupos «Encargado OTEC» ni "
                "«Profesional OTEC»."
            )

        # Al crear desde el detalle de una propuesta, esta no se elige.
        if propuesta is not None:
            self.fields["propuesta"].initial = propuesta.pk
            self.fields["propuesta"].disabled = True
            self.fields["propuesta"].widget = forms.HiddenInput()

    def clean(self):
        datos = super().clean()
        inicio, termino = datos.get("fecha_inicio"), datos.get("fecha_termino")
        if inicio and termino and termino < inicio:
            self.add_error(
                "fecha_termino", "El término no puede ser anterior al inicio."
            )

        facturado = datos.get("monto_facturado") or 0
        pagado = datos.get("monto_pagado") or 0
        if pagado > facturado:
            self.add_error(
                "monto_pagado", "No se puede haber pagado más de lo facturado."
            )

        propuesta = datos.get("propuesta") or self.initial.get("propuesta")
        nombre = (datos.get("nombre") or "").strip()
        if propuesta and nombre:
            hermanas = Actividad.objects.filter(propuesta=propuesta, nombre__iexact=nombre)
            if self.instance.pk:
                hermanas = hermanas.exclude(pk=self.instance.pk)
            if hermanas.exists():
                self.add_error(
                    "nombre",
                    "Esa propuesta ya tiene un curso con ese nombre. El importador "
                    "identifica los cursos por su nombre dentro de la propuesta.",
                )
        return datos


class _FormularioOtec(forms.ModelForm):
    """ModelForm con las clases de Bootstrap y el ancho de cada campo.

    ``ANCHOS`` dice qué campos ocupan la fila completa de la grilla de dos
    columnas. Va acá y no en el template para que el formulario siga siendo el
    único lugar donde se describe su propia forma.
    """

    ANCHOS = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilizar(self)

    def campos(self):
        """Pares (campo, clase de ancho) para recorrer desde el template."""
        return [(campo, self.ANCHOS.get(campo.name, "")) for campo in self]


class PorcentajeField(forms.DecimalField):
    """Se escribe en porcentaje (15) y se guarda en fracción (0,15).

    El modelo guarda la fracción porque es lo que multiplica en el cálculo,
    pero nadie razona el reparto en «0,15»: en la planilla y en las reuniones
    se habla de 15%.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("min_value", 0)
        kwargs.setdefault("max_value", 100)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("max_digits", 5)
        kwargs.setdefault("widget", forms.NumberInput(attrs={"step": "0.01"}))
        super().__init__(**kwargs)

    def prepare_value(self, value):
        # Al reenviar el formulario con errores el valor llega como texto y ya
        # está en porcentaje: solo se convierte lo que viene del modelo.
        if not isinstance(value, Decimal):
            return value
        pct = value * 100
        entero = pct.to_integral_value()
        return entero if pct == entero else pct

    def clean(self, value):
        pct = super().clean(value)
        return pct / 100 if pct is not None else pct


class SupuestosFinancierosForm(_FormularioOtec):
    """Los parámetros con los que se recalcula todo el flujo del año."""

    pct_upla = PorcentajeField(label="% de distribución UPLA")
    pct_otec = PorcentajeField(label="% de distribución OTEC")
    pct_autoaprendizaje = PorcentajeField(
        label="% en cursos de autoaprendizaje",
        help_text="Los cursos de autoaprendizaje se reparten mitad y mitad.",
    )

    class Meta:
        model = SupuestosFinancieros
        fields = [
            "saldo_inicial", "fecha_corte", "saldo_minimo",
            "pct_upla", "pct_otec", "pct_autoaprendizaje",
            "valor_hora_relatoria", "plazo_pago_costos_dias",
        ]
        widgets = {"fecha_corte": forms.DateInput(attrs=FECHA, format="%Y-%m-%d")}
        labels = {
            "saldo_inicial": "Saldo inicial de caja",
            "saldo_minimo": "Saldo mínimo de caja",
            "valor_hora_relatoria": "Valor hora de relatoría",
            "plazo_pago_costos_dias": "Plazo de pago de costos (días)",
        }
        help_texts = {
            "saldo_minimo": "Bajo este monto el mes se marca en rojo.",
        }


class MetaAnualForm(_FormularioOtec):
    """La meta contra la que se comparan los escenarios de ingreso."""

    class Meta:
        model = MetaAnual
        fields = ["monto"]
        labels = {"monto": "Meta de ingresos del año"}


class LineaFinancieraForm(_FormularioOtec):
    """Una línea de ingreso del flujo."""

    ANCHOS = {"descripcion": "span-2", "observacion": "span-2", "origen": "span-2"}

    class Meta:
        model = LineaFinanciera
        fields = [
            "codigo", "institucion", "descripcion", "actividad",
            "estado", "certeza", "autoaprendizaje",
            "participantes", "horas",
            "fecha_inicio", "fecha_termino", "fecha_facturacion",
            "fecha_pago_estimada", "fecha_pago_efectiva",
            "valor_ofertado", "monto_contratado", "monto_facturado", "monto_pagado",
            "origen", "observacion",
        ]
        widgets = {
            f: forms.DateInput(attrs=FECHA, format="%Y-%m-%d")
            for f in (
                "fecha_inicio", "fecha_termino", "fecha_facturacion",
                "fecha_pago_estimada", "fecha_pago_efectiva",
            )
        }
        labels = {
            "codigo": "Código de la línea",
            "actividad": "Curso asociado",
            "origen": "Origen del dato",
        }
        help_texts = {
            "fecha_pago_estimada": "Mes en que el flujo cuenta el ingreso.",
            "fecha_pago_efectiva": "Si está, manda sobre la estimada.",
            "monto_contratado": "El flujo usa este monto; si va en cero, usa el ofertado.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["institucion"].queryset = Institucion.objects.filter(activa=True)
        self.fields["actividad"].queryset = (
            Actividad.objects.select_related("propuesta").order_by("nombre")
        )

    def clean_codigo(self):
        codigo = (self.cleaned_data["codigo"] or "").strip()
        repetidas = LineaFinanciera.objects.filter(codigo__iexact=codigo)
        if self.instance.pk:
            repetidas = repetidas.exclude(pk=self.instance.pk)
        if repetidas.exists():
            raise forms.ValidationError(
                "Ya hay una línea con ese código. El importador del flujo "
                "reconoce las líneas por su código, así que no se repiten."
            )
        return codigo

    def clean(self):
        datos = super().clean()
        inicio, termino = datos.get("fecha_inicio"), datos.get("fecha_termino")
        if inicio and termino and termino < inicio:
            self.add_error("fecha_termino", "El término no puede ser anterior al inicio.")

        facturado = datos.get("monto_facturado") or 0
        pagado = datos.get("monto_pagado") or 0
        if pagado > facturado:
            self.add_error("monto_pagado", "No se puede haber pagado más de lo facturado.")
        return datos


class CostoDirectoForm(_FormularioOtec):
    """Los costos que se descuentan del ingreso de una línea."""

    ANCHOS = {"observacion": "span-2"}

    class Meta:
        model = CostoDirecto
        fields = [
            "relatoria", "materiales", "plataformas", "certificaciones",
            "traslados", "alimentacion", "arriendo", "otros",
            "fecha_pago_estimada", "fecha_pago_efectiva",
            "estado", "observacion",
        ]
        widgets = {
            f: forms.DateInput(attrs=FECHA, format="%Y-%m-%d")
            for f in ("fecha_pago_estimada", "fecha_pago_efectiva")
        }
        labels = {
            "relatoria": "Relatoría",
            "otros": "Otros costos directos",
            "estado": "Estado del pago",
        }
        help_texts = {
            "fecha_pago_estimada": "Mes en que el flujo carga el egreso.",
        }


class CostoTransversalForm(_FormularioOtec):
    """Un costo del área que no cuelga de ningún curso."""

    ANCHOS = {"descripcion": "span-2", "observacion": "span-2"}

    class Meta:
        model = CostoTransversal
        fields = [
            "codigo", "tipo", "descripcion", "area", "monto", "fecha_pago",
            "criterio", "fuente_financiamiento", "incluir_en_flujo", "observacion",
        ]
        widgets = {"fecha_pago": forms.DateInput(attrs=FECHA, format="%Y-%m-%d")}
        labels = {
            "codigo": "Código del costo",
            "incluir_en_flujo": "Incluirlo en el flujo de caja",
        }
        help_texts = {
            "incluir_en_flujo": "Desmárquelo para dejarlo registrado sin que pese en la caja.",
            "fecha_pago": "Sin fecha, el costo no entra en ningún mes.",
        }

    def clean_codigo(self):
        codigo = (self.cleaned_data["codigo"] or "").strip()
        repetidos = CostoTransversal.objects.filter(codigo__iexact=codigo)
        if self.instance.pk:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise forms.ValidationError("Ya hay un costo transversal con ese código.")
        return codigo


class CostoActividadForm(forms.ModelForm):
    """Las categorías fijas del desglose de costos de un curso."""

    class Meta:
        model = CostoActividad
        fields = [campo for campo, _ in CostoActividad.CATEGORIAS]
        labels = dict(CostoActividad.CATEGORIAS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilizar(self)


class GastoExtraForm(_FilaOpcional):
    """Una línea libre para lo que no calza en las categorías fijas."""

    CAMPOS_CLAVE = ("descripcion", "monto")

    class Meta:
        model = GastoExtra
        fields = ["descripcion", "monto"]
        labels = {"descripcion": "Glosa del gasto", "monto": "Monto (CLP)"}
        widgets = {
            "descripcion": forms.TextInput(
                attrs={"placeholder": "Ej: traslado del relator a Valparaíso"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilizar(self)


GastoExtraFormSet = forms.inlineformset_factory(
    Actividad,
    GastoExtra,
    form=GastoExtraForm,
    extra=1,
    can_delete=True,
)


class SubirTableroForm(forms.Form):
    archivo = forms.FileField(
        label="Archivo del Tablero Maestro (.xlsx)",
        widget=forms.ClearableFileInput(attrs={
            "accept": ".xlsx",
            "class": "form-control",
        }),
    )
    separar_conflictos = forms.BooleanField(
        required=False,
        initial=True,
        label="Separar expedientes que comparten un mismo ID de propuesta",
        help_text=(
            "Si un ID agrupa filas con distinta fecha de envío o distinto decreto, "
            "se importan como propuestas separadas con sufijo -2, -3."
        ),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    sobrescribir_ediciones = forms.BooleanField(
        required=False,
        initial=False,
        label="Dejar que el Excel pise los checklists editados en el sistema",
        help_text=(
            "Por defecto se conservan los ítems que alguien marcó desde la "
            "aplicación, porque suelen estar más al día que la planilla."
        ),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if not archivo.name.lower().endswith(".xlsx"):
            raise forms.ValidationError(
                "El archivo debe ser un .xlsx. Si es .xls o .xlsm, guárdelo como .xlsx."
            )
        if archivo.size > MAX_MB * 1024 * 1024:
            raise forms.ValidationError(f"El archivo supera los {MAX_MB} MB.")
        return archivo

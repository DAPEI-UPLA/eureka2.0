from django import forms
from .models import Gestion, Iniciativa, Formulacion, MetaAmbito


class IniciativaForm(forms.ModelForm):

    class Meta:
        model = Iniciativa
        fields = [
            "nombre",
            "descripcion",
            "unidad",
            "funcion_institucional",
            "fecha_inicio",
            "fecha_termino",
            "descarga_horas",
        ]

        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
            }),
            "descripcion": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "maxlength": 500,
            }),
            "unidad": forms.TextInput(attrs={
                "class": "form-control",
            }),
            "funcion_institucional": forms.Select(attrs={
                "class": "form-select",
            }),
            "fecha_inicio": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date"
            }),
            "fecha_termino": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date"
            }),
            "descarga_horas": forms.CheckboxInput(attrs={
                "class": "form-check-input"
            }),
        }

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get("fecha_inicio")
        termino = cleaned.get("fecha_termino")
        if inicio and termino and termino < inicio:
            self.add_error(
                "fecha_termino",
                "La fecha de término no puede ser anterior a la fecha de inicio.",
            )
        return cleaned


class FormulacionForm(forms.ModelForm):

    class Meta:
        model = Formulacion
        fields = [
            "nombre_fondo",
            "link_convocatoria",
        ]

        widgets = {
            "nombre_fondo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Fondo de Innovación Regional",
            }),
            "link_convocatoria": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "https://...",
            }),
        }


# =============================================================
# TABLERO MAESTRO DE RESULTADOS
# =============================================================

class GestionForm(forms.ModelForm):
    """Alta y edición de una fila del registro.

    Lo único que se exige es lo que el tablero necesita para contar: ámbito,
    nombre y estado. Las fechas y los montos pueden completarse después —una
    gestión "en identificación" todavía no tiene ni monto ni fecha de ingreso—,
    tal como pasa en la planilla.
    """

    class Meta:
        model = Gestion
        fields = [
            "codigo", "ambito", "tipo", "nombre", "institucion",
            "fecha_ingreso", "monto_postulado", "estado",
            "fecha_resultado", "monto_adjudicado", "responsable",
            "observaciones",
        ]
        widgets = {
            "codigo": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Ej: C-002 o ID 628-8-LE26"}),
            "ambito": forms.Select(attrs={"class": "form-select"}),
            "tipo": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Ej: Mercado Público"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "institucion": forms.TextInput(attrs={"class": "form-control"}),
            "fecha_ingreso": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "monto_postulado": forms.NumberInput(attrs={
                "class": "form-control", "min": 0, "step": 1}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "fecha_resultado": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "monto_adjudicado": forms.NumberInput(attrs={
                "class": "form-control", "min": 0, "step": 1}),
            "responsable": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Unidad o facultad"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        ingreso = cleaned.get("fecha_ingreso")
        resultado = cleaned.get("fecha_resultado")
        if ingreso and resultado and resultado < ingreso:
            self.add_error(
                "fecha_resultado",
                "La fecha de resultado no puede ser anterior a la de ingreso.",
            )
        return cleaned


class SubirPlanillaForm(forms.Form):
    """Carga del Excel actualizado."""

    archivo = forms.FileField(
        label="Planilla de resultados (.xlsx)",
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control", "accept": ".xlsx"}),
    )
    podar = forms.BooleanField(
        label="Eliminar las gestiones importadas que ya no vienen en el archivo",
        required=False,
        initial=True,
        help_text=(
            "Deja el sistema igual al Excel. Lo cargado a mano nunca se borra, "
            "y lo que se editó acá se pregunta una por una."
        ),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if not archivo.name.lower().endswith(".xlsx"):
            raise forms.ValidationError(
                "El archivo debe ser un .xlsx. Si lo tiene en .xls, guárdelo "
                "como libro de Excel moderno.")
        if archivo.size > 10 * 1024 * 1024:
            raise forms.ValidationError("El archivo supera los 10 MB.")
        return archivo


class MetaAmbitoForm(forms.ModelForm):
    class Meta:
        model = MetaAmbito
        fields = ["meta_gestiones"]
        widgets = {
            "meta_gestiones": forms.NumberInput(attrs={
                "class": "form-control form-control-sm text-end",
                "min": 0, "step": 1}),
        }
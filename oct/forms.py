from django import forms
from .models import Iniciativa, Formulacion


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
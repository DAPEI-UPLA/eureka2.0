from django import forms
from .models import Iniciativa


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
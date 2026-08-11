from django import forms
from .models import Informe


class InformeForm(forms.ModelForm):

    class Meta:
        model = Informe
        fields = [
            "nombre",
            "descripcion",
            "estado",
            "fecha_estimada_termino",
        ]

        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
            }),
            "descripcion": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "maxlength": 1000,
            }),
            "estado": forms.Select(attrs={
                "class": "form-select",
            }),
            "fecha_estimada_termino": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
        }

from django import forms
from .models import Indicador, Programa, Objetivo, Estrategia, SeguimientoIndicador

class IndicadorForm(forms.ModelForm):

    class Meta:
        model = Indicador
        fields = [
            "nombre",
            "descripcion",
            "objetivo",
            "formula",
            "unidad_medida",
            "linea_base",
            "calculo_invertido",
            "acumulativo",
        ]

        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "objetivo": forms.Select(attrs={"class": "form-select"}),
            "formula": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "unidad_medida": forms.Select(attrs={"class": "form-select"}),
            "linea_base": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "calculo_invertido": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "acumulativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ProgramaForm(forms.ModelForm):
    class Meta:
        model = Programa
        fields = ['nombre']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ingrese el nombre del plan'
            })
        }

class ObjetivoForm(forms.ModelForm):
    class Meta:
        model = Objetivo
        fields = ["nombre", "descripcion", "tipo"]
        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control rounded-3",
                "placeholder": "Ej: Mejorar cobertura académica"
            }),
            "descripcion": forms.Textarea(attrs={
                "class": "form-control rounded-3",
                "rows": 3,
                "placeholder": "Describe el alcance del objetivo..."
            }),
            "tipo": forms.Select(attrs={
            "class": "form-select form-select-lg rounded-3 shadow-sm border-0",
            })
        }



class EstrategiaForm(forms.ModelForm):
    class Meta:
        model = Estrategia
        fields = ["nombre", "descripcion", "plazo"]

        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Mejorar eficiencia operativa"
            }),
            "descripcion": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Describe la estrategia..."
            }),
            "plazo": forms.Select(attrs={
                "class": "form-select"
            }),
        }

class SeguimientoIndicadorForm(forms.ModelForm):
    class Meta:
        model = SeguimientoIndicador
        fields = ["anio", "valor"]

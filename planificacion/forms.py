from django import forms
from .models import Indicador, Programa

class IndicadorForm(forms.ModelForm):
    class Meta:
        model = Indicador
        fields = "__all__"
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'programa': forms.Select(attrs={'class': 'form-select'}),
            'aplica_linea_base': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'acumulativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'calculo_invertido': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ProgramaForm(forms.ModelForm):
    class Meta:
        model = Programa
        fields = ['nombre']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ingrese el nombre del programa'
            })
        }
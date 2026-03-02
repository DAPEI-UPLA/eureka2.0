from django import forms
from .models import Proyecto

class ProyectoForm(forms.ModelForm):
    class Meta:
        model = Proyecto
        fields = [
            'nombre',
            'descripcion',
            'tipo',
            'responsable',
            'duracion_meses',
            'prioridad',
            'estado',
            'presupuesto_total',
        ]

        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Proyecto Fortalecimiento 2026'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descripción breve del proyecto...'
            }),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'responsable': forms.Select(attrs={'class': 'form-select'}),
            'duracion_meses': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 12'
            }),
            'prioridad': forms.Select(attrs={'class': 'form-select'}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'presupuesto_total': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Monto en pesos chilenos (CLP)'
            }),
        }

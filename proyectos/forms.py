from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import Proyecto
from .numeros import a_decimal


def _parse_decimal(raw):
    """Convierte un string en formato CL ('1.234.567,89') o numérico a Decimal."""
    return a_decimal(raw, default=None)


class ProyectoForm(forms.ModelForm):

    porcentaje_corriente = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    porcentaje_capital = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    presupuesto_corriente = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    presupuesto_capital = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    # Presupuesto opcional: si se deja en blanco se conserva el actual.
    presupuesto_total = forms.DecimalField(
        required=False,
        max_digits=15,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Proyecto
        fields = [
            'nombre',
            'codigo',
            'descripcion',
            'tipo',
            'responsable',
            'duracion_meses',
            'fecha_inicio',
            'fecha_fin',
            'anio_inicial',
            'prioridad',
            'estado',
            'presupuesto_total',
            'presupuesto_corriente',
            'presupuesto_capital',
        ]

        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: UPA 22991'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'responsable': forms.Select(attrs={'class': 'form-select'}),
            'duracion_meses': forms.NumberInput(attrs={'class': 'form-control'}),
            # `type="date"` para que el navegador muestre su calendario. El
            # formato ISO del value es el único que ese control acepta, así que
            # las plantillas lo escriben con `|date:"Y-m-d"` y no localizado.
            'fecha_inicio': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'fecha_fin': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'anio_inicial': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': 'Ej: 2026',
                'min': 2000, 'max': 2100, 'step': 1,
            }),
            'prioridad': forms.Select(attrs={'class': 'form-select'}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'presupuesto_total': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    # Campos de presupuesto que se validan como un conjunto: si la combinación
    # no cuadra, ninguno entra a la instancia.
    _CAMPOS_PRESUPUESTO = (
        "presupuesto_total",
        "presupuesto_corriente",
        "presupuesto_capital",
    )

    def _error_presupuesto(self, cleaned_data, mensaje):
        """Reporta un problema de presupuesto una sola vez.

        `Proyecto.clean()` repite la regla «corriente + capital == total» y
        corre igual durante `_post_clean()`, aunque este `clean()` ya haya
        fallado: el usuario terminaba viendo el mismo problema redactado de dos
        formas. Sacando los montos de `cleaned_data`, `construct_instance()` los
        omite, la instancia conserva los valores guardados —que sí cuadran— y la
        validación del modelo no vuelve a quejarse.
        """
        for campo in self._CAMPOS_PRESUPUESTO:
            cleaned_data.pop(campo, None)
        raise ValidationError(mensaje)

    def clean(self):
        cleaned_data = super().clean()

        inst = self.instance

        total_raw = cleaned_data.get("presupuesto_total")
        if total_raw in (None, ""):
            total = inst.presupuesto_total or Decimal("0")
        elif isinstance(total_raw, Decimal):
            total = total_raw
        else:
            total = Decimal(str(total_raw))

        pc = cleaned_data.get("porcentaje_corriente")
        pk = cleaned_data.get("porcentaje_capital")

        mc = _parse_decimal(cleaned_data.get("presupuesto_corriente"))
        mk = _parse_decimal(cleaned_data.get("presupuesto_capital"))

        # PORCENTAJES tienen prioridad si vienen ambos
        if pc is not None and pk is not None:
            if pc + pk != Decimal("100"):
                self._error_presupuesto(
                    cleaned_data,
                    f"Los porcentajes deben sumar 100 (van {pc + pk:g}).",
                )
            cleaned_data["presupuesto_total"] = total
            cleaned_data["presupuesto_corriente"] = (total * pc / Decimal("100")).quantize(Decimal("0.01"))
            cleaned_data["presupuesto_capital"] = (total * pk / Decimal("100")).quantize(Decimal("0.01"))

        elif mc is not None and mk is not None:
            if (mc + mk) != total:
                # El modal deja el total en blanco y muestra el actual como
                # placeholder, así que es fácil escribir solo la distribución y
                # no entender por qué no cuadra: lo decimos explícitamente.
                if total_raw in (None, ""):
                    detalle = (
                        f"dejaste el Presupuesto Total en blanco, así que se conserva "
                        f"el actual (${total:,.0f}). Escribe también el total."
                    )
                else:
                    detalle = f"el Presupuesto Total es ${total:,.0f}."
                self._error_presupuesto(
                    cleaned_data,
                    f"Corriente (${mc:,.0f}) + Capital (${mk:,.0f}) = "
                    f"${mc + mk:,.0f}, pero {detalle}",
                )
            cleaned_data["presupuesto_total"] = total
            cleaned_data["presupuesto_corriente"] = mc
            cleaned_data["presupuesto_capital"] = mk

        else:
            # Distribución incompleta. Si el usuario no tocó nada el presupuesto
            # es opcional y conservamos el actual (o queda en 0 al crear); pero
            # si escribió algo no podemos ignorarlo en silencio: antes se perdía
            # el dato y aun así salía «Proyecto actualizado».
            if any(v not in (None, "") for v in (total_raw, mc, mk, pc, pk)):
                self._error_presupuesto(
                    cleaned_data,
                    "Para cambiar el presupuesto completa el Total y su "
                    "distribución: Corriente y Capital, en montos o en "
                    "porcentajes. Déjalos todos en blanco para mantener el actual.",
                )
            cleaned_data["presupuesto_total"] = inst.presupuesto_total or Decimal("0")
            cleaned_data["presupuesto_corriente"] = inst.presupuesto_corriente or Decimal("0")
            cleaned_data["presupuesto_capital"] = inst.presupuesto_capital or Decimal("0")

        return cleaned_data

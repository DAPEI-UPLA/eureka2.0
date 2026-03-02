from django.db import models


class TipoIndicador(models.Model):
    nombre = models.CharField(max_length=50)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Tipo de Indicador"
        verbose_name_plural = "Tipos de Indicadores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Programa(models.Model):
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Programa / PD"
        verbose_name_plural = "Programas / PD"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Indicador(models.Model):
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField()

    programa = models.ForeignKey(
        Programa,
        on_delete=models.CASCADE,
        related_name="indicadores"
    )

    tipo = models.ForeignKey(
        TipoIndicador,
        on_delete=models.PROTECT,
        related_name="indicadores"
    )

    aplica_linea_base = models.BooleanField(default=False)
    acumulativo = models.BooleanField(default=False)
    calculo_invertido = models.BooleanField(default=False)

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

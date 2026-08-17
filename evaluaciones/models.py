from django.db import models

# Nivel que se asume mientras nadie lo haya definido para un ítem.
NIVEL_POR_DEFECTO = 3


class NivelRequerido(models.Model):
    """Nivel exigido a un ítem del perfil de un cargo.

    En el prototipo esto vivía en un JSON dentro del directorio de la app, y
    cada guardado reescribía el archivo entero. Eso trae dos problemas que en
    el escritorio no se notan: al desplegar se reemplaza el código y el archivo
    se va con él, y dos jefaturas guardando a la vez se pisan el trabajo, porque
    la segunda escribe encima de lo que leyó antes que la primera guardara.
    Una fila por ítem resuelve las dos cosas.

    `ruta` es la del organigrama ('VAF/finanzas-presupuestos/presupuesto/d3') y
    `clave` el identificador del ítem dentro del perfil ('fun-0', 'hi-9'). No
    hay clave foránea porque el organigrama y los perfiles viven en archivos,
    no en la base; ver `estructura.py`.
    """

    ruta = models.CharField("ruta del cargo", max_length=200, db_index=True)
    clave = models.CharField("ítem del perfil", max_length=20)
    nivel = models.PositiveSmallIntegerField("nivel requerido", default=NIVEL_POR_DEFECTO)
    actualizado = models.DateTimeField("última modificación", auto_now=True)

    class Meta:
        verbose_name = "nivel requerido"
        verbose_name_plural = "niveles requeridos"
        ordering = ["ruta", "clave"]
        constraints = [
            models.UniqueConstraint(fields=["ruta", "clave"], name="evaluaciones_nivel_unico"),
        ]

    def __str__(self):
        return f"{self.ruta} · {self.clave} = {self.nivel}"


def niveles_de(ruta):
    """Los niveles guardados de un cargo, como {clave: nivel}."""
    return dict(NivelRequerido.objects.filter(ruta=ruta).values_list("clave", "nivel"))


def guardar_niveles(ruta, niveles):
    """Guarda {clave: nivel} para un cargo, creando o actualizando cada ítem."""
    for clave, nivel in niveles.items():
        NivelRequerido.objects.update_or_create(
            ruta=ruta, clave=clave, defaults={"nivel": nivel})

"""Perfiles de cargo y su troceo en ítems evaluables.

Los perfiles se extrajeron de los Excel piloto (Contabilidad, Presupuesto,
Tesorería) a `datos/perfiles.json`. Cada campo es un bloque de texto redactado
a mano, no una lista: para poder evaluar hay que partirlo en ítems, y de eso se
encargan las funciones de abajo.

El troceo es heurístico por necesidad — el original es prosa, con numeraciones
inconsistentes y encabezados pegados al texto. Acierta en los perfiles piloto y
degrada de forma visible (un ítem de más o de menos), nunca en silencio: los
ítems se muestran en pantalla, así que un corte malo se ve al evaluar.
"""

import json
import pathlib
import re

RUTA_DATOS = pathlib.Path(__file__).parent / "datos" / "perfiles.json"

PERFILES = json.loads(RUTA_DATOS.read_text(encoding="utf-8"))

# Campos del perfil y su etiqueta, en el orden en que se muestran en la ficha.
CAMPOS_PERFIL = [
    ("familia", "Familia de cargo"),
    ("escalafon", "Escalafón"),
    ("criterio_formacion", "Criterio de clasificación (formación)"),
    ("formacion", "Formación"),
    ("experiencia", "Experiencia laboral"),
    ("proposito", "Propósito del cargo"),
    ("funciones_criticas", "Funciones críticas"),
    ("hab_conductuales", "Habilidades conductuales transversales"),
    ("hab_tecnicas", "Habilidades técnicas o específicas"),
    ("hab_institucionales", "Habilidades institucionales UPLA"),
    ("evidencias", "Evidencias observables"),
    ("grado", "Grado"),
]

# Campos de identificación de la evaluación (texto libre, salen en el informe)
CAMPOS_IDENT = [
    ("funcionario", "Nombre del funcionario/a evaluado/a"),
    ("evaluador", "Nombre del evaluador/a (jefatura)"),
    ("periodo", "Período evaluado"),
]

# Etiquetas de la escala 0-4 (hoja "Hoja2" del Excel)
ESCALA_NIVEL = [
    (0, "0 · No observado"),
    (1, "1 · Inicial"),
    (2, "2 · Básico"),
    (3, "3 · Intermedio"),
    (4, "4 · Avanzado"),
]

CAMPOS_ASISTENCIA = [
    ("dias_habiles", "Total días hábiles del período"),
    ("dias_asistidos", "Días asistidos"),
    ("atrasos", "N° de atrasos"),
    ("salidas_anticipadas", "N° de salidas anticipadas"),
    ("inasistencias_justificadas", "N° de inasistencias justificadas"),
    ("inasistencias_injustificadas", "N° de inasistencias injustificadas"),
]

# Secciones evaluables del instrumento genérico: (id, campo del perfil, título).
# El id corto es el prefijo de la clave de cada ítem ("fun-0", "hc-3"), que es
# lo que se guarda como nivel requerido; cambiarlo desconecta lo ya guardado.
SECCIONES = [
    ("fun", "funciones_criticas", "Funciones críticas"),
    ("hc", "hab_conductuales", "Habilidades conductuales transversales"),
    ("ht", "hab_tecnicas", "Habilidades técnicas o específicas"),
    ("hi", "hab_institucionales", "Habilidades institucionales UPLA"),
]


def perfil_de(referencia):
    """Devuelve los datos del perfil ['depto', 'TIPO'], o None si no existe."""
    if not referencia:
        return None
    depto, tipo = referencia
    return PERFILES.get(depto, {}).get(tipo)


def campos_visibles(datos):
    """Pares (etiqueta, valor) del perfil, saltando los campos vacíos."""
    return [(etiqueta, datos.get(clave))
            for clave, etiqueta in CAMPOS_PERFIL if datos.get(clave)]


def partir_funciones(texto):
    """Parte un bloque de 'funciones críticas' (texto numerado) en ítems."""
    if not texto:
        return []
    t = re.sub(r"\s+", " ", texto.replace("\n", " ")).strip()
    segs = re.split(r"(?<!\d)\d+\.\-?\s+", t)
    salida = []
    for s in segs:
        s = s.strip()
        # quita un encabezado de categoría pegado al final ("...texto. Categoría:")
        s = re.sub(r"\s+[A-ZÁÉÍÓÚÑ][^.:]{3,70}:$", "", s).strip()
        if not s or s.endswith(":") or len(s) < 5:
            continue
        salida.append(s)
    return salida


def partir_lista(texto):
    """Parte un bloque de habilidades (oraciones o lista por comas) en ítems."""
    if not texto:
        return []
    salida = []
    for trozo in re.split(r"[.\n;]+", texto):
        trozo = trozo.strip(" ,")
        if not trozo:
            continue
        if trozo.count(",") >= 2:
            salida += [x.strip() for x in trozo.split(",") if len(x.strip()) >= 3]
        elif len(trozo) >= 3:
            salida.append(trozo)
    return salida


def secciones_evaluables(datos):
    """Secciones con sus ítems, a partir de los campos de texto del perfil."""
    if not datos:
        return []
    secs = []
    for sid, campo, titulo in SECCIONES:
        partir = partir_funciones if sid == "fun" else partir_lista
        items = partir(datos.get(campo))
        if items:
            secs.append({"id": sid, "titulo": titulo, "items": items})
    return secs


def claves(secciones):
    """Todas las claves de ítem ('fun-0', 'hc-1', ...) de esas secciones."""
    return [f"{s['id']}-{i}" for s in secciones for i, _ in enumerate(s["items"])]

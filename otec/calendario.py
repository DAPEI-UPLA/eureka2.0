"""Grilla horaria y códigos del calendario Zoom.

La hoja ``Zoom`` del Tablero Maestro usaba bloques fijos de 30 minutos entre
las 08:30 y las 20:00, y abreviaba cada curso con un código propio
(``FORM (S.AP)``). Acá viven esa grilla y la traducción de códigos.
"""

from datetime import time

# 23 bloques de 30 minutos, de 08:30 a 20:00.
BLOQUES = []
_minutos = 8 * 60 + 30
while _minutos < 20 * 60:
    BLOQUES.append((
        time(_minutos // 60, _minutos % 60),
        time((_minutos + 30) // 60, (_minutos + 30) % 60),
    ))
    _minutos += 30

# Etiqueta "08:30-09:00" -> (inicio, fin)
BLOQUES_POR_ETIQUETA = {
    f"{i:%H:%M}-{f:%H:%M}": (i, f) for i, f in BLOQUES
}

# Código del calendario -> fragmento distintivo del nombre de la actividad.
# El mapeo se verificó contra el solapamiento de fechas con la carta Gantt.
CODIGOS_ZOOM = {
    "FORM": "formulación, análisis y uso de indicadores",
    "HABORAT": "oratoria y comunicación efectiva",
    "FISCYSUP": "fiscalización y supervigilancia",
    "PLANFIS": "planificación, fiscalización y control",
    "CONYCORR": "conocimiento y correcta aplicación",
    "LEYBONOS": "ley y bonos de incentivo",
    "TALLDEGES": "taller de gestión y manejo de emociones",
    "GESRIESG": "gestión de riesgos",
    "ENTLAB": "entornos laborales saludables",
    "DESYFORT": "desarrollo y fortalecimiento",
}

# Filas especiales de la hoja Zoom (1-indexadas), por sala.
FILAS_SALA_1 = {"fechas": 3, "primer_bloque": 4, "ultimo_bloque": 26}
FILAS_SALA_2 = {"fechas": 31, "primer_bloque": 32, "ultimo_bloque": 54}
FILA_ASINCRONICAS = 27
FILA_OTRAS = 28

SALAS = [
    ("Sala Zoom 1", FILAS_SALA_1),
    ("Sala Zoom 2", FILAS_SALA_2),
]

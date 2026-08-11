"""Paleta y armado de datos para los gráficos de OTEC.

La paleta categórica es la de referencia del método de visualización, validada
sobre la superficie blanca de las tarjetas: banda de luminosidad, piso de croma,
separación bajo daltonismo (protan/deutan) y piso de visión normal. **El orden
de los slots es el mecanismo de seguridad, no es decorativo** — asignar siempre
en orden, nunca ciclando ni reordenando.

El azul UPLA ``#009fe3`` se mantiene como acento de interfaz (botones, enlaces,
barras de progreso), pero no como marca de datos: mide 2.97:1 contra blanco,
apenas bajo el mínimo de 3:1.
"""

# Slots categóricos, en orden fijo.
SERIES = [
    "#2a78d6",  # 1 azul
    "#eb6834",  # 2 naranja
    "#1baf7a",  # 3 aguamarina
    "#eda100",  # 4 amarillo
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 verde
    "#4a3aa7",  # 7 violeta
    "#e34948",  # 8 rojo
]

# Rampa secuencial (un solo tono, claro -> oscuro) para magnitud continua.
SECUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#256abf", "#184f95"]

# El nivel de certeza de un ingreso es una escala ORDENADA, no un conjunto de
# identidades: va de lo ya cobrado a lo apenas supuesto. Por eso lleva rampa
# ordinal de un solo tono (oscuro = firme, claro = supuesto) y no colores
# categóricos. Validada: ΔL >= 0.06 entre pasos y el paso más claro 2.11:1.
CERTEZA = {
    "EFECTIVO": "#184f95",
    "CONFIRMADO": "#2a78d6",
    "PROBABLE": "#5598e7",
    "PROYECTADO": "#86b6ef",
}

ETIQUETA_CERTEZA = {
    "EFECTIVO": "Efectivo (ya cobrado)",
    "CONFIRMADO": "Confirmado",
    "PROBABLE": "Probable",
    "PROYECTADO": "Proyectado",
}

# Estados: reservados, nunca se reutilizan como "serie N". Van siempre con
# etiqueta, nunca solo color.
ESTADO = {
    "bien": "#0ca30c",
    "atencion": "#fab219",
    "serio": "#ec835a",
    "critico": "#d03b3b",
}

# Tinta y cromo del gráfico.
TINTA = {
    "primaria": "#0b0b0b",
    "secundaria": "#52514e",
    "apagada": "#898781",
    "grilla": "#e1e0d9",
    "eje": "#c3c2b7",
    "superficie": "#ffffff",
}

# Riesgo y alerta usan la paleta de estados, no la categórica.
COLOR_RIESGO = {
    "Sin alerta": ESTADO["bien"],
    "Decretación pendiente": ESTADO["critico"],
    "Falta nómina": ESTADO["serio"],
    "Pendiente facturar": ESTADO["atencion"],
    "Pendiente pago": ESTADO["atencion"],
}

COLOR_ALERTA = {
    "Al día": ESTADO["bien"],
    "Pendientes críticos": ESTADO["critico"],
    "Pendientes operativos": ESTADO["atencion"],
    "Sin programación": ESTADO["serio"],
    "Seguimiento comercial": SERIES[0],
}

MESES_CORTOS = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}


def serie(indice):
    """Color categórico del slot ``indice`` (0-based).

    A partir del noveno no se inventa un tono nuevo: quien llame agrupa en
    "Otras" o cambia de forma. Por eso esto revienta en vez de ciclar.
    """
    if indice >= len(SERIES):
        raise IndexError(
            "No hay un noveno color categórico: agrupe en «Otras» o use "
            "múltiplos pequeños."
        )
    return SERIES[indice]

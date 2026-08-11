"""Catálogo de controles del checklist de una actividad.

Cada entrada corresponde a una de las columnas Sí/No/Pendiente de la hoja
``Registro Actividades`` del Tablero Maestro. La columna original se conserva
en ``columna_excel`` para que el importador pueda mapearla sin adivinar.

Los ítems marcados ``critico=True`` son los que bloquean la ejecución: si
alguno queda pendiente, la actividad se muestra con alerta crítica.
"""

from .models import Etapa

# (etapa, nombre, crítico, columna del Excel)
CATALOGO = [
    # --- Propuesta técnica ---
    (Etapa.PROPUESTA, "Propuesta de capacitación enviada", True, "Propuesta Capacitación Enviada"),
    (Etapa.PROPUESTA, "Planificación de actividad enviada", True, "Planificación Actividad Enviada"),
    (Etapa.PROPUESTA, "Propuesta técnica validada por requirente", True, "Propuesta técnica validada por requirente"),
    (Etapa.PROPUESTA, "Fichas técnicas recepcionadas", False, "Fichas técnicas recepcionadas"),
    (Etapa.PROPUESTA, "Fechas y horarios confirmados por escrito", True, "Fechas y horarios confirmados por escrito"),

    # --- Relatoría ---
    (Etapa.RELATORIA, "Relator/a confirmado/a", True, "Relator Confirmado"),
    (Etapa.RELATORIA, "Condiciones de relatoría aceptadas", True, "Condiciones relatoría aceptadas"),
    (Etapa.RELATORIA, "Antecedentes del relator/a completos", False, "Antecedentes relator/a completos"),
    (Etapa.RELATORIA, "SUCH generada", False, "SUCH generada"),
    (Etapa.RELATORIA, "Convenio de relator/a derivado", False, "Convenio relator/a derivado"),
    (Etapa.RELATORIA, "Boleta de honorarios solicitada", False, "Boleta honorarios solicitada"),

    # --- Plataforma ---
    (Etapa.PLATAFORMA, "Recepción nómina de participantes", True, "Recepción Nómina Participantes"),
    (Etapa.PLATAFORMA, "Participantes inscritos en plataforma", True, "Participantes inscritos en plataforma"),
    (Etapa.PLATAFORMA, "Curso creado en plataforma", True, "Curso creado en plataforma"),
    (Etapa.PLATAFORMA, "Relator/a con acceso", False, "Relator/a con acceso"),
    (Etapa.PLATAFORMA, "Gestora OTEC con acceso", False, "Gestora OTEC con acceso"),
    (Etapa.PLATAFORMA, "Material cargado", False, "Material cargado"),
    (Etapa.PLATAFORMA, "Evaluación final configurada", False, "Evaluación final configurada"),
    (Etapa.PLATAFORMA, "Encuesta de satisfacción cargada", False, "Encuesta satisfacción cargada"),

    # --- Comunicación a participantes ---
    (Etapa.COMUNICACION, "Credenciales de acceso al curso", False, "Credenciales Acceso Curso"),
    (Etapa.COMUNICACION, "Correo de bienvenida", False, "Correo Bienvenida"),
    (Etapa.COMUNICACION, "Programa enviado a participantes", False, "Programa/planificación enviada a participantes"),
    (Etapa.COMUNICACION, "Enlace Zoom enviado", False, "Enlace Zoom enviado"),
    (Etapa.COMUNICACION, "Contacto de soporte informado", False, "Contacto soporte informado"),
    (Etapa.COMUNICACION, "Reglas de asistencia y certificación informadas", False, "Reglas asistencia/evaluación/certificación informadas"),

    # --- Ejecución ---
    (Etapa.EJECUCION, "Registro de asistencia disponible", False, "Registro de asistencia disponible"),
    (Etapa.EJECUCION, "Seguimiento de participación realizado", False, "Seguimiento de participación realizado"),
    (Etapa.EJECUCION, "Soporte a participantes registrado", False, "Soporte participantes registrado"),
    (Etapa.EJECUCION, "Coordinación con relator/a registrada", False, "Coordinación con relator/a registrada"),
    (Etapa.EJECUCION, "Evidencias de ejecución respaldadas", False, "Evidencias de ejecución respaldadas"),

    # --- Cierre ---
    (Etapa.CIERRE, "Encuesta aplicada", False, "Encuesta Aplicada"),
    (Etapa.CIERRE, "Informe final recibido", False, "Informe Final Recibido"),
    (Etapa.CIERRE, "Informe final enviado", False, "Informe Final Enviado"),
    (Etapa.CIERRE, "Registro gráfico disponible", False, "Registro gráfico disponible"),
    (Etapa.CIERRE, "Certificados emitidos", False, "Certificados emitidos"),
    (Etapa.CIERRE, "Carpeta de respaldo completa", False, "Carpeta respaldo completa"),
]

# Columna del Excel -> (etapa, nombre) del ítem correspondiente.
COLUMNAS_EXCEL = {columna: (etapa, nombre) for etapa, nombre, _, columna in CATALOGO}


def sincronizar_catalogo():
    """Crea o actualiza los ítems de la plantilla. Idempotente.

    Devuelve (creados, actualizados).
    """
    from .models import PlantillaItem

    creados = actualizados = 0
    for orden, (etapa, nombre, critico, _columna) in enumerate(CATALOGO, start=1):
        item, creado = PlantillaItem.objects.update_or_create(
            etapa=etapa,
            nombre=nombre,
            defaults={"orden": orden, "critico": critico, "activo": True},
        )
        if creado:
            creados += 1
        else:
            actualizados += 1
    return creados, actualizados

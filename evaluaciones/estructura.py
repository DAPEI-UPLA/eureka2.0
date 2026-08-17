"""Estructura institucional UPLA como árbol de cualquier profundidad.

Cada nodo es una rama (tiene "hijos") o un cargo evaluable ("cargo": True).
Un cargo con "instrumento" enlaza a la evaluación oficial ya construida; los
demás se evalúan con el instrumento genérico armado desde el texto del perfil.
Las raíces (vicerrectorías) llevan "color", que se usa como acento de la página.

Vive en código y no en la base porque es organigrama, no dato de operación: se
mueve por decreto, no por uso del sistema. El día que haya que editarlo desde
la pantalla, esto se convierte en modelo.
"""

from django.http import Http404

ARBOL = {
    "VAF": {
        "nombre": "Vicerrectoría de Administración y Finanzas",
        "color": "#0a66c2",
        "hijos": {
            "finanzas-presupuestos": {
                "nombre": "Dirección General de Finanzas y Presupuestos",
                "hijos": {
                    "director": {"nombre": "Director", "cargo": True, "area": "Jefatura"},
                    "presupuesto": {
                        "nombre": "Departamento de Presupuesto",
                        "hijos": {
                            "d3": {"nombre": "Director de Departamento", "cargo": True, "area": "Directivo", "perfil": ["presupuesto", "D3"]},
                            "t2": {"nombre": "Técnico Superior Senior", "cargo": True, "area": "Técnico", "perfil": ["presupuesto", "T2"]},
                            "a1": {"nombre": "Administrativo / Secretaria Senior", "cargo": True, "area": "Administrativo", "perfil": ["presupuesto", "A1"]},
                        },
                    },
                    "tesoreria": {
                        "nombre": "Departamento de Tesorería",
                        "hijos": {
                            "d3": {"nombre": "Director de Departamento", "cargo": True, "area": "Directivo", "perfil": ["tesoreria", "D3"]},
                            "p4": {"nombre": "Profesional Junior", "cargo": True, "area": "Profesional", "perfil": ["tesoreria", "P4"]},
                            "t2": {"nombre": "Técnico Superior Senior", "cargo": True, "area": "Técnico", "perfil": ["tesoreria", "T2"], "instrumento": "evaluaciones:instrumento"},
                            "a1": {"nombre": "Administrativo / Secretaria Senior", "cargo": True, "area": "Administrativo", "perfil": ["tesoreria", "A1"]},
                            "ax2": {"nombre": "Auxiliar de Servicio Senior", "cargo": True, "area": "Auxiliar", "perfil": ["tesoreria", "Ax2"]},
                        },
                    },
                    "contabilidad": {
                        "nombre": "Departamento de Contabilidad",
                        "hijos": {
                            "d3": {"nombre": "Director de Departamento", "cargo": True, "area": "Directivo", "perfil": ["contabilidad", "D3"]},
                            "p4": {"nombre": "Profesional Junior", "cargo": True, "area": "Profesional", "perfil": ["contabilidad", "P4"]},
                            "t2": {"nombre": "Técnico Superior Senior", "cargo": True, "area": "Técnico", "perfil": ["contabilidad", "T2"]},
                            "a1": {"nombre": "Administrativo / Secretaria Senior", "cargo": True, "area": "Administrativo", "perfil": ["contabilidad", "A1"]},
                        },
                    },
                },
            },
            "rrhh": {
                "nombre": "Dirección de Administración de Recursos Humanos",
                "hijos": {
                    "directora": {"nombre": "Directora", "cargo": True, "area": "Jefatura"},
                    "secretaria": {"nombre": "Secretaria", "cargo": True},
                    "analista-gestion-dotacion": {"nombre": "Analista de Gestión y Dotación", "cargo": True},
                    "reloj-control": {"nombre": "Reloj Control, Teletrabajo y Horas Compensadas", "cargo": True},
                    "vacaciones-comisiones": {
                        "nombre": "Vacaciones, Comisiones de Estudio, Comisiones de Servicio, "
                                  "Cargas Familiares y Permisos", "cargo": True},
                    "automatizacion-procesos": {
                        "nombre": "Automatización de Procesos de Recursos Humanos y Colaciones", "cargo": True},
                    "encargada-nombramientos": {"nombre": "Encargada de Nombramientos", "cargo": True},
                    "nombramientos-proyectos-eafi": {
                        "nombre": "Nombramientos de Proyectos, No Académicos y Académicos de las "
                                  "Facultades de Ciencias de la Actividad Física e Ingeniería", "cargo": True},
                    "grados-salud-arte-educacion": {
                        "nombre": "Grados Académicos y Nombramientos Académicos de las Facultades de "
                                  "Ciencias de la Salud, Arte y Ciencias de la Educación", "cargo": True},
                    "nombramientos-sociales-naturales-humanidades": {
                        "nombre": "Nombramientos Académicos de las Facultades de Ciencias Sociales, "
                                  "Ciencias Naturales y Humanidades", "cargo": True},
                    "encargada-honorarios": {"nombre": "Encargada de Honorarios", "cargo": True},
                    "honorarios-pregrado": {"nombre": "Honorarios Docentes de Pregrado", "cargo": True},
                    "honorarios-postgrado": {"nombre": "Honorarios Docentes de Postgrado", "cargo": True},
                    "honorarios-proyectos": {"nombre": "Honorarios de Proyectos", "cargo": True},
                    "capacitacion-interna": {"nombre": "Capacitación Interna", "cargo": True},
                    "calificaciones-declaraciones": {
                        "nombre": "Calificaciones y Declaraciones de Interés y Patrimonio", "cargo": True},
                    "concursos-induccion": {"nombre": "Concursos e inducción", "cargo": True},
                    "carrera-funcionaria": {"nombre": "Carrera Funcionaria", "cargo": True},
                },
            },
            "credito-aranceles": {"nombre": "Dirección de Administración General del Fondo de Crédito y Aranceles", "hijos": {}},
            "informatica": {"nombre": "Dirección General de Informática", "hijos": {}},
            "adquisiciones": {"nombre": "Sección de Adquisiciones", "hijos": {}},
            "inventario-bodega": {"nombre": "Sección de Inventario y Bodega", "hijos": {}},
            "infraestructura": {"nombre": "Dirección General de Infraestructura", "hijos": {}},
            "operaciones": {"nombre": "Dirección de Operaciones", "hijos": {}},
            "medios-audiovisuales": {"nombre": "Departamento de Medios Audiovisuales", "hijos": {}},
            "oficina-partes": {"nombre": "Oficina de Partes", "hijos": {}},
        },
    },
    "VRA": {"nombre": "Vicerrectoría Académica", "color": "#2e7d32", "hijos": {}},
    "VIPEI": {"nombre": "Vicerrectoría de Investigación, Postgrado e Innovación", "color": "#8e44ad", "hijos": {}},
    "RECT": {"nombre": "Rectoría", "color": "#b9770e", "hijos": {}},
}


def es_cargo(nodo):
    return nodo.get("cargo", False)


def recorrer(ruta):
    """Sigue la ruta ('VAF/rrhh/...') y devuelve (nodo, breadcrumb, color).

    Una ruta que no existe da 404 en vez de KeyError: la ruta viene de la URL,
    o sea del usuario, y cualquiera puede escribirla mal a mano.
    """
    ids = [p for p in ruta.split("/") if p]
    if not ids:
        raise Http404("Ruta vacía")

    nodo = {"hijos": ARBOL}
    breadcrumb, acumulado = [], []
    for pid in ids:
        hijos = nodo.get("hijos") or {}
        if pid not in hijos:
            raise Http404("Ruta no encontrada")
        nodo = hijos[pid]
        acumulado.append(pid)
        breadcrumb.append({"nombre": nodo["nombre"], "ruta": "/".join(acumulado)})

    return nodo, breadcrumb, ARBOL[ids[0]]["color"]


def raices():
    """Las vicerrectorías, para la portada del módulo."""
    return [{"sigla": sigla, "nombre": v["nombre"], "color": v["color"],
             "ruta": sigla, "n": len(v.get("hijos") or {})}
            for sigla, v in ARBOL.items()]

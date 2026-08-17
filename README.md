# Sistema PRISMA

> **PRISMA** — Plataforma de Reportabilidad, Indicadores y Seguimiento para la Mejora Administrativa.

## Descripción

**PRISMA** es una plataforma web desarrollada en **Django** para la Dirección de Análisis, Planificación y Estudios Institucionales (**DAPEI – UPLA**). Centraliza la gestión, planificación, seguimiento y análisis del quehacer institucional mediante indicadores, proyectos, iniciativas e informes.

El sistema está organizado en cuatro módulos funcionales que comparten autenticación, diseño y control de permisos por grupo:

1. **Planificación** — Programas estratégicos (PEI / PD) gestionados mediante objetivos, indicadores, estrategias, metas y seguimientos anuales, con una vista tipo tablero (similar a Monday).
2. **Proyectos** — Gestión de proyectos con fondos asociados (PACE, Fortalecimiento, Regionales, etc.), su presupuesto, objetivos, resultados, actividades, planes de gasto y egresos (compras, honorarios y viáticos).
3. **OCT** — Ciclo de vida de iniciativas: registro, envío a revisión, aprobación, formulación a fondos concursables, postulación y adjudicación, con bitácora de movimientos.
4. **Análisis** — Gestión de informes institucionales con flujo de revisión/aprobación, trazabilidad y visualización de gráficos.

El sistema incluye **control de permisos por grupo**, permitiendo que solo ciertos usuarios puedan crear, editar o eliminar elementos en cada módulo.

### Interfaz y diseño

El sistema incluye:

1. Dashboard de acceso por módulos.
2. Menú lateral.
3. Tarjetas de acceso rápido.
4. Secciones desplegables.
5. Vista de seguimiento tipo tablero con semáforo de cumplimiento (umbrales configurables por indicador).
6. Mapas de calor (heatmap) y comparación de programas.
7. Importación y exportación de datos vía Excel (plantillas `.xlsx`).

Localización en español de Chile (`es-cl`), zona horaria `America/Santiago` y separadores de miles/decimales chilenos.

---

## Estructura del proyecto

```
Prisma/
├── manage.py
├── requirements.txt
├── .env.example              # Plantilla de variables de entorno
├── db.sqlite3                # Base de datos (desarrollo)
│
├── sistema/                  # Configuración del proyecto Django
│   ├── settings.py           # Settings (seguridad por variables de entorno)
│   ├── urls.py               # Enrutamiento raíz + media protegida
│   └── wsgi.py
│
├── core/                     # Autenticación, home/dashboard y media protegida
│   ├── views.py              # login, home, logout, media_protegida
│   └── templates/core/       # base.html, login.html, home.html
│
├── planificacion/            # Programas (PEI/PD), objetivos, indicadores,
│   ├── models.py             #   estrategias, metas, seguimientos, cierres
│   ├── helpers.py            # Decoradores y chequeo de permisos (grupo "Planificacion")
│   └── templatetags/
│
├── proyectos/                # Proyectos, objetivos, resultados, actividades,
│   ├── models.py             #   planes de gasto y egresos
│   └── views/
│
├── oct/                      # Iniciativas, formulaciones y documentos
│   ├── models.py
│   └── signals.py
│
├── analisis/                 # Informes institucionales y trazabilidad
│   └── models.py
│
├── evaluaciones/             # Evaluación de desempeño: perfiles de cargo,
│   ├── motor.py              #   instrumento oficial (réplica del Excel) y
│   ├── estructura.py         #   organigrama institucional
│   └── perfiles.py
│
├── media/                    # Archivos subidos (servidos solo con sesión)
└── DESPLIEGUE_RASPBERRY.md   # Guía de despliegue en producción
```

### Modelos principales por módulo

| Módulo | Modelos clave |
|---|---|
| **planificacion** | `Programa`, `Objetivo`, `Indicador`, `Estrategia`, `ProgramaIndicador`, `MetaIndicador`, `SeguimientoIndicador`, `CierreAnual` |
| **proyectos** | `Proyecto`, `ObjetivoEspecifico`, `Resultado`, `Actividad`, `PlanDeGasto`, `Egreso`, catálogo de gastos (`Transferencia`, `TipoGasto`, `Gasto`, `GastoElegible`) |
| **oct** | `Iniciativa`, `Formulacion`, `DocumentoIniciativa`, `DocumentoFormulacion`, `MovimientoIniciativa` |
| **analisis** | `Informe`, `MovimientoInforme` |
| **evaluaciones** | `NivelRequerido` (el organigrama y los perfiles viven en archivos, no en la base) |

### Permisos por grupo

El acceso a las acciones de cada módulo se controla mediante grupos de Django (los superusuarios tienen acceso total):

| Grupo | Módulo |
|---|---|
| `Planificacion` | Planificación |
| `JefeProyectos` / `EncargadaProyectos` | Proyectos |
| Grupo de aprobadores OCT | OCT |
| `encargado_analisis` | Análisis |

Los grupos se crean y asignan desde el panel de administración de Django (`/admin/`).

---

## Tecnologías

- **Python 3.13** + **Django 6.0.2**
- **SQLite** como base de datos
- **openpyxl** para importación/exportación de Excel
- HTML + Bootstrap en las plantillas

---

# Cómo duplicar el proyecto

## 1. Clonar repositorio

```bash
git clone "https://github.com/DAPEI-UPLA/eureka2.0"
cd eureka2.0
```

## 2. Crear entorno virtual

**Windows**

```bash
python -m venv venv
venv\Scripts\activate
```

**Linux / macOS**

```bash
python3 -m venv venv
source venv/bin/activate
```

## 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

## 4. Configurar variables de entorno

Copia la plantilla y completa los valores:

```bash
cp .env.example .env
```

Para desarrollo local basta con `DJANGO_DEBUG=True`. En **producción** la variable `DJANGO_SECRET_KEY` es **obligatoria**; puedes generar una con:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

| Variable | Descripción |
|---|---|
| `DJANGO_SECRET_KEY` | Clave secreta (obligatoria con `DEBUG=False`) |
| `DJANGO_DEBUG` | `True` solo en desarrollo |
| `DJANGO_ALLOWED_HOSTS` | Hosts permitidos, separados por coma |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Orígenes de confianza tras proxy/HTTPS |
| `DJANGO_LOG_LEVEL` | Nivel de logging (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

## 5. Configurar la base de datos

Ejecutar migraciones:

```bash
python manage.py migrate
```

## 6. Crear superusuario

```bash
python manage.py createsuperuser
```

## 7. Ejecutar el servidor

```bash
python manage.py runserver
```

Abrir en el navegador:

```
http://127.0.0.1:8000
```

---

## Despliegue en producción

El sistema está desplegado en una **Raspberry Pi** usando **gunicorn** (vía `systemd`) y expuesto públicamente con **Tailscale Funnel** (HTTPS automático). El procedimiento completo —empaquetado, subida, migraciones, `collectstatic` y reinicio del servicio— está documentado en [`DESPLIEGUE_RASPBERRY.md`](./DESPLIEGUE_RASPBERRY.md).

> En producción, `settings.py` activa automáticamente el *hardening* de seguridad (HTTPS forzado, HSTS, cookies seguras, etc.) cuando `DJANGO_DEBUG=False`.

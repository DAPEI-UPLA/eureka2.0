# Sistema DAPEI
## Descripción:
El sistema DAPEI es una plataforma web desarrollada en Django para la gestión, planificación y seguimiento de programas estratégicos mediante indicadores.
El sistema permite:
1. Crear planes.
2. Definir objetivos.
3. Asociar indicadores.
4. Vincular estrategias.
5. Registrar seguimientos anuales.
6. Visualizar el progreso mediante una vista tipo tablero (Muy similar a Monday).
El sistema además incluye control de permisos por grupo, permitiendo que solo ciertos usuarios puedan crear, editar o eliminar elementos.




### Interfaz y diseño
El sistema incluye:
  1. Dashboard.
  2. Menú lateral.
  3. Tarjetas de acceso rápido.
  4. Secciones desplegables.



### Estructura del proyecto





# Cómo duplicar el proyecto

## 1. Clonar repositorio
```
git clone "url de github"
cd "nombre del proyecto"
```

## 2. Crear entorno virtual
Windows
```
python -m venv venv
venv\Scripts\activate
```
Linux
```
python3 -m venv venv
source venv\bin\activate
```

## 3. Instalar dependencias
```
pip install -r requirements.txt
```

## 4. Configurar base de datos
Ejecutar migraciones:
```
python manage.py migrate
```

## 5. Crear superusuario
```
python manage.py createsuperuser
```

## 6. Ejecutar el servidor
```
python manage.py runserver
```
Abrir en tu navegador:
```
http://127.0.0.1:8000
```

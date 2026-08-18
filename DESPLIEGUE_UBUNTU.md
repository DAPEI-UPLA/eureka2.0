# Despliegue de Prisma en servidor Ubuntu (SSH)

> Servidor: **`dapei@172.16.31.160`** — hostname `dapei1`, **Ubuntu 26.04 LTS**, red interna.
> Arquitectura: **nginx** (puerto 80) → **gunicorn** (`127.0.0.1:8000`) → **Django 6.0 + SQLite**.
> nginx sirve directamente `/static/` y `/media/`.
> Estado: **desplegado y funcionando** (2026-08-03).

Tamaños de referencia: el proyecto sin `venv` pesa **~20 MB** (`media/` 15 MB, `db.sqlite3` 1 MB),
y el `venv` en el servidor ocupa ~55 MB.

Hay dos scripts que automatizan esto, en la raíz del proyecto:

| Script | Qué hace |
|---|---|
| `setup_ubuntu.sh` | Pasos 4 a 9 completos (venv, env, migraciones, systemd, nginx, ufw). Idempotente |
| `ampliar_disco.sh` | Paso 1: detecta LVM o partición directa y amplía la raíz |

---

## Paso -1 — Migración de nombres (Eureka → Prisma)

> ⚠️ **Este documento ya usa los nombres nuevos, pero el servidor todavía no.**
> El despliegue del 2026-08-03 quedó con `eureka.service`, `/etc/eureka.env`,
> `~/Eureka` y el sitio nginx `eureka`. Hasta correr esta migración, lee
> `eureka` donde el documento dice `prisma`.
>
> Solo aplica a servidores ya desplegados. En una instalación nueva,
> `setup_ubuntu.sh` ya crea todo con los nombres nuevos.

```bash
sudo systemctl stop eureka.service

# Proyecto, variables de entorno y unidad systemd
mv ~/Eureka ~/Prisma
sudo mv /etc/eureka.env /etc/prisma.env
sudo mv /etc/systemd/system/eureka.service /etc/systemd/system/prisma.service
sudo sed -i 's|/Eureka|/Prisma|g; s|/etc/eureka\.env|/etc/prisma.env|; s|^Description=Eureka|Description=Prisma|' \
    /etc/systemd/system/prisma.service

# nginx
sudo mv /etc/nginx/sites-available/eureka /etc/nginx/sites-available/prisma
sudo rm -f /etc/nginx/sites-enabled/eureka
sudo ln -sfn /etc/nginx/sites-available/prisma /etc/nginx/sites-enabled/prisma
sudo sed -i 's|/Eureka/|/Prisma/|g' /etc/nginx/sites-available/prisma

# cron del respaldo diario
crontab -l | sed 's|/Eureka/|/Prisma/|g' | crontab -

# Levantar
sudo systemctl daemon-reload
sudo systemctl disable eureka.service 2>/dev/null || true
sudo systemctl enable --now prisma.service
sudo nginx -t && sudo systemctl reload nginx
```

Comprobación:

```bash
systemctl is-active prisma.service     # active
curl -sI http://172.16.31.160/ | head -1   # HTTP/1.1 200 OK
crontab -l | grep backup.sh            # debe decir /Prisma/
```

Si algo falla, se vuelve atrás deshaciendo los `mv` y reactivando `eureka.service`.

### En el equipo local (Windows)

Este documento asume que la carpeta del proyecto es `%USERPROFILE%\Desktop\Prisma`.
Con el editor y las terminales cerradas:

```powershell
Rename-Item "$env:USERPROFILE\Desktop\Eureka" "Prisma"
```

El `venv` guarda rutas absolutas, así que después hay que recrearlo:

```powershell
cd "$env:USERPROFILE\Desktop\Prisma"
Remove-Item -Recurse -Force venv
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
```

---

## Paso 0 — Comprobación previa: versión de Python

**Django 6.0 requiere Python ≥ 3.12.**

```bash
ssh dapei@172.16.31.160
lsb_release -a
python3 --version
```

En Ubuntu 26.04 esto ya está cubierto. Si algún día se despliega en Ubuntu 22.04
(Python 3.10), Django 6.0 **no** funciona: hay que instalar 3.12 desde
`ppa:deadsnakes` o bajar a `Django==5.2.*`.

---

## Paso 1 — Ampliar el disco

### Lo que pasó en este servidor

El disco es un **NVMe de 1,8 TB**, pero el instalador de Ubuntu creó el volumen
lógico de solo **100 GB** (su comportamiento por defecto) y dejó **1,72 TB libres
dentro del volume group**. La partición `nvme0n1p3` ya cubría todo el disco, así que
**no hizo falta `growpart` ni `pvresize`** — solo estirar el LV y el sistema de archivos:

```bash
sudo lvextend -l +100%FREE /dev/ubuntu-vg/ubuntu-lv
sudo resize2fs /dev/ubuntu-vg/ubuntu-lv
df -h /
```

Resultado: raíz de **98 G → 1,8 T**. Todo en caliente, sin reiniciar ni detener el servicio.

> De los 12 GB usados en la instalación base, ~3,5 GB son directorios
> (`/usr` 2,9 G, `/var` 449 M, `/home` 123 M) y los ~8,5 GB restantes son
> `/swap.img`. Es normal, no hay nada que limpiar.

### Diagnóstico para otros casos

```bash
lsblk -o NAME,SIZE,FSTYPE,TYPE,MOUNTPOINTS; df -h /; sudo vgs; sudo pvs
```

| Situación | Comandos |
|---|---|
| LVM con `VFree > 0` (este caso) | `lvextend -l +100%FREE` + `resize2fs` |
| LVM con `VFree = 0` y disco con espacio sin asignar | `growpart <disco> <n>` → `pvresize` → `lvextend` → `resize2fs` |
| Partición ext4 directa, sin LVM | `growpart <disco> <n>` → `resize2fs` |

`growpart` viene en el paquete `cloud-guest-utils`. El script `ampliar_disco.sh`
detecta el caso solo y pide confirmación antes de tocar nada.

> Si se quiere reservar espacio para **snapshots LVM** (respaldos consistentes en
> caliente), usar `lvextend -L +1.5T` en vez de `-l +100%FREE` y dejar el resto libre.

---

## Paso 2 — Paquetes base y zona horaria

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip nginx sqlite3 rsync ufw
sudo timedatectl set-timezone America/Santiago
```

---

## Paso 3 — Empaquetar y subir el proyecto (desde Windows)

En **PowerShell** de tu máquina. Este es el primer despliegue, así que **sí** se sube
`db.sqlite3` y `media/` (en redespliegues futuros, no — ver Paso 12).

```powershell
cd "$env:USERPROFILE\Desktop\Prisma"
tar -czf "$env:TEMP\prisma.tar.gz" --exclude=venv --exclude=staticfiles --exclude=__pycache__ --exclude=*.pyc --exclude=.git --exclude=.env --exclude=.claude --exclude=db.sqlite3.bak-* .
scp "$env:TEMP\prisma.tar.gz" dapei@172.16.31.160:~/
```

En el **servidor**:

```bash
mkdir -p ~/Prisma
tar -xzf ~/prisma.tar.gz -C ~/Prisma
cd ~/Prisma && ls -la
```

Permiso de tránsito para que nginx (usuario `www-data`) pueda leer los estáticos:

```bash
chmod o+x /home/dapei          # permite atravesar, no listar
```

---

## Paso 4 — Entorno virtual y dependencias

```bash
cd ~/Prisma
python3 -m venv venv           # o python3.12 -m venv venv si instalaste deadsnakes
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
venv/bin/pip install gunicorn==23.0.0
```

---

## Paso 5 — Variables de entorno (`/etc/prisma.env`)

Genera la clave secreta:

```bash
cd ~/Prisma
venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Crea el archivo (pega la clave generada en `DJANGO_SECRET_KEY`):

```bash
sudo nano /etc/prisma.env
```

```ini
DJANGO_SECRET_KEY=pega-aqui-la-clave-generada
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=172.16.31.160,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://172.16.31.160
DJANGO_SECURE_SSL_REDIRECT=False
DJANGO_LOG_LEVEL=INFO
```

```bash
sudo chmod 600 /etc/prisma.env
sudo chown root:root /etc/prisma.env
```

> ⚠️ **`DJANGO_SECURE_SSL_REDIRECT=False` es imprescindible mientras sirvas por HTTP plano.**
> Con `True`, Django redirige todo a `https://` (bucle infinito) y marca las cookies de
> sesión/CSRF como `Secure`, así que el login nunca funcionaría. Cuando pongas un
> certificado (dominio interno + Let's Encrypt, o cert propio), cámbialo a `True`
> y actualiza `DJANGO_CSRF_TRUSTED_ORIGINS` a `https://...`.
>
> ⚠️ En `/etc/prisma.env` **no** uses comillas ni escapes: systemd toma todo lo que va
> tras el primer `=` como valor literal. Si necesitas cargarlo en una shell, hazlo
> línea por línea (ver Paso 12), nunca con `source`.

---


## Antes de migrar el POA al resultado (migraciones 0020–0028)

Este grupo de migraciones mueve el plan de gasto desde la actividad al
resultado, y elimina el presupuesto de las actividades. **Sobre una base con
datos hay un caso que hace fallar la migración a medio camino**, así que
primero se revisa:

```bash
cd /opt/prisma
venv/bin/python manage.py revisar_migracion_poa
```

No modifica nada. Informa tres cosas:

1. **Lo que bloquea.** La restricción nueva es `(resultado, gasto elegible,
   año)`; la vieja era `(actividad, gasto elegible, año)`. Dos actividades del
   mismo resultado con la misma línea son legales hoy y chocan al fusionarse:
   `migrate` aborta con `UNIQUE constraint failed`. Hay que fusionar esos
   planes en uno solo sumando sus montos, o moverlos a años distintos, antes
   de migrar.

2. **Lo que se pierde.** El presupuesto de cada actividad, que es el reparto
   interno del resultado y es justo lo que se decidió dejar de llevar. El
   presupuesto del resultado no cambia. Si se quiere de referencia, exportarlo
   antes.

3. **Lo que queda por revisar.** Las migraciones dejan todo el presupuesto
   concentrado en el primer año a propósito. Hasta que cada equipo reparta sus
   años, los planes de los demás años quedan sin respaldo y no se podrán
   editar.

Respaldo obligatorio antes de correr `migrate`:

```bash
cp db.sqlite3 db.sqlite3.bak-$(date +%Y%m%d-%H%M)
```


## Paso 6 — Migraciones, estáticos y superusuario

```bash
cd ~/Prisma
# Cargar el entorno en esta sesión de shell (línea por línea, por los caracteres especiales)
set -a
while IFS= read -r line; do
  case "$line" in ''|\#*) continue ;; esac
  export "${line%%=*}=${line#*=}"
done < <(sudo cat /etc/prisma.env)
set +a

venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
venv/bin/python manage.py createsuperuser      # solo si necesitas un usuario nuevo
venv/bin/python manage.py check --deploy
```

> Si subiste tu `db.sqlite3` local, tus usuarios y datos ya están ahí:
> `createsuperuser` solo hace falta si quieres una cuenta adicional.

---

## Paso 7 — Servicio systemd (gunicorn)

```bash
sudo nano /etc/systemd/system/prisma.service
```

```ini
[Unit]
Description=Prisma (Django + gunicorn)
After=network.target

[Service]
User=dapei
Group=dapei
WorkingDirectory=/home/dapei/Prisma
EnvironmentFile=/etc/prisma.env
ExecStart=/home/dapei/Prisma/venv/bin/gunicorn sistema.wsgi:application \
    --workers 3 \
    --bind 127.0.0.1:8000 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now prisma.service
systemctl status prisma.service --no-pager
curl -s -o /dev/null -w "gunicorn: HTTP %{http_code}\n" http://127.0.0.1:8000/
```

---

## Paso 8 — nginx como proxy inverso

```bash
sudo nano /etc/nginx/sites-available/prisma
```

```nginx
server {
    listen 80;
    server_name 172.16.31.160;

    client_max_body_size 25M;

    location /static/ {
        alias /home/dapei/Prisma/staticfiles/;
        access_log off;
        expires 30d;
    }

    location /media/ {
        alias /home/dapei/Prisma/media/;
        access_log off;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/prisma /etc/nginx/sites-enabled/prisma
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

---

## Paso 9 — Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw --force enable
sudo ufw status
```

---

## Paso 10 — Verificación

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://172.16.31.160/
```

`200` o `302` = OK. Luego abre en el navegador:

## 🔗 http://172.16.31.160/

Revisa que carguen los CSS (estáticos vía nginx) y que el login funcione.
El admin queda en `http://172.16.31.160/admin/`.

---

## Paso 11 — Respaldo automático

La lógica vive en **`scripts/backup.sh`** (versionado en el proyecto, así viaja en cada
despliegue). Respalda la base con `sqlite3 .backup` — consistente aunque gunicorn la esté
usando, a diferencia de un `cp` — verifica el resultado con `PRAGMA integrity_check`, la
comprime, empaqueta `media/` y aplica retención (30 días la base, 7 días media).

Instalar el cron (una sola vez, sin abrir el editor):

```bash
chmod +x ~/Prisma/scripts/backup.sh
( crontab -l 2>/dev/null | grep -Fv 'Prisma/scripts/backup.sh'; \
  echo '0 2 * * * /home/dapei/Prisma/scripts/backup.sh >> /home/dapei/Prisma/backups/backup.log 2>&1' \
) | crontab -
crontab -l
```

> El `date` va **dentro** del script, no en la línea del crontab: así se evita tener que
> escapar el `%` (en crontab `%` es un carácter especial y rompe el comando).

Probar y revisar:

```bash
bash ~/Prisma/scripts/backup.sh     # ejecución manual
ls -lh ~/Prisma/backups/
tail -n 5 ~/Prisma/backups/backup.log
```

### Restaurar

```bash
sudo systemctl stop prisma.service
cd ~/Prisma
mv db.sqlite3 db.sqlite3.antes-de-restaurar
gunzip -c backups/db_2026-08-03_0200.sqlite3.gz > db.sqlite3
tar -xzf backups/media_2026-08-03_0200.tar.gz -C .   # solo si también hay que recuperar archivos
sudo systemctl start prisma.service
```

### Bajar un respaldo a Windows

```powershell
scp dapei@172.16.31.160:~/Prisma/backups/db_2026-08-03_0200.sqlite3.gz "$env:USERPROFILE\Desktop\"
```

> `/etc/prisma.env` **no** se respalda (el script corre como `dapei` y el archivo es solo
> de root). Si se perdiera, basta generar una `SECRET_KEY` nueva: el único efecto es que
> las sesiones activas se cierran. Los datos no dependen de ella.

---

## Paso 12 — Redespliegues futuros (solo código)

**Regla de oro:** nunca sobrescribas en el servidor `db.sqlite3`, `media/`, `venv/`,
`staticfiles/`, `backups/` ni `/etc/prisma.env`.

En Windows:

```powershell
cd "$env:USERPROFILE\Desktop\Prisma"
tar -czf "$env:TEMP\prisma.tar.gz" --exclude=venv --exclude=db.sqlite3* --exclude=*.sqlite3 --exclude=media --exclude=staticfiles --exclude=backups --exclude=__pycache__ --exclude=*.pyc --exclude=.git --exclude=.env --exclude=.claude .
scp "$env:TEMP\prisma.tar.gz" dapei@172.16.31.160:~/
```

En el servidor:

```bash
cd ~/Prisma
cp db.sqlite3 backups/db_pre_deploy_$(date +%F_%H%M).sqlite3
tar -xzf ~/prisma.tar.gz -C ~/Prisma
venv/bin/pip install -r requirements.txt

set -a
while IFS= read -r line; do
  case "$line" in ''|\#*) continue ;; esac
  export "${line%%=*}=${line#*=}"
done < <(sudo cat /etc/prisma.env)
set +a

venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart prisma.service
systemctl is-active prisma.service
```

---

## Paso 13 — Acceso SSH sin contraseña (opcional, recomendado)

Desde Windows:

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\id_ed25519_dapei" -C "prisma-deploy"
type "$env:USERPROFILE\.ssh\id_ed25519_dapei.pub" | ssh dapei@172.16.31.160 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

Agrega a `%USERPROFILE%\.ssh\config`:

```
Host prisma
    HostName 172.16.31.160
    User dapei
    IdentityFile ~/.ssh/id_ed25519_dapei
```

Desde ahí basta `ssh prisma` y `scp archivo prisma:~/`.

---

## Comandos de mantenimiento

```bash
# Estado y logs de la app
systemctl status prisma.service
journalctl -u prisma -n 100 --no-pager
journalctl -u prisma -f

# nginx
sudo nginx -t && sudo systemctl reload nginx
sudo tail -f /var/log/nginx/error.log

# Reiniciar todo
sudo systemctl restart prisma.service nginx

# Espacio en disco
df -h /
du -sh ~/Prisma/*
```

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| `ERR_TOO_MANY_REDIRECTS` | `DJANGO_SECURE_SSL_REDIRECT` quedó en `True` sirviendo HTTP → ponlo en `False` y reinicia el servicio |
| Login "no hace nada" | Cookies marcadas `Secure` por HTTP → misma causa que arriba |
| `DisallowedHost` en los logs | Falta la IP/dominio en `DJANGO_ALLOWED_HOSTS` |
| `403 CSRF verification failed` | Falta el origen en `DJANGO_CSRF_TRUSTED_ORIGINS` (con esquema `http://`) |
| Página sin estilos, 404 en `/static/...` | Falta `collectstatic`, o `www-data` no puede atravesar `/home/dapei` → `chmod o+x /home/dapei` |
| `502 Bad Gateway` | gunicorn caído → `journalctl -u prisma -n 50` |
| `ImproperlyConfigured: Falta DJANGO_SECRET_KEY` | El servicio no está leyendo `/etc/prisma.env`, o lo ejecutaste a mano sin cargar el entorno |
| `attempt to write a readonly database` | Permisos: `db.sqlite3` y su carpeta deben pertenecer a `dapei` |

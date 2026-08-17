# Despliegue de Prisma en la Raspberry Pi

> Documento de la sesión del **2026-06-16**. Resume cómo quedó montado el servidor
> y cómo repetir el despliegue en el futuro.

---

## 0. Migración de nombres (Eureka → Prisma)

> ⚠️ **Este documento ya usa los nombres nuevos, pero el servidor todavía no.**
> El despliegue original quedó con `eureka.service`, `/etc/eureka.env` y
> `~/Eureka`. Hasta correr esta migración, lee `eureka` donde el documento
> dice `prisma`.

La Pi no usa nginx (la expone Tailscale Funnel), así que la migración es corta:

```bash
sudo systemctl stop eureka.service

mv ~/Eureka ~/Prisma
sudo mv /etc/eureka.env /etc/prisma.env
sudo mv /etc/systemd/system/eureka.service /etc/systemd/system/prisma.service

sudo sed -i 's|/Eureka|/Prisma|g; s|/etc/eureka\.env|/etc/prisma.env|; s|^Description=Eureka|Description=Prisma|' \
    /etc/systemd/system/prisma.service

sudo systemctl daemon-reload
sudo systemctl disable eureka.service 2>/dev/null || true
sudo systemctl enable --now prisma.service

systemctl is-active prisma.service
curl -sI http://127.0.0.1:8000/ | head -1
```

El túnel de Tailscale no se toca: apunta al puerto 8000, no al nombre del servicio.
Tampoco cambia la URL pública.

Si algo falla, se vuelve atrás deshaciendo los `mv` y reactivando `eureka.service`.

---

## 1. Datos del servidor

| Dato | Valor |
|---|---|
| Host SSH | `claudio745@bot.local` |
| Acceso | Por **contraseña** (login interactivo desde una terminal real) |
| Equipo | Raspberry Pi (ARM), Python 3.13 en venv |
| Ruta del proyecto | `/home/claudio745/Prisma` |
| Servicio web | `prisma.service` (systemd) → gunicorn `sistema.wsgi:application`, 3 workers, `127.0.0.1:8000`, usuario `claudio745` |
| Variables de entorno | `/etc/prisma.env` (solo root, `rw-------`) |
| Settings de Django | `sistema.settings` |

> ⚠️ **Nota SSH:** el login con contraseña solo funciona desde una terminal real
> (no desde herramientas no interactivas, porque no hay TTY para escribir la clave).
> Se intentó configurar una clave SSH pero el servidor la rechazaba; quedó pendiente.

---

## 2. URL pública fija (Tailscale Funnel)

## 🔗 https://bot.tailac71f1.ts.net/

- Montada con **Tailscale Funnel** (`sudo tailscale funnel --bg 8000`): expone el
  puerto 443 público y lo reenvía a `127.0.0.1:8000` (gunicorn), con **HTTPS automático**.
- Tailnet de la cuenta **`claudioalfaro745@gmail.com`**, máquina **"bot"**.
- **Es permanente** y sobrevive a reinicios (tailscaled arranca al boot y restaura la
  config de Funnel; `prisma.service` está `enabled`).
- ⚠️ **No renombrar el dispositivo "bot"** en el panel de Tailscale, o cambiaría la URL.

### ¿Por qué Tailscale y no No-IP?
El ISP usa **CGNAT**: la WAN del router es `6.6.6.6` pero la IP pública real es
`186.78.151.95` (no coinciden). Por eso **no se pueden abrir puertos** y No-IP / DDNS
no eran viables. Tailscale Funnel funciona como túnel de salida, sin abrir puertos.

### Túnel viejo de Cloudflare
`cloudflared-eureka.service` era un *quick tunnel* que generaba una URL aleatoria
distinta en cada reinicio (de ahí que la URL "cambiara"). Quedó **redundante**.
Para desactivarlo:
```bash
sudo systemctl disable --now cloudflared-eureka.service
```

---

## 3. Configuración de hosts/CSRF en `/etc/prisma.env`

```
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=.trycloudflare.com,localhost,127.0.0.1,bot.tailac71f1.ts.net
DJANGO_CSRF_TRUSTED_ORIGINS=https://bot.tailac71f1.ts.net
```
(además contiene `DJANGO_SECRET_KEY`, no mostrada).

> El `settings.py` lee `DJANGO_ALLOWED_HOSTS` y `DJANGO_CSRF_TRUSTED_ORIGINS` del
> entorno (separados por coma). En producción aplica `SECURE_SSL_REDIRECT` +
> `SECURE_PROXY_SSL_HEADER` (confía en `X-Forwarded-Proto`), compatible con Funnel.

> ⚠️ `DJANGO_SECRET_KEY` contiene espacios y caracteres especiales (`% # @ +`), por lo
> que **NO** se puede cargar con `source` de bash. Hay que leer el archivo línea por
> línea tomando todo lo que va tras el primer `=` como valor literal (ver Paso 3 abajo).

---

## 4. Procedimiento de despliegue (subir código nuevo)

**Regla de oro:** subir **solo el código**. NUNCA sobrescribir en la Pi:
`db.sqlite3`, `media/`, `venv/`, `staticfiles/`, `backups/` ni `/etc/prisma.env`.

### Paso 1 — Empaquetar en local (Windows, Git Bash)
```bash
tar -czf /c/Users/claud/Desktop/prisma_deploy.tar.gz \
  --exclude='venv' --exclude='db.sqlite3*' --exclude='*.sqlite3' --exclude='media' \
  --exclude='staticfiles' --exclude='backups' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='.env' --exclude='.git' --exclude='.claude' .
```

### Paso 2 — Subir (PowerShell de Windows, pide contraseña)
```powershell
scp "$env:USERPROFILE\Desktop\prisma_deploy.tar.gz" claudio745@bot.local:~/prisma_deploy.tar.gz
```

### Paso 3 — Desplegar (en la Raspberry)
```bash
# Backup de la base de datos de producción
mkdir -p ~/Prisma/backups
cp ~/Prisma/db.sqlite3 ~/Prisma/backups/db_pre_deploy_$(date +%F_%H%M).sqlite3

# Extraer el código encima (no toca DB/media/venv)
tar -xzf ~/prisma_deploy.tar.gz -C ~/Prisma
cd ~/Prisma

# Dependencias
venv/bin/pip install -r requirements.txt

# Cargar el entorno (línea por línea por los caracteres especiales del SECRET_KEY)
while IFS= read -r line; do
  case "$line" in ''|\#*) continue ;; esac
  export "${line%%=*}=${line#*=}"
done < <(sudo cat /etc/prisma.env)

# Migraciones y estáticos
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput

# Reiniciar
sudo systemctl restart prisma.service
systemctl is-active prisma.service
```

### Paso 4 — Verificar
```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://bot.tailac71f1.ts.net/
```
`200` o `302` = OK. Luego abrir la URL en el navegador.

---

## 5. Comandos útiles de mantenimiento

```bash
# Estado del servicio y logs
systemctl status prisma.service
journalctl -u prisma -n 50

# Estado de Tailscale / Funnel
tailscale status
sudo tailscale funnel status

# Reactivar Funnel si hiciera falta
sudo tailscale funnel --bg 8000
```

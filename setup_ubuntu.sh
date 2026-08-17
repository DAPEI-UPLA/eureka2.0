#!/usr/bin/env bash
#
# Instalación de Prisma en un servidor Ubuntu limpio.
# Cubre los pasos 4 a 9 de DESPLIEGUE_UBUNTU.md: venv, dependencias, variables de
# entorno, migraciones, estáticos, servicio systemd, nginx y firewall.
#
# Uso (como el usuario dapei, con sudo disponible):
#     bash ~/setup_ubuntu.sh
#
# Es idempotente: se puede volver a correr sin perder la base de datos ni la
# SECRET_KEY ya generada.

set -euo pipefail

APP_USER="$(id -un)"
APP_DIR="$HOME/Prisma"
TARBALL="$HOME/prisma.tar.gz"
SERVER_IP="172.16.31.160"
ENV_FILE="/etc/prisma.env"
SERVICE="prisma.service"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 0. requisitos
say "Comprobando requisitos"

[ -f "$TARBALL" ] || [ -d "$APP_DIR" ] || die "No encuentro $TARBALL ni $APP_DIR. Sube el tar primero."

sudo -v || die "Este script necesita sudo."

# ------------------------------------------------------------------ 1. paquetes
say "Instalando paquetes del sistema"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3-venv python3-pip nginx sqlite3 rsync ufw curl
sudo timedatectl set-timezone America/Santiago

PYV="$(python3 -c 'import sys; print("%d%02d" % sys.version_info[:2])')"
if [ "$PYV" -lt 312 ]; then
    die "Django 6.0 requiere Python >= 3.12 y este sistema tiene $(python3 --version).
     Opciones: instalar python3.12 (ppa:deadsnakes) o bajar a Django==5.2 en requirements.txt."
fi
echo "    Python: $(python3 --version)"

# --------------------------------------------------------- 2. extraer el código
if [ -f "$TARBALL" ]; then
    say "Extrayendo el proyecto en $APP_DIR"
    mkdir -p "$APP_DIR/backups"
    if [ -f "$APP_DIR/db.sqlite3" ]; then
        BK="$APP_DIR/backups/db_pre_setup_$(date +%F_%H%M).sqlite3"
        sqlite3 "$APP_DIR/db.sqlite3" ".backup '$BK'"
        echo "    Respaldo previo de la BD: $BK"
    fi
    tar -xzf "$TARBALL" -C "$APP_DIR"
fi

# nginx (www-data) necesita atravesar el home para leer staticfiles/ y media/
chmod o+x "$HOME"

# --------------------------------------------------------- 3. venv y dependencias
say "Creando el entorno virtual e instalando dependencias"
cd "$APP_DIR"
[ -d venv ] || python3 -m venv venv
venv/bin/pip install --upgrade -q pip
venv/bin/pip install -q -r requirements.txt
venv/bin/pip install -q 'gunicorn>=23.0'
echo "    Django: $(venv/bin/python -c 'import django; print(django.get_version())')"
echo "    gunicorn: $(venv/bin/gunicorn --version)"

# ------------------------------------------------------- 4. variables de entorno
if sudo test -f "$ENV_FILE"; then
    say "$ENV_FILE ya existe: lo conservo tal cual"
else
    say "Generando $ENV_FILE con una SECRET_KEY nueva"
    SECRET="$(venv/bin/python -c 'from django.core.management.utils import get_random_secret_key as k; print(k())')"
    sudo tee "$ENV_FILE" > /dev/null <<EOF
DJANGO_SECRET_KEY=$SECRET
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=$SERVER_IP,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://$SERVER_IP
DJANGO_SECURE_SSL_REDIRECT=False
DJANGO_LOG_LEVEL=INFO
EOF
    sudo chown root:root "$ENV_FILE"
    sudo chmod 600 "$ENV_FILE"
fi

# Cargar el entorno en esta shell: línea por línea, tomando todo lo que va tras el
# primer '=' como valor literal (la SECRET_KEY puede traer % # @ + y espacios).
while IFS= read -r line; do
    case "$line" in ''|\#*) continue ;; esac
    export "${line%%=*}=${line#*=}"
done < <(sudo cat "$ENV_FILE")

# ------------------------------------------------- 5. migraciones y estáticos
say "Aplicando migraciones"
venv/bin/python manage.py migrate --noinput

say "Recolectando archivos estáticos"
venv/bin/python manage.py collectstatic --noinput --clear

# --------------------------------------------------------- 6. servicio systemd
say "Instalando $SERVICE"
sudo tee "/etc/systemd/system/$SERVICE" > /dev/null <<EOF
[Unit]
Description=Prisma (Django + gunicorn)
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/venv/bin/gunicorn sistema.wsgi:application \\
    --workers 3 \\
    --bind 127.0.0.1:8000 \\
    --timeout 60 \\
    --access-logfile - \\
    --error-logfile -
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable -q "$SERVICE"
sudo systemctl restart "$SERVICE"

sleep 3
systemctl is-active --quiet "$SERVICE" \
    || die "$SERVICE no arrancó. Revisa: journalctl -u prisma -n 50 --no-pager"

# ------------------------------------------------------------------- 7. nginx
say "Configurando nginx"
sudo tee /etc/nginx/sites-available/prisma > /dev/null <<EOF
server {
    listen 80;
    server_name $SERVER_IP;

    client_max_body_size 25M;

    location /static/ {
        alias $APP_DIR/staticfiles/;
        access_log off;
        expires 30d;
    }

    location /media/ {
        alias $APP_DIR/media/;
        access_log off;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
    }
}
EOF

sudo ln -sfn /etc/nginx/sites-available/prisma /etc/nginx/sites-enabled/prisma
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

# ---------------------------------------------------------------- 8. firewall
say "Configurando el firewall"
sudo ufw allow OpenSSH   > /dev/null
sudo ufw allow 80/tcp    > /dev/null
sudo ufw --force enable  > /dev/null
sudo ufw status | head -n 8

# ------------------------------------------------------------ 9. verificación
say "Verificando"
G="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/ || echo 000)"
N="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/     || echo 000)"
echo "    gunicorn (127.0.0.1:8000) -> HTTP $G"
echo "    nginx    (127.0.0.1:80)   -> HTTP $N"

case "$N" in
    200|302) printf '\n\033[1;32m LISTO. Abre http://%s/ en el navegador.\033[0m\n' "$SERVER_IP" ;;
    *)       printf '\n\033[1;33m nginx respondió %s. Revisa:\n   journalctl -u prisma -n 50 --no-pager\n   sudo tail -n 30 /var/log/nginx/error.log\033[0m\n' "$N" ;;
esac

cat <<EOF

Siguientes pasos manuales (opcionales):
  * Crear un usuario admin adicional:
      cd $APP_DIR && venv/bin/python manage.py createsuperuser
  * Respaldo diario automático (paso 11 de DESPLIEGUE_UBUNTU.md):
      crontab -e
EOF

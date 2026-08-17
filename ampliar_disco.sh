#!/usr/bin/env bash
#
# Amplía el sistema de archivos raíz hacia el espacio libre del disco.
# Detecta solo si la raíz está sobre LVM o sobre una partición directa.
#
# Uso:   bash ~/ampliar_disco.sh
#
# Todas las operaciones son de CRECIMIENTO (growpart / pvresize / lvextend /
# resize2fs). Ninguna borra ni reduce datos, y funcionan en caliente sin
# desmontar ni reiniciar. Aun así: si el servidor es una VM, toma un snapshot
# antes de correr esto.

set -euo pipefail

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m    %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

sudo -v || die "Necesito sudo."

# ------------------------------------------------------------ estado inicial
say "Estado actual"
lsblk -o NAME,SIZE,FSTYPE,TYPE,MOUNTPOINTS
echo
df -h /
ANTES="$(df -h --output=size / | tail -n1 | tr -d ' ')"

# ------------------------------------------------------------ detección
ROOT_SRC="$(findmnt -no SOURCE /)"
FSTYPE="$(findmnt -no FSTYPE /)"

case "$FSTYPE" in
    ext2|ext3|ext4|xfs) : ;;
    *) die "Sistema de archivos '$FSTYPE' no soportado por este script." ;;
esac

if sudo lvs "$ROOT_SRC" &>/dev/null; then
    MODE="lvm"
    LV="$ROOT_SRC"
    VG="$(sudo lvs --noheadings -o vg_name "$LV" | tr -d ' ')"
    PART="$(sudo pvs --noheadings -o pv_name --select "vg_name=$VG" | tr -d ' ' | head -n1)"
    [ -n "$PART" ] || die "No pude identificar el physical volume del VG $VG."
else
    MODE="plain"
    PART="$ROOT_SRC"
fi

PART_NAME="$(basename "$PART")"
[ -f "/sys/class/block/$PART_NAME/partition" ] \
    || die "$PART no parece una partición. Revisa 'lsblk' y hazlo a mano."
PARTNUM="$(cat "/sys/class/block/$PART_NAME/partition")"
DISK="/dev/$(lsblk -no PKNAME "$PART" | head -n1)"

# ------------------------------------------------------------ plan
say "Plan detectado"
cat <<EOF
    Esquema      : $MODE
    Raíz         : $ROOT_SRC  ($FSTYPE, $ANTES)
    Partición    : $PART  (partición $PARTNUM de $DISK)
EOF
[ "$MODE" = "lvm" ] && echo "    Volume group : $VG"
echo
echo "    Se ejecutará:"
echo "      1. growpart $DISK $PARTNUM        (crece la partición al espacio libre)"
if [ "$MODE" = "lvm" ]; then
    echo "      2. pvresize $PART                 (el LVM reconoce el nuevo tamaño)"
    echo "      3. lvextend -l +100%FREE $LV      (crece el volumen lógico)"
    TARGET="$LV"
else
    TARGET="$PART"
fi
if [ "$FSTYPE" = "xfs" ]; then
    echo "      4. xfs_growfs /                   (crece el sistema de archivos)"
else
    echo "      4. resize2fs $TARGET              (crece el sistema de archivos)"
fi

echo
read -r -p "    ¿Continuar? (escribe SI): " OK
[ "$OK" = "SI" ] || { echo "    Cancelado, no se tocó nada."; exit 0; }

# ------------------------------------------------------------ ejecución
say "Instalando growpart"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cloud-guest-utils

say "1. Creciendo la partición $PART"
if OUT="$(sudo growpart "$DISK" "$PARTNUM" 2>&1)"; then
    echo "    $OUT"
else
    if echo "$OUT" | grep -qi "NOCHANGE"; then
        warn "Sin cambios: la partición ya ocupa todo el espacio libre del disco."
        warn "$OUT"
    else
        die "growpart falló: $OUT"
    fi
fi

if [ "$MODE" = "lvm" ]; then
    say "2. Actualizando el physical volume"
    sudo pvresize "$PART"

    say "3. Creciendo el volumen lógico"
    if sudo vgs --noheadings -o vg_free --units b "$VG" | grep -q '^\s*0B'; then
        warn "El volume group $VG no tiene espacio libre; nada que extender."
    else
        sudo lvextend -l +100%FREE "$LV"
    fi
fi

say "4. Creciendo el sistema de archivos"
if [ "$FSTYPE" = "xfs" ]; then
    sudo xfs_growfs /
else
    sudo resize2fs "$TARGET"
fi

# ------------------------------------------------------------ resultado
say "Resultado"
lsblk -o NAME,SIZE,FSTYPE,TYPE,MOUNTPOINTS
echo
df -h /
DESPUES="$(df -h --output=size / | tail -n1 | tr -d ' ')"
printf '\n\033[1;32m Raíz: %s  ->  %s\033[0m\n' "$ANTES" "$DESPUES"

if [ "$ANTES" = "$DESPUES" ]; then
    warn "No hubo cambio de tamaño. Si el servidor es una VM, lo más probable es que"
    warn "el disco virtual esté lleno: amplíalo primero en el hipervisor (VMware,"
    warn "Proxmox, Hyper-V...) y vuelve a correr este script."
fi

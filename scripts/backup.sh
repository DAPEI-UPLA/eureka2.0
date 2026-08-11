#!/usr/bin/env bash
#
# Respaldo diario de Prisma: base de datos + archivos subidos.
# Lo invoca cron a las 02:00 (ver DESPLIEGUE_UBUNTU.md, paso 11).
#
# Uso manual:  bash ~/Prisma/scripts/backup.sh
#
# Usa el comando '.backup' de sqlite3, que produce una copia consistente aunque
# la base esté en uso por gunicorn. Un simple 'cp' NO es seguro con la app corriendo.

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$APP_DIR/backups"
DB="$APP_DIR/db.sqlite3"
KEEP_DB=30        # días de respaldos de la base
KEEP_MEDIA=7      # días de respaldos de media/
STAMP="$(date +%F_%H%M)"

log() { printf '%s  %s\n' "$(date '+%F %T')" "$*"; }
die() { printf '%s  ERROR: %s\n' "$(date '+%F %T')" "$*" >&2; exit 1; }

[ -f "$DB" ] || die "No encuentro la base de datos en $DB"
mkdir -p "$DEST"

# ------------------------------------------------------------ base de datos
TMP="$DEST/.tmp_$STAMP.sqlite3"
trap 'rm -f "$TMP"' EXIT

sqlite3 "$DB" ".backup '$TMP'" || die "sqlite3 .backup falló"

CHECK="$(sqlite3 "$TMP" 'PRAGMA integrity_check;' | head -n1)"
[ "$CHECK" = "ok" ] || die "el respaldo salió corrupto (integrity_check: $CHECK)"

gzip -9 "$TMP"
mv "$TMP.gz" "$DEST/db_$STAMP.sqlite3.gz"
trap - EXIT

# ------------------------------------------------------- archivos subidos
if [ -d "$APP_DIR/media" ]; then
    tar -czf "$DEST/media_$STAMP.tar.gz" -C "$APP_DIR" media
fi

# ------------------------------------------------------------- retención
ls -1t "$DEST"/db_*.sqlite3.gz 2>/dev/null | tail -n +$((KEEP_DB + 1))    | xargs -r rm -f
ls -1t "$DEST"/media_*.tar.gz  2>/dev/null | tail -n +$((KEEP_MEDIA + 1)) | xargs -r rm -f

DB_SIZE="$(du -h "$DEST/db_$STAMP.sqlite3.gz" | cut -f1)"
TOTAL="$(du -sh "$DEST" | cut -f1)"
log "OK  db_$STAMP.sqlite3.gz ($DB_SIZE)  |  total en backups/: $TOTAL"

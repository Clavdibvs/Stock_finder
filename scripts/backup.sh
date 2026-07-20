#!/usr/bin/env bash
# Backup cifrato: pg_dump + snapshot Parquet -> Restic.
# Richiede RESTIC_REPOSITORY e RESTIC_PASSWORD in .env (o ambiente).
# Da schedulare via cron sul VPS, es: 30 18 * * 1-5 /opt/ddr/scripts/backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY non impostato (vedi .env.example)}"
: "${RESTIC_PASSWORD:?RESTIC_PASSWORD non impostato}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "[1/3] Dump del database…"
docker compose exec -T db pg_dump -U "${DDR_DB_USER:-ddr}" -d "${DDR_DB_NAME:-ddr}" --format=custom \
  > "$WORKDIR/ddr_${STAMP}.pgdump"

echo "[2/3] Copio gli snapshot Parquet…"
docker compose cp api:/app/data "$WORKDIR/appdata" 2>/dev/null || echo "  (nessun dato applicativo)"

echo "[3/3] Snapshot Restic cifrato…"
restic backup "$WORKDIR" --tag ddr --tag "$STAMP"
restic forget --tag ddr --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --prune

echo "Backup completato: $STAMP"
echo "IMPORTANTE: provare periodicamente il restore (scripts/restore.sh) — un backup mai ripristinato non è un backup."

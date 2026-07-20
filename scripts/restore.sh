#!/usr/bin/env bash
# Restore da backup Restic. USO: scripts/restore.sh [snapshot-id|latest]
# ATTENZIONE: sovrascrive il database corrente. Chiede conferma esplicita.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY non impostato}"
: "${RESTIC_PASSWORD:?RESTIC_PASSWORD non impostato}"

SNAPSHOT="${1:-latest}"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "Ripristino dello snapshot '$SNAPSHOT' in area temporanea…"
restic restore "$SNAPSHOT" --target "$WORKDIR"

DUMP="$(find "$WORKDIR" -name '*.pgdump' | sort | tail -1)"
[ -n "$DUMP" ] || { echo "ERRORE: nessun dump trovato nello snapshot." >&2; exit 1; }
echo "Dump trovato: $DUMP"

read -r -p "SOVRASCRIVERE il database corrente con questo dump? (scrivere 'sì') " CONFIRM
[ "$CONFIRM" = "sì" ] || { echo "Annullato."; exit 1; }

echo "Ripristino database…"
docker compose exec -T db dropdb -U "${DDR_DB_USER:-ddr}" --if-exists "${DDR_DB_NAME:-ddr}_restore" || true
docker compose exec -T db createdb -U "${DDR_DB_USER:-ddr}" "${DDR_DB_NAME:-ddr}_restore"
docker compose exec -T db pg_restore -U "${DDR_DB_USER:-ddr}" -d "${DDR_DB_NAME:-ddr}_restore" < "$DUMP"
# swap: il vecchio db resta come _old per rollback manuale
docker compose stop api
docker compose exec -T db psql -U "${DDR_DB_USER:-ddr}" -d postgres -c \
  "ALTER DATABASE \"${DDR_DB_NAME:-ddr}\" RENAME TO \"${DDR_DB_NAME:-ddr}_old_$(date +%s)\";
   ALTER DATABASE \"${DDR_DB_NAME:-ddr}_restore\" RENAME TO \"${DDR_DB_NAME:-ddr}\";"
docker compose start api

echo "Restore completato. Verificare l'applicazione e poi eliminare i database *_old_*."

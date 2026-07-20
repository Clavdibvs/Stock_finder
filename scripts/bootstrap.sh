#!/usr/bin/env bash
# Bootstrap: crea .env con segreti casuali (se assente) e avvia lo stack.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null; then
  echo "ERRORE: docker non trovato. Installare Docker prima di procedere." >&2
  exit 1
fi

rand() {
  # n byte casuali in esadecimale (evita SIGPIPE di tr|head sotto pipefail)
  if command -v openssl >/dev/null; then
    openssl rand -hex "$(( ${1:-48} / 2 ))"
  else
    python3 -c "import secrets;print(secrets.token_hex(${1:-48}//2))"
  fi
}

if [ ! -f .env ]; then
  echo "Creo .env con segreti generati casualmente…"
  cp .env.example .env
  DB_PW="$(rand 32)"
  ADMIN_PW="$(rand 20)"
  SESSION_SECRET="$(rand 64)"
  # sostituzione portabile (macOS/BSD e GNU sed)
  sed -i.bak \
    -e "s|DDR_DB_PASSWORD=.*|DDR_DB_PASSWORD=${DB_PW}|" \
    -e "s|DDR_ADMIN_PASSWORD=.*|DDR_ADMIN_PASSWORD=${ADMIN_PW}|" \
    -e "s|DDR_SESSION_SECRET=.*|DDR_SESSION_SECRET=${SESSION_SECRET}|" \
    .env && rm -f .env.bak
  chmod 600 .env
  echo
  echo "=============================================================="
  echo " Credenziali generate (conservale in un password manager):"
  echo "   utente:   admin"
  echo "   password: ${ADMIN_PW}"
  echo " Modalità: demo (nessuna API key necessaria)."
  echo "=============================================================="
  echo
else
  echo ".env esistente: non tocco i segreti."
fi

echo "Build e avvio dello stack…"
docker compose up -d --build

echo
echo "Attendo che l'API sia pronta…"
for i in $(seq 1 60); do
  if docker compose exec -T api python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health')" 2>/dev/null; then
    break
  fi
  sleep 2
done

echo
echo "Fatto. Interfaccia: http://localhost:${DDR_HTTP_PORT:-80}/ (o il dominio configurato)"
echo "In modalità demo il dataset dimostrativo viene caricato al primo avvio."

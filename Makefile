# Drawdown Radar — comandi principali
.PHONY: dev-api dev-web test build up down logs seed-reset backup

# sviluppo: API su :8000 (SQLite locale, demo, auth attiva con password demo)
dev-api:
	cd backend && DDR_DATABASE_URL="sqlite:///data/dev.db" DDR_APP_MODE=demo \
	DDR_ADMIN_PASSWORD=demo-password DDR_COOKIE_SECURE=false \
	.venv/bin/uvicorn app.main:app --reload --port 8000

# sviluppo: frontend su :5173 (proxy /api -> :8000)
dev-web:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/python -m pytest tests/ -q

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

# ricrea da zero il dataset demo in sviluppo
seed-reset:
	rm -f backend/data/dev.db

backup:
	./scripts/backup.sh

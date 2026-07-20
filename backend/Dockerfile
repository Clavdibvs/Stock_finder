FROM python:3.12-slim AS base

# utente non privilegiato (least privilege)
RUN groupadd -r ddr && useradd -r -g ddr -d /app -s /sbin/nologin ddr

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir . && pip uninstall -y drawdown-radar-backend

COPY alembic.ini ./
COPY alembic ./alembic
COPY config ./config
COPY app ./app

RUN mkdir -p /app/data && chown -R ddr:ddr /app/data
USER ddr

EXPOSE 8000

# le migrazioni girano prima dell'avvio; l'API ascolta SOLO sulla rete interna
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

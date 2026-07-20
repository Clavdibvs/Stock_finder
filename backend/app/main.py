"""Drawdown Radar — applicazione privata mono-utente.

Non è consulenza finanziaria. Nessuna esecuzione di ordini, nessun
collegamento operativo a broker, nessuna raccomandazione short.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import auth, dashboard, quality, securities, settings_api, sources, watchlist
from app.config import APP_VERSION, get_settings
from app.constants import DISCLAIMER
from app.core.logging import setup_logging
from app.core.security import ensure_admin_user
from app.db import get_engine, get_sessionmaker
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.models import Base

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.debug)

    engine = get_engine()
    if settings.database_url.startswith("sqlite"):
        # solo sviluppo/test: in produzione lo schema è gestito da Alembic
        Base.metadata.create_all(engine)

    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        if settings.admin_password and not settings.auth_disabled:
            ensure_admin_user(db)
        if settings.app_mode == "demo":
            from app.seed.demo import run_demo_seed
            result = run_demo_seed(db)
            logger.info("Seed demo: %s", result.get("status"))
    finally:
        db.close()

    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Drawdown Radar",
    version=APP_VERSION,
    description=DISCLAIMER,
    lifespan=lifespan,
    docs_url=None,     # nessuna documentazione API pubblica
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # mai esporre stack trace o dettagli interni
    logger.exception("Errore non gestito su %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Errore interno"})


@app.get("/api/health")
def health():
    settings = get_settings()
    return {"status": "ok", "version": APP_VERSION, "mode": settings.app_mode}


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(securities.router)
app.include_router(sources.router)
app.include_router(watchlist.router)
app.include_router(quality.router)
app.include_router(settings_api.router)

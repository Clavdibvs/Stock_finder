"""Dispatcher della news discovery: provider sostituibile.

- "gdelt" (default): gratuito, aperto, nessuna chiave;
- "brave": opzionale, richiede piano/chiave (https://brave.com/search/api/);
- "" / altro: non configurata (stato esplicito, nessun dato inventato).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.base import AdapterStatus
from app.config import get_settings
from app.models import Security


def news_status() -> AdapterStatus:
    provider = get_settings().news_discovery_provider
    if provider == "gdelt":
        from app.adapters.gdelt_news import gdelt_status
        return gdelt_status()
    if provider == "brave":
        from app.adapters.brave_news import brave_status
        return brave_status()
    return AdapterStatus.NOT_CONFIGURED


def news_provider_name() -> str:
    return get_settings().news_discovery_provider or "nessuno"


def ingest_news_for_security(db: Session, security: Security, ticker: str) -> dict:
    provider = get_settings().news_discovery_provider
    if provider == "gdelt":
        from app.adapters.gdelt_news import ingest_news_for_security as fn
        return fn(db, security, ticker)
    if provider == "brave":
        from app.adapters.brave_news import ingest_news_for_security as fn
        return fn(db, security, ticker)
    return {"documents": 0, "note": "news discovery non configurata"}

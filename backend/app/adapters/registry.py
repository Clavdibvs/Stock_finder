"""Registro degli adapter: risolve i provider da configurazione."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.base import AdapterStatus, DocumentSourceAdapter, MarketDataAdapter
from app.adapters.alpaca import AlpacaMarketDataAdapter
from app.adapters.demo import DemoMarketDataAdapter
from app.adapters.nasdaq_halts import halts_status
from app.adapters.news_discovery import news_provider_name, news_status
from app.adapters.sec_edgar import SECEdgarAdapter
from app.adapters.stubs import (
    AlpacaStubAdapter, BraveDiscoveryStubAdapter, ClinicalTrialsStubAdapter,
    EODHDStubAdapter, FINRAStubAdapter, IRRssStubAdapter,
    NasdaqHaltsStubAdapter, OpenFDAStubAdapter, TiingoStubAdapter,
)
from app.config import get_settings


def get_market_adapter(db: Session) -> MarketDataAdapter:
    provider = get_settings().market_data_provider
    if provider == "demo":
        return DemoMarketDataAdapter(db)
    if provider == "alpaca":
        return AlpacaMarketDataAdapter()
    mapping = {
        "eodhd_stub": EODHDStubAdapter,
        "tiingo_stub": TiingoStubAdapter,
        "alpaca_stub": AlpacaStubAdapter,
    }
    cls = mapping.get(provider)
    if cls is None:
        raise ValueError(f"Provider di mercato sconosciuto: {provider}")
    return cls()


def get_document_adapters(db: Session) -> dict[str, DocumentSourceAdapter]:
    return {
        "sec_edgar": SECEdgarAdapter(),
        "clinicaltrials": ClinicalTrialsStubAdapter(),
        "openfda": OpenFDAStubAdapter(),
        "ir_rss": IRRssStubAdapter(),
        "nasdaq_halts": NasdaqHaltsStubAdapter(),
        "finra": FINRAStubAdapter(),
        "brave_discovery": BraveDiscoveryStubAdapter(),
    }


def provider_statuses(db: Session) -> list[dict]:
    """Stato di tutti i provider per la schermata Data Quality/Impostazioni."""
    settings = get_settings()
    market = get_market_adapter(db)
    out = [{
        "name": f"market_data ({market.name})",
        "kind": "market",
        "status": market.status().value,
        "configured": market.status() is AdapterStatus.OK,
    }]
    for key, adapter in get_document_adapters(db).items():
        if key == "nasdaq_halts":
            status = halts_status()      # adapter reale (RSS ufficiale)
        elif key == "brave_discovery":
            key = f"news_discovery ({news_provider_name()})"
            status = news_status()       # dispatcher: gdelt (gratuito) | brave (key)
        else:
            status = adapter.status()
        out.append({
            "name": key,
            "kind": "documents",
            "status": status.value,
            "configured": status is AdapterStatus.OK,
        })
    out.append({
        "name": f"ai ({settings.ai_provider})",
        "kind": "ai",
        "status": "ok" if settings.ai_enabled and settings.ai_api_key else "non configurata",
        "configured": settings.ai_enabled and bool(settings.ai_api_key),
    })
    return out

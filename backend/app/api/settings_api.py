"""Impostazioni: modalità, provider, soglie, pesi, job, budget AI, export.

Le API key non vengono MAI restituite: solo lo stato (configurata/assente).
Le soglie e i pesi si modificano nei file config/*.yaml (versionati); qui
vengono mostrati in sola lettura con la loro versione.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.registry import provider_statuses
from app.ai.provider import month_spend_eur
from app.config import (
    APP_VERSION, candidates_config, config_hash, get_settings, jobs_config, scoring_config,
)
from app.constants import DISCLAIMER
from app.core.audit import audit
from app.core.security import require_auth
from app.db import get_db
from app.validation.export import export_dataset

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_app_settings(db: Session = Depends(get_db), _: str = Depends(require_auth)):
    settings = get_settings()
    return {
        "app_version": APP_VERSION,
        "mode": settings.app_mode,
        "auth_disabled": settings.auth_disabled,
        "timezone_display": jobs_config()["timezone_display"],
        "providers": provider_statuses(db),
        "api_keys": {
            # stato senza mostrare i valori
            "market_data": bool(settings.market_data_api_key),
            "openfda": bool(settings.openfda_api_key),
            "news_discovery": bool(settings.news_discovery_api_key),
            "ai": bool(settings.ai_api_key),
        },
        "candidate_thresholds": candidates_config(),
        "scoring": {
            "version": scoring_config()["version"],
            "weights": scoring_config()["weights"],
            "thresholds": scoring_config()["thresholds"],
            "config_hash": config_hash(),
        },
        "jobs": jobs_config()["jobs"],
        "notifications": {
            "channel": settings.notify_channel,
            "rules": jobs_config()["notifications"],
        },
        "ai": {
            "enabled": settings.ai_enabled,
            "provider": settings.ai_provider,
            "model": settings.ai_model if settings.ai_enabled else None,
            "monthly_budget_eur": settings.ai_monthly_budget_eur,
            "month_spend_eur": round(month_spend_eur(db), 2),
            "max_candidates": settings.ai_max_candidates,
        },
        "retention": {
            "documents_days": settings.retention_documents_days,
            "social_days": settings.retention_social_days,
        },
        "disclaimer": DISCLAIMER,
        "config_note": (
            "Soglie e pesi si modificano nei file config/candidates.yaml e "
            "config/scoring.yaml incrementando la versione; ogni score salva "
            "versione e hash della configurazione usata."
        ),
    }


@router.get("/universe")
def get_universe(db: Session = Depends(get_db), _: str = Depends(require_auth)):
    """Universo live corrente (esclusi titoli demo). In auto-discovery
    l'elenco può contare migliaia di titoli: si restituiscono conteggi e
    un'anteprima limitata."""
    from app.adapters.discovery import active_crypto
    from app.adapters.sec_universe import active_universe
    settings = get_settings()
    equities = active_universe(db)
    cryptos = active_crypto(db)
    rows = []
    for sec, listing in equities[:200]:
        rows.append({
            "security_id": sec.id,
            "ticker": listing.ticker,
            "name": sec.name,
            "exchange": listing.exchange,
            "cik": sec.cik,
            "shares_outstanding": listing.shares_outstanding,
        })
    return {
        "mode": settings.app_mode,
        "universe_mode": settings.universe_mode,
        "crypto_enabled": settings.crypto_enabled,
        "benchmark": settings.benchmark_ticker,
        "env_tickers": settings.universe_ticker_list,
        "total_equities": len(equities),
        "total_crypto": len(cryptos),
        "tickers": sorted(rows, key=lambda r: r["ticker"]),
        "preview_truncated": len(equities) > 200,
    }


class UniverseUpdate(BaseModel):
    tickers: list[str] = Field(max_length=500, description="Ticker da aggiungere/sincronizzare")


@router.post("/universe")
def update_universe(payload: UniverseUpdate, db: Session = Depends(get_db),
                    user: str = Depends(require_auth)):
    """Aggiunge/sincronizza ticker nell'universo live (anagrafica da SEC se configurata)."""
    from app.adapters.sec_universe import sync_universe
    settings = get_settings()
    if settings.app_mode != "live":
        raise HTTPException(status_code=409,
                            detail="L'universo si gestisce in modalità live (DDR_APP_MODE=live).")
    clean = [t.strip().upper() for t in payload.tickers if t.strip()]
    if not clean:
        raise HTTPException(status_code=422, detail="Nessun ticker valido")
    if len(clean) > 500:
        raise HTTPException(status_code=422,
                            detail="Massimo 500 ticker per l'universo esplicito (vedi SOURCE_REGISTRY.md)")
    result = sync_universe(db, clean)
    audit(db, actor=user, action="universe_sync",
          details={"requested": len(clean), "created": result["created"],
                   "unknown_to_sec": result["unknown_to_sec"]})
    db.commit()
    return result


@router.post("/export")
def export_data(fmt: str = "parquet", db: Session = Depends(get_db),
                user: str = Depends(require_auth)):
    """Esporta il dataset segnali+outcome (Parquet/CSV) per il backtest."""
    try:
        path = export_dataset(db, fmt)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    audit(db, actor=user, action="export_dataset", details={"path": str(path), "fmt": fmt})
    db.commit()
    media = "application/octet-stream" if fmt == "parquet" else "text/csv"
    return FileResponse(path, media_type=media, filename=path.name)

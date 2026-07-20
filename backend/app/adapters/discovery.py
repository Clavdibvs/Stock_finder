"""Scoperta automatica dell'universo (modalità DDR_UNIVERSE_MODE=auto).

Equity: intero listino USA dal provider (NYSE, NASDAQ, NYSE American),
filtrando ETF/fondi/warrant/right/unit/preferred con euristiche dichiarate.
L'anagrafica SEC (CIK, shares outstanding) NON viene scaricata per tutto il
listino: si arricchisce lazy, solo per i candidati del giorno (fair access).

Crypto (DDR_CRYPTO_ENABLED=true): coppie */USD del provider, security_type
"crypto". Limiti permanenti dichiarati: nessun filing, nessuna market cap
ufficiale, nessun claim graph -> confidence massima C, mai «RISCHIO ELEVATO».
"""
from __future__ import annotations

import logging
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.alpaca import AlpacaMarketDataAdapter
from app.config import get_settings
from app.models import Security, SecurityListing

logger = logging.getLogger(__name__)

ALLOWED_EXCHANGES = {"NYSE", "NASDAQ", "AMEX"}  # AMEX = NYSE American

# euristiche di esclusione per strumenti non-common-stock (documentate)
_NAME_EXCLUDE = re.compile(
    r"\b(etf|etn|fund|warrant|warrants|right|rights|unit|units|preferred|"
    r"depositary|ishares|proshares|vanguard|direxion|spdr|graniteshares|"
    r"leveraged|2x|3x|-1x|closed[- ]end|income trust)\b",
    re.IGNORECASE,
)


def filter_equity_assets(assets: list[dict]) -> list[dict]:
    """Filtra l'elenco del provider al perimetro 'azioni ordinarie USA'."""
    out = []
    for a in assets:
        if not a.get("tradable") or a.get("status") != "active":
            continue
        if a.get("exchange") not in ALLOWED_EXCHANGES:
            continue  # esclude ARCA/BATS (quasi solo ETF) e OTC
        symbol = a.get("symbol") or ""
        if not symbol or "." in symbol or "/" in symbol or "-" in symbol:
            continue  # classi speciali, warrant (.WS), preferred (-P)
        name = a.get("name") or ""
        if _NAME_EXCLUDE.search(name):
            continue
        out.append(a)
    return out


def discover_equities(db: Session) -> dict:
    """Sincronizza l'universo equity dall'elenco asset del provider."""
    adapter = AlpacaMarketDataAdapter()
    assets = adapter.list_assets("us_equity")
    filtered = filter_equity_assets(assets)

    existing = {
        listing.ticker for listing in db.scalars(
            select(SecurityListing).where(SecurityListing.status == "active")
        )
    }
    created = 0
    for a in filtered:
        symbol = a["symbol"]
        if symbol in existing:
            continue
        sec = Security(name=a.get("name") or symbol, is_demo=False)
        db.add(sec)
        db.flush()
        db.add(SecurityListing(
            security_id=sec.id, ticker=symbol,
            exchange=a.get("exchange") or "UNKNOWN",
            status="active", valid_from=date.today(),
        ))
        created += 1
    db.flush()
    return {"provider_assets": len(assets), "in_perimeter": len(filtered),
            "created": created, "already_known": len(filtered) - created}


def discover_crypto(db: Session) -> dict:
    """Sincronizza le coppie crypto */USD del provider (se abilitate)."""
    settings = get_settings()
    if not settings.crypto_enabled:
        return {"created": 0, "note": "crypto disabilitate (DDR_CRYPTO_ENABLED=false)"}
    adapter = AlpacaMarketDataAdapter()
    assets = adapter.list_assets("crypto")
    pairs = [a for a in assets
             if a.get("tradable") and (a.get("symbol") or "").endswith("/USD")]
    existing = {
        listing.ticker for listing in db.scalars(
            select(SecurityListing).where(SecurityListing.status == "active")
        )
    }
    created = 0
    for a in pairs:
        symbol = a["symbol"]
        if symbol in existing or len(symbol) > 12:
            continue
        sec = Security(name=a.get("name") or symbol, is_demo=False,
                       security_type="crypto")
        db.add(sec)
        db.flush()
        db.add(SecurityListing(
            security_id=sec.id, ticker=symbol, exchange="CRYPTO",
            status="active", valid_from=date.today(),
        ))
        created += 1
    db.flush()
    return {"pairs": len(pairs), "created": created}


def active_crypto(db: Session) -> list[tuple[Security, SecurityListing]]:
    rows = db.scalars(
        select(SecurityListing).where(SecurityListing.status == "active",
                                      SecurityListing.exchange == "CRYPTO")
    ).all()
    out = []
    for listing in rows:
        sec = db.get(Security, listing.security_id)
        if sec and sec.security_type == "crypto" and not sec.is_demo:
            out.append((sec, listing))
    return out


def enrich_candidate_anagrafica(db: Session, securities: list[Security],
                                ticker_map: dict | None = None) -> int:
    """Anagrafica SEC lazy SOLO per i candidati: CIK + shares outstanding.

    `ticker_map` può essere passato per riusare la mappa (1 sola richiesta
    company_tickers per run). Fallisce in silenzio esplicito: senza SEC i
    campi restano mancanti.
    """
    from app.adapters.base import NotConfiguredError
    from app.adapters.sec_universe import fetch_shares_outstanding, fetch_ticker_map
    from app.core.http import FetchError

    if ticker_map is None:
        try:
            ticker_map = fetch_ticker_map()
        except (NotConfiguredError, FetchError) as exc:
            logger.info("Anagrafica SEC non disponibile: %s", exc)
            return 0

    enriched = 0
    for sec in securities:
        if sec.security_type != "common_stock":
            continue
        listing = db.scalar(
            select(SecurityListing).where(SecurityListing.security_id == sec.id,
                                          SecurityListing.status == "active")
        )
        if listing is None:
            continue
        info = ticker_map.get(listing.ticker)
        if info is None:
            continue
        changed = False
        if not sec.cik and info.get("cik"):
            sec.cik = info["cik"]
            changed = True
        if sec.name == listing.ticker and info.get("name"):
            sec.name = info["name"]
            changed = True
        if listing.shares_outstanding is None and sec.cik:
            try:
                shares = fetch_shares_outstanding(sec.cik)
            except (NotConfiguredError, FetchError):
                shares = None
            if shares:
                listing.shares_outstanding = shares
                changed = True
        if changed:
            enriched += 1
    db.flush()
    return enriched

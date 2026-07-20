"""Universo e anagrafica da fonti SEC gratuite e ufficiali.

- company_tickers_exchange.json: mappa ticker -> CIK, nome, exchange
  (l'identificatore stabile resta il nostro, MAI il ticker);
- XBRL companyconcept dei/EntityCommonStockSharesOutstanding: shares
  outstanding point-in-time (il float NON è disponibile: resta mancante).

Richiede DDR_SEC_USER_AGENT (fair access). Senza configurazione le funzioni
sollevano NotConfiguredError: i titoli si creano comunque, ma senza CIK né
shares (confidence ridotta, mai dati inventati).
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import NotConfiguredError
from app.adapters.sec_edgar import _throttle
from app.config import get_settings
from app.core.http import FetchError, safe_fetch
from app.models import Security, SecurityListing

logger = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SHARES_URL = ("https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:0>10}/dei/"
              "EntityCommonStockSharesOutstanding.json")

_EXCHANGE_MAP = {"nasdaq": "NASDAQ", "nyse": "NYSE", "nyse american": "NYSE American",
                 "nyse arca": "NYSE Arca", "cboe": "CBOE", "otc": "OTC"}


def _require_sec() -> str:
    s = get_settings()
    if not s.sec_edgar_enabled or not s.sec_user_agent:
        raise NotConfiguredError(
            "SEC non configurata: impostare DDR_SEC_EDGAR_ENABLED=true e "
            "DDR_SEC_USER_AGENT ('Nome Cognome email@example.com')."
        )
    return s.sec_user_agent


def fetch_ticker_map() -> dict[str, dict]:
    """{TICKER: {cik, name, exchange}} dall'elenco ufficiale SEC."""
    ua = _require_sec()
    _throttle()
    resp = safe_fetch(TICKERS_URL, headers={"User-Agent": ua})
    payload = resp.json()
    fields = payload.get("fields", [])
    out: dict[str, dict] = {}
    for row in payload.get("data", []):
        rec = dict(zip(fields, row))
        ticker = str(rec.get("ticker") or "").upper()
        if not ticker:
            continue
        exchange_raw = str(rec.get("exchange") or "").strip().lower()
        out[ticker] = {
            "cik": f"{int(rec['cik']):010d}" if rec.get("cik") else None,
            "name": rec.get("name") or ticker,
            "exchange": _EXCHANGE_MAP.get(exchange_raw, rec.get("exchange")),
        }
    return out


def fetch_shares_outstanding(cik: str) -> float | None:
    """Ultimo valore dichiarato di shares outstanding (XBRL dei)."""
    ua = _require_sec()
    _throttle()
    try:
        resp = safe_fetch(SHARES_URL.format(cik=cik), headers={"User-Agent": ua})
    except FetchError:
        return None
    data = resp.json()
    best: tuple[str, float] | None = None
    for unit_values in (data.get("units") or {}).values():
        for v in unit_values:
            end, val = v.get("end"), v.get("val")
            if end and val:
                if best is None or end > best[0]:
                    best = (end, float(val))
    return best[1] if best else None


def sync_universe(db: Session, tickers: list[str]) -> dict:
    """Crea/aggiorna Security+Listing per i ticker richiesti (+ benchmark).

    Idempotente. Se la SEC non è configurata, i titoli nascono senza CIK/nome
    ufficiale/shares: lo stato resta esplicito, nessun dato inventato.
    """
    settings = get_settings()
    try:
        mapping = fetch_ticker_map()
        sec_ok = True
    except (NotConfiguredError, FetchError) as exc:
        logger.warning("Universo senza anagrafica SEC: %s", exc)
        mapping, sec_ok = {}, False

    created, updated, unknown = [], [], []
    wanted = [t.strip().upper() for t in tickers if t.strip()]

    for ticker in dict.fromkeys(wanted):  # dedup preservando l'ordine
        info = mapping.get(ticker)
        if sec_ok and info is None:
            unknown.append(ticker)  # non registrato SEC: si crea comunque
        listing = db.scalar(
            select(SecurityListing).where(SecurityListing.ticker == ticker,
                                          SecurityListing.status == "active")
        )
        if listing is None:
            sec_row = Security(
                name=(info or {}).get("name") or ticker,
                cik=(info or {}).get("cik"),
                is_demo=False,
            )
            db.add(sec_row)
            db.flush()
            listing = SecurityListing(
                security_id=sec_row.id, ticker=ticker,
                exchange=(info or {}).get("exchange") or "UNKNOWN",
                status="active", valid_from=date.today(),
            )
            db.add(listing)
            db.flush()
            created.append(ticker)
        else:
            sec_row = db.get(Security, listing.security_id)
            if info:
                sec_row.cik = sec_row.cik or info.get("cik")
                if sec_row.name == listing.ticker and info.get("name"):
                    sec_row.name = info["name"]
                if listing.exchange == "UNKNOWN" and info.get("exchange"):
                    listing.exchange = info["exchange"]
            updated.append(ticker)

        # shares outstanding da XBRL (se CIK noto)
        sec_row = db.get(Security, listing.security_id)
        if sec_ok and sec_row.cik:
            shares = fetch_shares_outstanding(sec_row.cik)
            if shares:
                listing.shares_outstanding = shares

    # benchmark (ETF proxy) come security di tipo index
    bench_ticker = settings.benchmark_ticker.upper()
    if bench_ticker:
        bench = db.scalar(
            select(SecurityListing).where(SecurityListing.ticker == bench_ticker)
        )
        if bench is None:
            bench_sec = Security(name=f"Benchmark {bench_ticker}",
                                 security_type="index", is_demo=False)
            db.add(bench_sec)
            db.flush()
            db.add(SecurityListing(security_id=bench_sec.id, ticker=bench_ticker,
                                   exchange="ARCA", status="active",
                                   valid_from=date.today()))
    db.flush()
    return {"created": created, "updated": updated, "unknown_to_sec": unknown,
            "sec_configured": sec_ok}


def active_universe(db: Session) -> list[tuple[Security, SecurityListing]]:
    """Titoli live attivi (esclusi demo e benchmark)."""
    rows = db.scalars(
        select(SecurityListing).where(SecurityListing.status == "active")
    ).all()
    out = []
    for listing in rows:
        sec = db.get(Security, listing.security_id)
        if sec and not sec.is_demo and sec.security_type == "common_stock":
            out.append((sec, listing))
    return out

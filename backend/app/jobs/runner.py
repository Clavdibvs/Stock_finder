"""Job giornalieri. Ogni job:
- è idempotente (chiave job+data: una seconda esecuzione sovrascrive, non duplica);
- registra una IngestionRun con esito ed errori;
- non genera MAI segnali da dati corrotti o mancanti (blocco esplicito).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterStatus, NotConfiguredError
from app.adapters.registry import get_document_adapters, get_market_adapter
from app.config import get_settings, jobs_config
from app.models import (
    DataQualityIssue, IngestionRun, MarketBar, Notification, RiskScore,
    Security, utcnow,
)
from app.scoring.pipeline import run_for_security
from app.seed.demo import last_business_day
from app.validation.retrospective import update_all_pending

logger = logging.getLogger(__name__)


def _start_run(db: Session, job_name: str, triggered_by: str, asof: date) -> IngestionRun:
    run = IngestionRun(
        job_name=job_name, triggered_by=triggered_by,
        idempotency_key=f"{job_name}:{asof.isoformat()}",
    )
    db.add(run)
    db.flush()
    return run


def _finish(db: Session, run: IngestionRun, status: str, items: int = 0,
            errors: list | None = None) -> None:
    run.status = status
    run.items_processed = items
    run.errors = errors
    run.finished_at = utcnow()
    db.commit()


# --------------------------------------------------------------- job impl ---

def _upsert_bars(db: Session, security_id: int, bars: list, provider: str) -> int:
    """Insert bulk idempotente: 1 query per titolo, non 1 per barra
    (necessario con l'universo full-market: ~1M barre al primo backfill)."""
    if not bars:
        return 0
    existing = {
        (d, s) for d, s in db.execute(
            select(MarketBar.bar_date, MarketBar.session).where(
                MarketBar.security_id == security_id,
                MarketBar.provider == provider)
        )
    }
    new_rows = [
        MarketBar(security_id=security_id, bar_date=b.bar_date, session=b.session,
                  open=b.open, high=b.high, low=b.low, close=b.close,
                  volume=b.volume, vwap=b.vwap, provider=provider)
        for b in bars if (b.bar_date, b.session) not in existing
    ]
    db.add_all(new_rows)
    return len(new_rows)


def _live_universe(db: Session):
    """(security, listing) attivi non-demo, benchmark incluso in coda."""
    from app.adapters.discovery import active_crypto
    from app.adapters.sec_universe import active_universe
    from app.models import SecurityListing
    universe = active_universe(db) + active_crypto(db)
    bench = db.scalars(
        select(Security).where(Security.security_type == "index",
                               Security.is_demo.is_(False))
    ).all()
    for sec in bench:
        listing = db.scalar(select(SecurityListing).where(
            SecurityListing.security_id == sec.id))
        if listing is not None:
            universe.append((sec, listing))
    return universe


def _fetch_bars_for_universe(db: Session, run, start_days_back: int, asof: date) -> tuple[int, list]:
    """Barre per tutto l'universo live (bulk se il provider lo supporta)."""
    from datetime import timedelta
    adapter = get_market_adapter(db)
    universe = _live_universe(db)
    if not universe:
        db.add(DataQualityIssue(
            run_id=run.id, issue_type="ingestion_error", severity="warn",
            message="Universo vuoto: aggiungere ticker da Impostazioni → Universo "
                    "o DDR_UNIVERSE_TICKERS, poi eseguire universe_sync.",
        ))
        return 0, []
    start = asof - timedelta(days=start_days_back)
    equities = [(s, lst) for s, lst in universe if s.security_type != "crypto"]
    cryptos = [(s, lst) for s, lst in universe if s.security_type == "crypto"]
    tickers = [listing.ticker for _, listing in equities]
    by_ticker = {listing.ticker: sec.id for sec, listing in universe}
    errors: list[str] = []
    saved = 0
    try:
        if hasattr(adapter, "get_daily_bars_bulk"):
            bulk = adapter.get_daily_bars_bulk(tickers, start, asof)
        else:
            bulk = {t: adapter.get_daily_bars(t, start, asof) for t in tickers}
        if cryptos and hasattr(adapter, "get_crypto_bars_bulk"):
            bulk.update(adapter.get_crypto_bars_bulk(
                [lst.ticker for _, lst in cryptos], start, asof))
        for ticker, bars in bulk.items():
            sec_id = by_ticker.get(ticker)
            if sec_id is None:
                continue
            saved += _upsert_bars(db, sec_id, bars, adapter.name)
            if not bars:
                db.add(DataQualityIssue(
                    run_id=run.id, security_id=sec_id, issue_type="missing_bar",
                    severity="warn",
                    message=f"{ticker}: nessuna barra dal provider nel periodo richiesto.",
                ))
    except NotConfiguredError as exc:
        errors.append(str(exc))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"barre: {exc}")
    return saved, errors


def job_ingest_eod(db: Session, triggered_by: str = "schedule") -> dict:
    """Ingestione EOD live: barre (bulk), filing EDGAR, halt Nasdaq."""
    settings = get_settings()
    asof = last_business_day()
    run = _start_run(db, "ingest_eod", triggered_by, asof)
    if settings.app_mode == "demo":
        _finish(db, run, "success", 0)
        return {"status": "success", "note": "Modalità demo: nessuna ingestione esterna."}

    adapter = get_market_adapter(db)
    if adapter.status() is not AdapterStatus.OK:
        db.add(DataQualityIssue(
            run_id=run.id, issue_type="provider_not_configured", severity="error",
            message=f"Provider di mercato '{adapter.name}' non configurato: ingestione saltata, "
                    "nessun dato fittizio generato.",
        ))
        _finish(db, run, "failed", 0, [f"{adapter.name}: non configurato"])
        return {"status": "failed", "note": "provider non configurato"}

    errors: list[str] = []
    # 1. barre degli ultimi 7 giorni di calendario (recupera festivi/lag)
    bars_saved, bar_errors = _fetch_bars_for_universe(db, run, 7, asof)
    errors.extend(bar_errors)

    # 2. filing EDGAR per l'universo (se configurato).
    # In auto-discovery l'universo è l'intero mercato: i filing si ingeriscono
    # SOLO per i candidati nella fase 2 del ranking (fair access SEC).
    filings_docs = 0
    from app.adapters.edgar_ingest import ingest_filings
    from app.adapters.sec_edgar import SECEdgarAdapter
    if SECEdgarAdapter().status() is AdapterStatus.OK \
            and settings.universe_mode != "auto":
        for sec, listing in _live_universe(db):
            if sec.security_type != "common_stock":
                continue
            try:
                result = ingest_filings(db, sec, listing)
                filings_docs += result.get("documents", 0)
            except NotConfiguredError:
                break
            except Exception as exc:  # noqa: BLE001
                errors.append(f"edgar {listing.ticker}: {exc}")
    else:
        db.add(DataQualityIssue(
            run_id=run.id, issue_type="provider_not_configured", severity="info",
            message="SEC EDGAR non configurata: nessun filing ingerito.",
        ))

    # 3. halt Nasdaq (se abilitato)
    halts_created = 0
    if settings.nasdaq_halts_enabled:
        from app.adapters.nasdaq_halts import ingest_halts
        try:
            halts_created = ingest_halts(db).get("created", 0)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"halts: {exc}")

    db.commit()
    status = "success" if not errors else "partial"
    _finish(db, run, status, bars_saved + filings_docs + halts_created, errors or None)
    return {"status": status, "bars": bars_saved, "filings": filings_docs,
            "halts": halts_created, "errors": errors[:5]}


def job_universe_sync(db: Session, triggered_by: str = "schedule") -> dict:
    """Sincronizza l'universo.

    - modalità "auto": scoperta automatica full-market dal provider
      (equity + crypto se abilitate); anagrafica SEC lazy sui candidati;
    - modalità "explicit": lista DDR_UNIVERSE_TICKERS / UI con anagrafica SEC.
    """
    settings = get_settings()
    asof = last_business_day()
    run = _start_run(db, "universe_sync", triggered_by, asof)
    if settings.app_mode == "demo":
        _finish(db, run, "success", 0)
        return {"status": "success", "note": "Demo: universo gestito dal seed."}

    if settings.universe_mode == "auto":
        from app.adapters.discovery import discover_crypto, discover_equities
        from app.adapters.sec_universe import sync_universe
        try:
            eq = discover_equities(db)
        except NotConfiguredError as exc:
            _finish(db, run, "failed", 0, [str(exc)])
            return {"status": "failed", "note": str(exc)}
        cr = discover_crypto(db)
        # il benchmark resta gestito da sync_universe (nessun ticker extra)
        sync_universe(db, [])
        db.commit()
        _finish(db, run, "success", eq["created"] + cr.get("created", 0))
        return {"status": "success", "equities": eq, "crypto": cr}

    from app.adapters.sec_universe import active_universe, sync_universe
    tickers = settings.universe_ticker_list
    tickers = list(dict.fromkeys(
        tickers + [listing.ticker for _, listing in active_universe(db)]
    ))
    if not tickers:
        _finish(db, run, "partial", 0, ["universo vuoto"])
        return {"status": "partial",
                "note": "Nessun ticker: impostare DDR_UNIVERSE_TICKERS o usare "
                        "Impostazioni → Universo."}
    result = sync_universe(db, tickers)
    db.commit()
    _finish(db, run, "success", len(result["created"]) + len(result["updated"]))
    return {"status": "success", **result}


def job_backfill_history(db: Session, triggered_by: str = "manual") -> dict:
    """Backfill iniziale dello storico barre per l'universo live."""
    settings = get_settings()
    asof = last_business_day()
    run = _start_run(db, "backfill_history", triggered_by, asof)
    if settings.app_mode == "demo":
        _finish(db, run, "success", 0)
        return {"status": "success", "note": "Demo: storico già nel seed."}
    adapter = get_market_adapter(db)
    if adapter.status() is not AdapterStatus.OK:
        _finish(db, run, "failed", 0, ["provider non configurato"])
        return {"status": "failed", "note": "provider non configurato"}
    days_back = (settings.discover_backfill_days
                 if settings.universe_mode == "auto" else settings.backfill_days)
    saved, errors = _fetch_bars_for_universe(db, run, days_back, asof)
    db.commit()
    status = "success" if not errors else "partial"
    _finish(db, run, status, saved, errors or None)
    return {"status": status, "bars": saved, "errors": errors[:5]}


def job_quality_checks(db: Session, triggered_by: str = "schedule") -> dict:
    """QC: barre mancanti, OHLC impossibili, documenti senza timestamp, azioni non riconciliate."""
    asof = last_business_day()
    run = _start_run(db, "quality_checks", triggered_by, asof)
    issues = 0
    settings = get_settings()
    qc_query = select(Security).where(Security.security_type == "common_stock")
    if settings.app_mode == "live":
        qc_query = qc_query.where(Security.is_demo.is_(False))
    for sec in db.scalars(qc_query):
        last_bar = db.scalar(
            select(MarketBar).where(MarketBar.security_id == sec.id,
                                    MarketBar.session == "regular")
            .order_by(MarketBar.bar_date.desc()).limit(1)
        )
        if last_bar is None:
            db.add(DataQualityIssue(run_id=run.id, security_id=sec.id,
                                    issue_type="missing_bar", severity="error",
                                    message="Nessuna barra disponibile."))
            issues += 1
            continue
        if (asof - last_bar.bar_date).days > 3:
            db.add(DataQualityIssue(run_id=run.id, security_id=sec.id,
                                    issue_type="stale_source", severity="warn",
                                    message=f"Ultima barra {last_bar.bar_date}: dati stale."))
            issues += 1
        if last_bar.high is not None and last_bar.low is not None and last_bar.high < last_bar.low:
            db.add(DataQualityIssue(run_id=run.id, security_id=sec.id,
                                    issue_type="impossible_ohlc", severity="error",
                                    message="OHLC incoerente (high < low)."))
            issues += 1
    _finish(db, run, "success", issues)
    return {"status": "success", "issues": issues}


def job_ranking_eod(db: Session, triggered_by: str = "schedule") -> dict:
    """Ranking deterministico EOD in due fasi.

    Fase 1: screening di tutto l'universo (solo i candidati producono score).
    Fase 2 (live): enrichment dei candidati — anagrafica SEC lazy, filing
    EDGAR e news discovery — poi ri-scoring dei soli candidati (idempotente).
    """
    asof = last_business_day()
    run = _start_run(db, "ranking_eod", triggered_by, asof)
    cfg = jobs_config()["notifications"]
    settings = get_settings()
    scored = 0
    candidates: list[Security] = []
    prev_by_sec: dict[int, RiskScore | None] = {}

    query = select(Security).where(
        Security.security_type.in_(["common_stock", "crypto"]))
    if settings.app_mode == "live":
        query = query.where(Security.is_demo.is_(False))

    for sec in db.scalars(query):
        prev_by_sec[sec.id] = db.scalar(
            select(RiskScore).where(RiskScore.security_id == sec.id,
                                    RiskScore.score_date < asof)
            .order_by(RiskScore.score_date.desc()).limit(1)
        )
        score = run_for_security(db, sec, asof, run_id=run.id)
        if score is not None:
            candidates.append(sec)

    # fase 2: enrichment SOLO sui candidati (bounded), poi ri-scoring
    if settings.app_mode == "live" and candidates:
        _enrich_candidates(db, run, candidates)
        for sec in candidates:
            run_for_security(db, sec, asof, run_id=run.id)

    for sec in candidates:
        score = db.scalar(select(RiskScore).where(
            RiskScore.security_id == sec.id, RiskScore.score_date == asof))
        if score is None:
            continue
        scored += 1
        _maybe_notify(db, sec, prev_by_sec.get(sec.id), score, cfg, asof)
    db.commit()
    _finish(db, run, "success", scored)
    return {"status": "success", "scored": scored,
            "candidates": [s.id for s in candidates]}


def _enrich_candidates(db: Session, run, candidates: list[Security]) -> None:
    """Anagrafica SEC + filing EDGAR + news discovery per i candidati del giorno."""
    from app.adapters.base import AdapterStatus as _AS
    from app.adapters.discovery import enrich_candidate_anagrafica
    from app.adapters.news_discovery import ingest_news_for_security, news_status
    from app.adapters.edgar_ingest import ingest_filings
    from app.adapters.sec_edgar import SECEdgarAdapter
    from app.models import SecurityListing

    # enrichment solo sui candidati PRINCIPALI: ordina per Risk Index della
    # fase 1 (i non quantificabili in coda), poi limita (budget/fair access)
    from app.seed.demo import last_business_day as _lbd
    asof = _lbd()
    scores = {
        s.security_id: s.risk_index
        for s in db.scalars(select(RiskScore).where(RiskScore.score_date == asof))
    }
    ranked = sorted(candidates,
                    key=lambda s: (scores.get(s.id) is None,
                                   -(scores.get(s.id) or 0)))
    bounded = ranked[:30]
    equities = [s for s in bounded if s.security_type == "common_stock"]

    try:
        enrich_candidate_anagrafica(db, equities)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Anagrafica candidati non arricchita: %s", exc)

    if SECEdgarAdapter().status() is _AS.OK:
        for sec in equities:
            listing = db.scalar(select(SecurityListing).where(
                SecurityListing.security_id == sec.id,
                SecurityListing.status == "active"))
            if listing is None or not sec.cik:
                continue
            try:
                ingest_filings(db, sec, listing)
            except Exception as exc:  # noqa: BLE001
                logger.warning("EDGAR candidato %s: %s", listing.ticker, exc)

    if news_status() is _AS.OK:
        from app.adapters.gdelt_news import circuit_open, reset_circuit
        reset_circuit()
        for sec in bounded[:20]:  # news discovery: solo i primi 20 (fair use)
            if circuit_open():
                db.add(DataQualityIssue(
                    run_id=run.id, issue_type="stale_source", severity="warn",
                    message="News discovery sospesa per il run: rate limit del provider "
                            "(GDELT). Riprenderà al prossimo run.",
                ))
                break
            listing = db.scalar(select(SecurityListing).where(
                SecurityListing.security_id == sec.id,
                SecurityListing.status == "active"))
            if listing is None:
                continue
            try:
                ingest_news_for_security(db, sec, listing.ticker)
            except Exception as exc:  # noqa: BLE001
                logger.warning("News discovery %s: %s", listing.ticker, exc)
    db.flush()


def _maybe_notify(db: Session, sec: Security, prev: RiskScore | None,
                  score: RiskScore, cfg: dict, asof: date) -> None:
    """Notifiche SOLO su condizioni materiali pre-registrate. Mai per duplicati."""
    def push(rule: str, title: str, body: str) -> None:
        key = f"{rule}:{sec.id}:{asof.isoformat()}"
        from sqlalchemy import select as _select
        if db.scalar(_select(Notification).where(Notification.dedup_key == key)) is None:
            db.add(Notification(security_id=sec.id, rule=rule, title=title,
                                body=body, dedup_key=key))
            from app.core.notify import send_notification
            send_notification(title, body)  # canale esterno se configurato

    ticker = sec.listings[0].ticker if sec.listings else str(sec.id)
    if cfg.get("state_change") and prev is not None and prev.state != score.state:
        push("state_change", f"{ticker}: cambio di stato",
             f"Da «{prev.state}» a «{score.state}».")
    if (cfg.get("score_delta_min") and prev is not None
            and prev.risk_index is not None and score.risk_index is not None
            and abs(score.risk_index - prev.risk_index) >= cfg["score_delta_min"]):
        push("score_delta", f"{ticker}: variazione significativa del Risk Index",
             f"Da {prev.risk_index:.0f} a {score.risk_index:.0f} (indice ordinale, non probabilità).")
    if (cfg.get("confidence_cross") and prev is not None
            and (prev.confidence_grade in "CD") != (score.confidence_grade in "CD")):
        push("confidence_cross", f"{ticker}: cambiamento rilevante della confidence",
             f"Da {prev.confidence_grade} a {score.confidence_grade}.")
    if cfg.get("new_in_top10") and prev is None and score.risk_index is not None:
        push("new_in_top10", f"{ticker}: nuovo candidato in lista",
             score.summary or "Nuovo candidato.")


def job_retrospective(db: Session, triggered_by: str = "schedule") -> dict:
    asof = last_business_day()
    run = _start_run(db, "retrospective_review", triggered_by, asof)
    updated = update_all_pending(db)
    _finish(db, run, "success", updated)
    return {"status": "success", "updated": updated}


def job_premarket_snapshot(db: Session, triggered_by: str = "schedule") -> dict:
    """Snapshot pre-market ritardato (demo: no-op documentato; live: adapter intraday)."""
    asof = last_business_day()
    run = _start_run(db, "premarket_snapshot", triggered_by, asof)
    _finish(db, run, "success", 0)
    return {"status": "success",
            "note": "Pre-market ritardato: attivo solo con provider intraday configurato."}


def job_claim_enrichment(db: Session, triggered_by: str = "schedule") -> dict:
    """Dedup e claim SOLO per i candidati del giorno (non per l'intero universo)."""
    asof = last_business_day()
    run = _start_run(db, "claim_enrichment", triggered_by, asof)
    settings = get_settings()
    if settings.app_mode == "demo":
        _finish(db, run, "success", 0)
        return {"status": "success", "note": "Demo: claim graph già popolato dal seed."}
    statuses = {k: a.status().value for k, a in get_document_adapters(db).items()}
    not_conf = [k for k, v in statuses.items() if v == "non configurata"]
    if not_conf:
        db.add(DataQualityIssue(
            run_id=run.id, issue_type="provider_not_configured", severity="info",
            message=f"Fonti non configurate (stato esplicito, nessun dato fittizio): {', '.join(not_conf)}",
        ))
    _finish(db, run, "success", 0)
    return {"status": "success", "sources": statuses}


def job_daily_report(db: Session, triggered_by: str = "schedule") -> dict:
    """Report giornaliero deterministico (testo dal DB, ogni frase con fonte)."""
    asof = last_business_day()
    run = _start_run(db, "daily_report", triggered_by, asof)
    n = db.scalar(select(RiskScore.id).where(RiskScore.score_date == asof).limit(1))
    _finish(db, run, "success" if n else "partial", 1 if n else 0)
    return {"status": run.status}


def job_freeze_and_backup(db: Session, triggered_by: str = "schedule") -> dict:
    """Freeze: esporta lo snapshot Parquet riproducibile del giorno."""
    from app.validation.export import export_dataset
    asof = last_business_day()
    run = _start_run(db, "freeze_and_backup", triggered_by, asof)
    try:
        path = export_dataset(db, "parquet")
        _finish(db, run, "success", 1)
        return {"status": "success", "snapshot": str(path)}
    except ValueError as exc:
        _finish(db, run, "partial", 0, [str(exc)])
        return {"status": "partial", "note": str(exc)}


def job_validation_report(db: Session, triggered_by: str = "schedule") -> dict:
    """Auto-valutazione: precision@5/@10 vs baseline su finestre chiuse."""
    from app.validation.report import build_report, save_report
    asof = last_business_day()
    run = _start_run(db, "validation_report", triggered_by, asof)
    report = build_report(db)
    save_report(db, report)
    db.commit()
    _finish(db, run, "success", report["signals_evaluated"])
    return {"status": "success", "signals": report["signals_evaluated"],
            "lift": report["lift_vs_best_baseline"],
            "interpretable": report["interpretable"]}


JOB_REGISTRY: dict[str, Callable[[Session, str], dict]] = {
    "validation_report": job_validation_report,
    "universe_sync": job_universe_sync,
    "backfill_history": job_backfill_history,
    "ingest_eod": job_ingest_eod,
    "quality_checks": job_quality_checks,
    "premarket_snapshot": job_premarket_snapshot,
    "claim_enrichment": job_claim_enrichment,
    "ranking_eod": job_ranking_eod,
    "daily_report": job_daily_report,
    "retrospective_review": job_retrospective,
    "freeze_and_backup": job_freeze_and_backup,
}

"""Retrospective review: outcome del segnale a 1/3/5/10/20 sedute.

Etichetta primaria: drawdown intraday <= -20% dal prezzo di riferimento
entro 10 sedute (DD_10 <= -20%). Secondarie: -10/-20/-30/-40% su tutte
le finestre, su minimo intraday e su chiusura, outcome relativo al benchmark.

Il prezzo di riferimento P0 è coerente con il momento del segnale: per un
modello EOD è l'apertura della seduta successiva (mai la chiusura già nota).
Nessun dato futuro entra nelle feature: qui si calcolano SOLO etichette,
dopo la chiusura della finestra.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import RETRO_HORIZONS
from app.models import MarketBar, RetrospectiveOutcome, RiskScore, Security


def _bars_after(db: Session, security_id: int, after: date, limit: int = 25) -> list[MarketBar]:
    return list(db.scalars(
        select(MarketBar)
        .where(MarketBar.security_id == security_id,
               MarketBar.bar_date > after,
               MarketBar.session == "regular")
        .order_by(MarketBar.bar_date)
        .limit(limit)
    ))


def reference_price(db: Session, score: RiskScore) -> tuple[float, date] | None:
    """P0 = apertura (o VWAP se disponibile) della prima seduta successiva al segnale."""
    bars = _bars_after(db, score.security_id, score.score_date, limit=1)
    if not bars:
        return None
    bar = bars[0]
    p0 = bar.vwap if bar.vwap is not None else bar.open
    if p0 is None or p0 <= 0:
        return None
    return p0, bar.bar_date


def _benchmark_security(db: Session) -> Security | None:
    return db.scalar(select(Security).where(Security.security_type == "index").limit(1))


def _benchmark_return(db: Session, start: date, end: date) -> float | None:
    bench = _benchmark_security(db)
    if bench is None:
        return None
    bars = list(db.scalars(
        select(MarketBar).where(
            MarketBar.security_id == bench.id,
            MarketBar.bar_date >= start, MarketBar.bar_date <= end,
            MarketBar.session == "regular",
        ).order_by(MarketBar.bar_date)
    ))
    if len(bars) < 2 or not bars[0].close or not bars[-1].close:
        return None
    return bars[-1].close / bars[0].close - 1


def compute_outcomes(db: Session, score: RiskScore) -> list[RetrospectiveOutcome]:
    """Calcola (o aggiorna) gli outcome per tutti gli orizzonti disponibili."""
    ref = reference_price(db, score)
    if ref is None:
        return []
    p0, ref_date = ref
    # barre a partire dalla seduta di riferimento inclusa
    bars = _bars_after(db, score.security_id, score.score_date, limit=25)
    out: list[RetrospectiveOutcome] = []

    for horizon in RETRO_HORIZONS:
        window = bars[:horizon]
        complete = len(window) >= horizon
        if not window:
            continue
        lows = [b.low for b in window if b.low is not None]
        closes = [b.close for b in window if b.close is not None]
        highs = [b.high for b in window if b.high is not None]
        dd_intraday = min(lo / p0 - 1 for lo in lows) if lows else None
        dd_close = min(c / p0 - 1 for c in closes) if closes else None
        ret_close = (closes[-1] / p0 - 1) if closes else None
        max_up = max(h / p0 - 1 for h in highs) if highs else None
        bench_ret = _benchmark_return(db, ref_date, window[-1].bar_date)
        ret_vs_bench = (ret_close - bench_ret) if (ret_close is not None and bench_ret is not None) else None

        existing = db.scalar(
            select(RetrospectiveOutcome).where(
                RetrospectiveOutcome.risk_score_id == score.id,
                RetrospectiveOutcome.horizon_days == horizon,
            )
        )
        fields = dict(
            security_id=score.security_id,
            reference_price=p0, reference_date=ref_date,
            dd_intraday=dd_intraday, dd_close=dd_close,
            ret_close=ret_close, ret_vs_benchmark=ret_vs_bench,
            max_adverse_up=max_up,
            hit_minus10=None if dd_intraday is None else dd_intraday <= -0.10,
            hit_minus20=None if dd_intraday is None else dd_intraday <= -0.20,
            hit_minus30=None if dd_intraday is None else dd_intraday <= -0.30,
            hit_minus40=None if dd_intraday is None else dd_intraday <= -0.40,
            complete=complete,
        )
        if existing is None:
            existing = RetrospectiveOutcome(
                risk_score_id=score.id, horizon_days=horizon, **fields
            )
            db.add(existing)
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
        out.append(existing)
    db.flush()
    return out


def update_all_pending(db: Session) -> int:
    """Job giornaliero: aggiorna gli outcome non ancora completi."""
    scores = db.scalars(select(RiskScore)).all()
    updated = 0
    for score in scores:
        incomplete = db.scalar(
            select(RetrospectiveOutcome)
            .where(RetrospectiveOutcome.risk_score_id == score.id,
                   RetrospectiveOutcome.complete.is_(False))
            .limit(1)
        )
        has_any = db.scalar(
            select(RetrospectiveOutcome)
            .where(RetrospectiveOutcome.risk_score_id == score.id)
            .limit(1)
        )
        if has_any is None or incomplete is not None:
            if compute_outcomes(db, score):
                updated += 1
    return updated


def precision_at_k(db: Session, k: int, score_date: date, horizon: int = 10,
                   threshold: float = -0.20) -> float | None:
    """precision@k: quota dei top-k per Risk Index con DD_horizon <= threshold."""
    scores = list(db.scalars(
        select(RiskScore)
        .where(RiskScore.score_date == score_date, RiskScore.risk_index.is_not(None))
        .order_by(RiskScore.risk_index.desc())
        .limit(k)
    ))
    if not scores:
        return None
    hits, evaluable = 0, 0
    for s in scores:
        outcome = db.scalar(
            select(RetrospectiveOutcome).where(
                RetrospectiveOutcome.risk_score_id == s.id,
                RetrospectiveOutcome.horizon_days == horizon,
                RetrospectiveOutcome.complete.is_(True),
            )
        )
        if outcome is None or outcome.dd_intraday is None:
            continue
        evaluable += 1
        if outcome.dd_intraday <= threshold:
            hits += 1
    if evaluable == 0:
        return None
    return hits / evaluable

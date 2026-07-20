"""Baseline semplici da battere (F.5 della ricerca).

Il Risk Index è utile solo se identifica i futuri drawdown meglio di regole
elementari. Ogni baseline produce un ranking sullo stesso set di candidati.
Il ranking casuale è riproducibile (seed esplicito).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FeatureSnapshot


@dataclass
class BaselineRank:
    security_id: int
    value: float | None


def _snapshots(db: Session, score_date: date) -> list[FeatureSnapshot]:
    return list(db.scalars(
        select(FeatureSnapshot).where(
            FeatureSnapshot.snapshot_date == score_date,
            FeatureSnapshot.is_candidate.is_(True),
        )
    ))


def _rank_by(snaps: list[FeatureSnapshot], key: str, descending: bool = True) -> list[BaselineRank]:
    ranks = [BaselineRank(s.security_id, s.features.get(key)) for s in snaps]
    with_value = [r for r in ranks if r.value is not None]
    missing = [r for r in ranks if r.value is None]  # i mancanti in coda, mai trattati come 0
    with_value.sort(key=lambda r: r.value, reverse=descending)
    return with_value + missing


def baseline_ret_recent(db: Session, score_date: date, window: int = 5) -> list[BaselineRank]:
    """Rendimento recente (1/5/20 giorni)."""
    key = {1: "ret_1d", 5: "ret_5d", 20: "ret_20d"}[window]
    return _rank_by(_snapshots(db, score_date), key)


def baseline_rvol(db: Session, score_date: date) -> list[BaselineRank]:
    return _rank_by(_snapshots(db, score_date), "rvol")


def baseline_atr(db: Session, score_date: date) -> list[BaselineRank]:
    return _rank_by(_snapshots(db, score_date), "atr_14")


def baseline_dist_ema(db: Session, score_date: date) -> list[BaselineRank]:
    """Distanza dalla media (EMA20 in ATR)."""
    return _rank_by(_snapshots(db, score_date), "dist_ema20_atr")


def baseline_market_cap(db: Session, score_date: date) -> list[BaselineRank]:
    """Capitalizzazione (ascendente: i piccoli prima)."""
    return _rank_by(_snapshots(db, score_date), "market_cap", descending=False)


def baseline_ret_plus_rvol(db: Session, score_date: date) -> list[BaselineRank]:
    """Combinazione rendimento 5g + RVOL (somma dei ranghi)."""
    snaps = _snapshots(db, score_date)
    by_ret = {r.security_id: i for i, r in enumerate(baseline_ret_recent(db, score_date, 5))}
    by_rvol = {r.security_id: i for i, r in enumerate(baseline_rvol(db, score_date))}
    combined = [BaselineRank(s.security_id, -(by_ret.get(s.security_id, 999)
                                              + by_rvol.get(s.security_id, 999)))
                for s in snaps]
    combined.sort(key=lambda r: r.value, reverse=True)
    return combined


def baseline_random(db: Session, score_date: date, seed: int = 42) -> list[BaselineRank]:
    """Ranking casuale riproducibile: stesso seed, stesso ordine."""
    snaps = _snapshots(db, score_date)
    rng = random.Random(seed + score_date.toordinal())
    ranks = [BaselineRank(s.security_id, rng.random()) for s in snaps]
    ranks.sort(key=lambda r: r.value, reverse=True)
    return ranks


ALL_BASELINES = {
    "ret_1d": lambda db, d: baseline_ret_recent(db, d, 1),
    "ret_5d": lambda db, d: baseline_ret_recent(db, d, 5),
    "ret_20d": lambda db, d: baseline_ret_recent(db, d, 20),
    "rvol": baseline_rvol,
    "atr": baseline_atr,
    "dist_ema20": baseline_dist_ema,
    "market_cap": baseline_market_cap,
    "ret_plus_rvol": baseline_ret_plus_rvol,
    "random": baseline_random,
}

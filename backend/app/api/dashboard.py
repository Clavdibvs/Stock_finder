"""Dashboard giornaliera: classifica limitata (max 10-20) e spiegabile."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serialize import score_row
from app.config import candidates_config, get_settings
from app.constants import (
    DISCLAIMER, STATE_BELOW_THRESHOLD, STATE_ELEVATED, STATE_MONITOR,
)
from app.core.security import require_auth
from app.db import get_db
from app.models import RiskScore, WatchlistItem

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# ordinamento in dashboard: prima gli stati informativi (score + gate con
# contenuto), in fondo il non-quantificabile/dati insufficienti — con il
# full-market i penny stock illiquidi non devono seppellire la classifica
from app.constants import STATE_BINARY_EVENT, STATE_INSUFFICIENT_DATA,     STATE_POSSIBLE_SQUEEZE, STATE_UNQUANTIFIABLE  # noqa: E402

_STATE_ORDER = {s: i for i, s in enumerate([
    STATE_ELEVATED, STATE_BINARY_EVENT, STATE_POSSIBLE_SQUEEZE,
    STATE_MONITOR, STATE_UNQUANTIFIABLE, STATE_INSUFFICIENT_DATA,
    STATE_BELOW_THRESHOLD,
])}


@router.get("")
def daily_list(
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
    day: str | None = Query(default=None, description="YYYY-MM-DD; default ultimo giorno con score"),
    state: str | None = None,
    event_type: str | None = None,
    confidence: str | None = None,
    max_market_cap: float | None = None,
    min_market_cap: float | None = None,
    watchlist_only: bool = False,
    new_only: bool = Query(default=False, description="solo nuovi candidati"),
    changed_only: bool = Query(default=False, description="solo cambiamenti materiali"),
):
    settings = get_settings()
    target_date = date.fromisoformat(day) if day else db.scalar(
        select(RiskScore.score_date).order_by(RiskScore.score_date.desc()).limit(1)
    )
    if target_date is None:
        return {"date": None, "items": [], "disclaimer": DISCLAIMER,
                "mode": settings.app_mode, "demo": settings.app_mode == "demo"}

    scores = db.scalars(
        select(RiskScore).where(RiskScore.score_date == target_date)
    ).all()

    watch_ids = {
        w.security_id for w in db.scalars(
            select(WatchlistItem).where(WatchlistItem.removed_at.is_(None))
        )
    }

    rows = []
    for s in scores:
        if s.state == STATE_BELOW_THRESHOLD:
            continue  # mai nella lista primaria
        if state and s.state != state:
            continue
        if event_type and s.catalyst_type != event_type:
            continue
        if confidence and s.confidence_grade != confidence:
            continue
        if watchlist_only and s.security_id not in watch_ids:
            continue
        if new_only or changed_only:
            prev = db.scalar(
                select(RiskScore).where(RiskScore.security_id == s.security_id,
                                        RiskScore.score_date < target_date)
                .order_by(RiskScore.score_date.desc()).limit(1)
            )
            if new_only and prev is not None:
                continue
            if changed_only and (prev is None or prev.state == s.state):
                continue
        row = score_row(db, s)
        if max_market_cap is not None and (row["market_cap"] or 0) > max_market_cap:
            continue
        if min_market_cap is not None and (row["market_cap"] or float("inf")) < min_market_cap:
            continue
        rows.append(row)

    rows.sort(key=lambda r: (
        _STATE_ORDER.get(r["state"], 99),
        -(r["risk_index"] if r["risk_index"] is not None else -1),
    ))
    max_items = candidates_config()["daily_list"]["max_items"]
    return {
        "date": target_date.isoformat(),
        "items": rows[:max_items],
        "total_candidates": len(rows),
        "disclaimer": DISCLAIMER,
        "mode": settings.app_mode,
        "demo": settings.app_mode == "demo",
    }


@router.get("/filters")
def filter_options(db: Session = Depends(get_db), _: str = Depends(require_auth)):
    states = db.scalars(select(RiskScore.state).distinct()).all()
    events = db.scalars(select(RiskScore.catalyst_type).distinct()).all()
    return {
        "states": [s for s in states if s and s != STATE_BELOW_THRESHOLD],
        "event_types": [e for e in events if e],
        "confidence_grades": ["A", "B", "C", "D"],
    }

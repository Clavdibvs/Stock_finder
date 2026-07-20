"""Pagina titolo: perché è entrato, cosa è successo, qualità della narrativa,
rischi della tesi, storico."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serialize import (
    claim_dict, document_dict, factor_dict, outcome_dict, score_row, security_brief,
)
from app.constants import DISCLAIMER
from app.core.security import require_auth
from app.db import get_db
from app.models import (
    Claim, CorporateAction, Document, Event, FeatureSnapshot, MarketBar,
    RetrospectiveOutcome, RiskScore, ScoreFactor, Security,
)

router = APIRouter(prefix="/api/securities", tags=["securities"])


@router.get("/{security_id}")
def security_detail(security_id: int, db: Session = Depends(get_db),
                    _: str = Depends(require_auth)):
    sec = db.get(Security, security_id)
    if sec is None:
        raise HTTPException(status_code=404, detail="Titolo non trovato")

    latest = db.scalar(
        select(RiskScore).where(RiskScore.security_id == security_id)
        .order_by(RiskScore.score_date.desc()).limit(1)
    )
    snapshot = None
    if latest is not None and latest.feature_snapshot_id:
        snapshot = db.get(FeatureSnapshot, latest.feature_snapshot_id)

    # 1. Perché è entrato
    why = {
        "candidate_reasons": snapshot.candidate_reasons if snapshot else [],
        "features": snapshot.features if snapshot else {},
        "missing_fields": snapshot.missing_fields if snapshot else [],
        "config_version": snapshot.config_version if snapshot else None,
        "asof": snapshot.asof_ts.isoformat() if snapshot else None,
    }

    # 2. Cosa è successo: timeline sincronizzata prezzo/volume/eventi/documenti
    bars = db.scalars(
        select(MarketBar).where(MarketBar.security_id == security_id,
                                MarketBar.session == "regular")
        .order_by(MarketBar.bar_date.desc()).limit(90)
    ).all()
    bars = list(reversed(bars))
    events = db.scalars(
        select(Event).where(Event.security_id == security_id).order_by(Event.announced_at)
    ).all()
    docs = db.scalars(
        select(Document).where(Document.security_id == security_id)
        .order_by(Document.first_seen_at)
    ).all()

    timeline = {
        "bars": [{"date": b.bar_date.isoformat(), "open": b.open, "high": b.high,
                  "low": b.low, "close": b.close, "volume": b.volume} for b in bars],
        "events": [{
            "id": e.id, "type": e.event_type, "title": e.title, "status": e.status,
            "is_binary": e.is_binary, "materiality": e.materiality,
            "announced_at": e.announced_at.isoformat() if e.announced_at else None,
            "effective_at": e.effective_at.isoformat() if e.effective_at else None,
            "classified_by": e.classified_by,
        } for e in events],
        "documents": [document_dict(db, d) for d in docs],
    }

    # 3. Qualità della narrativa
    claims = db.scalars(
        select(Claim).where(Claim.security_id == security_id)
    ).all()
    families: dict[int, int] = {}
    for d in docs:
        fam = d.duplicate_family_id or d.id
        families[fam] = families.get(fam, 0) + 1
    move_start = max((e.announced_at for e in events if e.announced_at), default=None)
    narrative = {
        "claims": [claim_dict(db, c) for c in claims],
        "independent_origins": len(families),
        "total_documents": len(docs),
        "duplicate_documents": sum(1 for d in docs if d.is_duplicate),
        "families": [{"family_id": k, "copies": v} for k, v in sorted(families.items())],
        "post_move_documents": sum(
            1 for d in docs
            if move_start and d.published_at and d.published_at > move_start
        ),
    }

    # 4. Rischi della tesi (dal punteggio corrente)
    risks = None
    if latest is not None:
        factors = db.scalars(
            select(ScoreFactor).where(ScoreFactor.risk_score_id == latest.id)
        ).all()
        risks = {
            "state": latest.state,
            "gate_applied": latest.gate_applied,
            "squeeze_hazard": latest.squeeze_hazard,
            "squeeze_unknown": latest.squeeze_unknown,
            "execution_hazard": latest.execution_hazard,
            "borrow_known": False,  # nessuna fonte borrow nell'MVP: sempre esplicito
            "main_contrary_evidence": latest.main_contrary_evidence,
            "invalidation_conditions": latest.invalidation_conditions or [],
            "missing_data": latest.missing_data or [],
            "factors_up": [factor_dict(f) for f in factors if f.direction > 0],
            "factors_down": [factor_dict(f) for f in factors if f.direction < 0],
            "factors_missing": [factor_dict(f) for f in factors if f.missing],
            "factors_neutral": [factor_dict(f) for f in factors
                                if f.direction == 0 and not f.missing],
        }

    # 5. Storico
    history_scores = db.scalars(
        select(RiskScore).where(RiskScore.security_id == security_id)
        .order_by(RiskScore.score_date)
    ).all()
    outcomes = []
    for s in history_scores:
        rows = db.scalars(
            select(RetrospectiveOutcome).where(RetrospectiveOutcome.risk_score_id == s.id)
            .order_by(RetrospectiveOutcome.horizon_days)
        ).all()
        if rows:
            outcomes.append({
                "score_date": s.score_date.isoformat(),
                "risk_index": s.risk_index,
                "state": s.state,
                "horizons": [outcome_dict(o) for o in rows],
            })
    history = {
        "scores": [{
            "date": s.score_date.isoformat(), "risk_index": s.risk_index,
            "state": s.state, "confidence": s.confidence_grade,
            "scoring_version": s.scoring_version, "config_hash": s.config_hash,
        } for s in history_scores],
        "outcomes": outcomes,
    }

    # corporate actions per contesto
    actions = db.scalars(
        select(CorporateAction).where(CorporateAction.security_id == security_id)
    ).all()

    return {
        "security": security_brief(db, sec),
        "current": score_row(db, latest) if latest else None,
        "why_entered": why,
        "timeline": timeline,
        "narrative": narrative,
        "thesis_risks": risks,
        "history": history,
        "corporate_actions": [{
            "type": a.action_type, "ratio": a.ratio,
            "effective_date": a.effective_date.isoformat(),
            "reconciled": a.reconciled, "details": a.details,
        } for a in actions],
        "disclaimer": DISCLAIMER,
    }

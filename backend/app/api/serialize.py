"""Serializzazione dei modelli verso il frontend."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Claim, ClaimRelation, Document, DocumentSource, FeatureSnapshot,
    RetrospectiveOutcome, RiskScore, ScoreFactor, Security, SecurityListing,
    WatchlistItem,
)


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def security_brief(db: Session, sec: Security) -> dict:
    listing = db.scalar(
        select(SecurityListing).where(SecurityListing.security_id == sec.id)
        .order_by(SecurityListing.valid_from.desc()).limit(1)
    )
    return {
        "id": sec.id,
        "stable_id": sec.stable_id,
        "name": sec.name,
        "ticker": listing.ticker if listing else None,
        "exchange": listing.exchange if listing else None,
        "listing_status": listing.status if listing else None,
        "sector": sec.sector,
        "is_demo": sec.is_demo,
    }


def score_row(db: Session, score: RiskScore, sec: Security | None = None,
              features: dict | None = None) -> dict:
    sec = sec or db.get(Security, score.security_id)
    if features is None:
        snap = db.get(FeatureSnapshot, score.feature_snapshot_id) if score.feature_snapshot_id else None
        features = snap.features if snap else {}
    in_watchlist = db.scalar(
        select(WatchlistItem).where(WatchlistItem.security_id == sec.id,
                                    WatchlistItem.removed_at.is_(None)).limit(1)
    ) is not None
    return {
        **security_brief(db, sec),
        "score_id": score.id,
        "score_date": score.score_date.isoformat(),
        "price": features.get("price"),
        "market_cap": features.get("market_cap"),
        "ret_1d": features.get("ret_1d"),
        "ret_5d": features.get("ret_5d"),
        "ret_20d": features.get("ret_20d"),
        "gap": features.get("gap"),
        "premarket_gap": features.get("premarket_gap"),
        "rvol": features.get("rvol"),
        "catalyst_type": score.catalyst_type,
        "risk_index": score.risk_index,
        "confidence": score.confidence_grade,
        "squeeze_hazard": score.squeeze_hazard,
        "squeeze_unknown": score.squeeze_unknown,
        "execution_hazard": score.execution_hazard,
        "dilution_risk": score.dilution_risk,
        "state": score.state,
        "gate_applied": score.gate_applied,
        "summary": score.summary,
        "main_contrary_evidence": score.main_contrary_evidence,
        "independent_origins": score.independent_origins,
        "missing_data": score.missing_data or [],
        "in_watchlist": in_watchlist,
        "updated_at": _iso(score.created_at),
        "scoring_version": score.scoring_version,
        "config_hash": score.config_hash,
    }


def factor_dict(f: ScoreFactor) -> dict:
    return {
        "component": f.component, "name": f.name, "direction": f.direction,
        "value": f.value, "weight": f.weight, "missing": f.missing,
        "explanation": f.explanation,
    }


def document_dict(db: Session, d: Document) -> dict:
    src = db.get(DocumentSource, d.source_id) if d.source_id else None
    family_size = 0
    if d.duplicate_family_id is not None:
        family_size = len(db.scalars(
            select(Document.id).where(Document.duplicate_family_id == d.duplicate_family_id)
        ).all())
    return {
        "id": d.id,
        "security_id": d.security_id,
        "title": d.title,
        "url": d.url_canonical,
        "publisher": d.publisher,
        "author": d.author,
        "source_name": src.name if src else None,
        "source_level": d.source_level,
        "published_at": _iso(d.published_at),
        "effective_at": _iso(d.effective_at),
        "first_seen_at": _iso(d.first_seen_at),
        "retrieved_at": _iso(d.retrieved_at),
        "original_timezone": d.original_timezone,
        "excerpt": d.excerpt,
        "license_state": d.license_state,
        "is_duplicate": d.is_duplicate,
        "duplicate_family_id": d.duplicate_family_id,
        "family_size": family_size,
        "content_hash": d.content_hash,
    }


def claim_dict(db: Session, c: Claim) -> dict:
    relations = db.scalars(
        select(ClaimRelation).where(ClaimRelation.claim_id == c.id)
    ).all()
    inbound = db.scalars(
        select(ClaimRelation).where(ClaimRelation.related_claim_id == c.id)
    ).all()
    return {
        "id": c.id,
        "security_id": c.security_id,
        "subject": c.subject,
        "predicate": c.predicate,
        "object": c.object,
        "figure": c.figure,
        "claim_date": c.claim_date.isoformat() if c.claim_date else None,
        "status": c.status,
        "confirmation_level": c.confirmation_level,
        "evidence_span": c.evidence_span,
        "source_document_id": c.source_document_id,
        "extracted_by": c.extracted_by,
        "relations": [
            {"relation": r.relation, "claim_id": r.related_claim_id, "note": r.note,
             "direction": "out"} for r in relations
        ] + [
            {"relation": r.relation, "claim_id": r.claim_id, "note": r.note,
             "direction": "in"} for r in inbound
        ],
    }


def outcome_dict(o: RetrospectiveOutcome) -> dict:
    return {
        "horizon_days": o.horizon_days,
        "reference_price": o.reference_price,
        "reference_date": o.reference_date.isoformat(),
        "dd_intraday": o.dd_intraday,
        "dd_close": o.dd_close,
        "ret_close": o.ret_close,
        "ret_vs_benchmark": o.ret_vs_benchmark,
        "max_adverse_up": o.max_adverse_up,
        "hit_minus10": o.hit_minus10,
        "hit_minus20": o.hit_minus20,
        "hit_minus30": o.hit_minus30,
        "hit_minus40": o.hit_minus40,
        "complete": o.complete,
    }

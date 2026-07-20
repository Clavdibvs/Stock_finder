"""Pipeline giornaliera: feature -> candidato -> narrativa -> score -> persistenza.

Idempotente: ricalcolare lo stesso giorno sovrascrive lo snapshot/score del
giorno (unique constraint), senza duplicare righe.
"""
from __future__ import annotations

from datetime import date, datetime, time, UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.candidates.features import compute_features
from app.candidates.generator import evaluate
from app.claims.graph import compute_narrative_stats
from app.config import APP_VERSION, candidates_config
from app.constants import BINARY_EVENT_TYPES
from app.models import (
    DataQualityIssue, Event, FeatureSnapshot, RiskScore, ScoreFactor, Security,
)
from app.scoring.engine import EventContext, compute_score


def build_event_context(db: Session, security_id: int, asof: date) -> EventContext:
    ctx = EventContext()
    events = db.scalars(
        select(Event).where(Event.security_id == security_id).order_by(Event.announced_at.desc())
    ).all()
    for ev in events:
        ann = ev.announced_at.date() if ev.announced_at else None
        if ann is not None and ann > asof:
            continue  # point-in-time: eventi futuri non esistono ancora
        if ev.status == "pending" and (ev.is_binary or ev.event_type in BINARY_EVENT_TYPES):
            ctx.has_pending_binary = True
            ctx.pending_binary_types.append(ev.event_type)
        if ctx.dominant_event_type is None and ev.materiality == "high":
            ctx.dominant_event_type = ev.event_type
        if ev.event_type == "offering_or_dilution" and ann is not None and (asof - ann).days <= 30:
            ctx.recent_dilution_filing = True
        if ev.event_type == "offering_or_dilution" and (ev.details or {}).get("shelf_open"):
            ctx.shelf_or_atm_open = True
        if ev.event_type in ("earnings_surprise", "guidance_change") and ann is not None \
                and (asof - ann).days <= 30:
            ctx.has_fundamental_catalyst = True
        if ev.event_type == "halt" and ann is not None and (asof - ann).days <= 5:
            ctx.recent_halt = True
    return ctx


def _asof_ts(asof: date) -> datetime:
    # 16:15 ET ~ 20:15/21:15 UTC; si usa un timestamp deterministico EOD UTC
    return datetime.combine(asof, time(21, 15), tzinfo=UTC)


def move_start_ts(db: Session, security_id: int, asof: date) -> datetime | None:
    """Timestamp di inizio del movimento: l'annuncio dell'evento dominante,
    usato per marcare i documenti pubblicati DOPO il movimento.
    Point-in-time: considera solo eventi annunciati entro asof."""
    ev = db.scalar(
        select(Event)
        .where(Event.security_id == security_id,
               Event.announced_at.is_not(None),
               Event.announced_at <= _asof_ts(asof))
        .order_by(Event.announced_at.desc())
        .limit(1)
    )
    return ev.announced_at if ev else None


def run_for_security(db: Session, security: Security, asof: date,
                     run_id: int | None = None) -> RiskScore | None:
    """Esegue la pipeline per una security. Ritorna il RiskScore o None se soppresso."""
    features = compute_features(db, security.id, asof)

    if features.blocked_unreconciled_action:
        db.add(DataQualityIssue(
            run_id=run_id, security_id=security.id,
            issue_type="unreconciled_corporate_action", severity="error",
            message="Titolo bloccato: corporate action non riconciliata. Nessun segnale generato.",
        ))
        return None

    if features.bars_available == 0:
        db.add(DataQualityIssue(
            run_id=run_id, security_id=security.id,
            issue_type="missing_bar", severity="error",
            message="Nessuna barra disponibile: segnale soppresso.",
        ))
        return None

    decision = evaluate(features, asof)
    if not decision.is_candidate:
        # niente accelerazione+conferma: nessun segnale e nessuno snapshot
        # (con l'universo full-market lo storage resta proporzionato ai candidati)
        return None
    cand_cfg = candidates_config()

    snapshot = db.scalar(
        select(FeatureSnapshot).where(
            FeatureSnapshot.security_id == security.id,
            FeatureSnapshot.snapshot_date == asof,
        )
    )
    payload = dict(
        asof_ts=_asof_ts(asof),
        features=features.to_dict(),
        missing_fields=features.missing,
        is_candidate=decision.is_candidate,
        candidate_reasons=decision.reasons(),
        provider="demo" if security.is_demo else None,
        pipeline_version=APP_VERSION,
        config_version=cand_cfg["version"],
    )
    if snapshot is None:
        snapshot = FeatureSnapshot(security_id=security.id, snapshot_date=asof, **payload)
        db.add(snapshot)
    else:
        for k, v in payload.items():
            setattr(snapshot, k, v)
    db.flush()

    move_ts = move_start_ts(db, security.id, asof)
    narrative = compute_narrative_stats(db, security.id, move_start=move_ts,
                                        asof_ts=_asof_ts(asof))
    ctx = build_event_context(db, security.id, asof)
    result = compute_score(features, narrative, ctx, decision.universe_status)

    summary, contrary = _build_summary(security, features, narrative, ctx, result.state)

    score = db.scalar(
        select(RiskScore).where(
            RiskScore.security_id == security.id, RiskScore.score_date == asof
        )
    )
    fields = dict(
        feature_snapshot_id=snapshot.id,
        risk_index=result.risk_index,
        squeeze_hazard=result.squeeze_hazard,
        squeeze_unknown=result.squeeze_unknown,
        execution_hazard=result.execution_hazard,
        dilution_risk=result.dilution_risk,
        confidence_grade=result.confidence_grade,
        state=result.state,
        gate_applied=result.gate_applied,
        summary=summary,
        main_contrary_evidence=contrary,
        invalidation_conditions=result.invalidation_conditions,
        missing_data=result.missing_data,
        independent_origins=narrative.independent_origins or None,
        catalyst_type=ctx.dominant_event_type,
        scoring_version=result.scoring_version,
        config_hash=result.config_hash,
        code_version=result.code_version,
    )
    if score is None:
        score = RiskScore(security_id=security.id, score_date=asof, **fields)
        db.add(score)
        db.flush()
    else:
        for k, v in fields.items():
            setattr(score, k, v)
        db.flush()
        # sostituisce i fattori precedenti dello stesso giorno
        for old in db.scalars(select(ScoreFactor).where(ScoreFactor.risk_score_id == score.id)):
            db.delete(old)

    for comp in result.components.values():
        if comp.value is None:
            db.add(ScoreFactor(
                risk_score_id=score.id, component=comp.component,
                name=f"Componente {comp.component} non calcolabile",
                direction=0, value=None, weight=comp.weight, missing=True,
                explanation="Dato mancante: NON conteggiato come zero; pesi rinormalizzati e confidence ridotta.",
            ))
            continue
        for factor in comp.factors:
            db.add(ScoreFactor(
                risk_score_id=score.id,
                component=factor["component"],
                name=factor["name"],
                direction=factor["direction"],
                value=factor.get("value"),
                weight=comp.weight,
                missing=False,
                explanation=factor.get("explanation"),
            ))
    db.flush()
    return score


def _build_summary(security: Security, f, n, ctx, state: str) -> tuple[str, str | None]:
    """Frase sintetica deterministica + principale evidenza contraria."""
    bits = []
    if f.ret_1d is not None and abs(f.ret_1d) >= 0.10:
        bits.append(f"rendimento 1g {f.ret_1d:+.0%}")
    elif f.ret_5d is not None and abs(f.ret_5d) >= 0.20:
        bits.append(f"rendimento 5g {f.ret_5d:+.0%}")
    if f.premarket_gap is not None and f.premarket_gap >= 0.15:
        bits.append(f"gap pre-market {f.premarket_gap:+.0%}")
    if f.rvol is not None and f.rvol >= 2:
        bits.append(f"volume {f.rvol:.0f}× la mediana")
    driver = ctx.dominant_event_type or "causa non classificata"
    origin = (f"{n.independent_origins} origine indipendente" if n.independent_origins == 1
              else f"{n.independent_origins} origini indipendenti")
    summary = f"Accelerazione ({', '.join(bits) if bits else 'segnali multipli'}) guidata da {driver}; {origin}."

    contrary = None
    if n.primary_sources > 0 and n.central_claim_status == "fatto":
        contrary = "Il claim centrale è confermato da fonte primaria: il movimento può riflettere informazione reale."
    elif ctx.has_fundamental_catalyst:
        contrary = "È presente un catalizzatore fondamentale dichiarato (earnings/guidance): il re-rating potrebbe essere sostenibile."
    elif ctx.has_pending_binary:
        contrary = "L'esito binario pendente può risolversi a favore del titolo e produrre un ulteriore gap rialzista."
    elif n.central_claim_status == "rumor":
        contrary = "Il rumor proviene da fonte giornalistica credibile: una conferma produrrebbe un gap contrario alla tesi."
    return summary, contrary

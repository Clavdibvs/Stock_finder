"""Data quality e run: stato provider, run, issue, rilancio manuale dei job."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.registry import provider_statuses
from app.api.serialize import security_brief
from app.core.audit import audit
from app.core.security import require_auth
from app.db import get_db
from app.jobs.runner import JOB_REGISTRY
from app.models import AIInvocation, DataQualityIssue, IngestionRun, Security

router = APIRouter(prefix="/api/quality", tags=["quality"])


@router.get("")
def quality_overview(db: Session = Depends(get_db), _: str = Depends(require_auth)):
    runs = db.scalars(
        select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(50)
    ).all()
    issues = db.scalars(
        select(DataQualityIssue).where(DataQualityIssue.resolved_at.is_(None))
        .order_by(DataQualityIssue.detected_at.desc()).limit(200)
    ).all()
    rejected_ai = db.scalars(
        select(AIInvocation).where(AIInvocation.status != "ok")
        .order_by(AIInvocation.ts.desc()).limit(50)
    ).all()

    issue_rows = []
    for i in issues:
        sec = db.get(Security, i.security_id) if i.security_id else None
        issue_rows.append({
            "id": i.id, "type": i.issue_type, "severity": i.severity,
            "message": i.message, "detected_at": i.detected_at.isoformat(),
            "security": security_brief(db, sec) if sec else None,
        })

    from app.models import AppSetting
    validation = db.get(AppSetting, "validation_report")
    return {
        "validation": validation.value if validation else None,
        "providers": provider_statuses(db),
        "runs": [{
            "id": r.id, "job": r.job_name, "status": r.status,
            "started_at": r.started_at.isoformat(),
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "items": r.items_processed, "triggered_by": r.triggered_by,
            "errors": r.errors,
        } for r in runs],
        "issues": issue_rows,
        "ai_rejected": [{
            "id": a.id, "ts": a.ts.isoformat(), "model": a.model,
            "status": a.status, "purpose": a.purpose,
        } for a in rejected_ai],
        "allowed_jobs": sorted(JOB_REGISTRY.keys()),
    }


@router.post("/jobs/{job_name}/run")
def run_job_manually(job_name: str, db: Session = Depends(get_db),
                     user: str = Depends(require_auth)):
    """Rilancio manuale di un job CONSENTITO (solo quelli in registry)."""
    fn = JOB_REGISTRY.get(job_name)
    if fn is None:
        raise HTTPException(status_code=404, detail="Job non consentito o inesistente")
    audit(db, actor=user, action="manual_job_run", entity_type="job", entity_id=job_name)
    db.commit()
    result = fn(db, "manual")
    return {"job": job_name, "result": result}


@router.post("/retention/apply")
def apply_retention(db: Session = Depends(get_db), user: str = Depends(require_auth)):
    """Cancellazione su richiesta dei contenuti community/opinione oltre retention.

    Elimina l'estratto e l'autore dei documenti di livello 7-9 più vecchi di
    DDR_RETENTION_SOCIAL_DAYS (restano URL, hash e metadata minimi per l'audit).
    Azione tracciata nell'audit log.
    """
    from datetime import timedelta

    from app.config import get_settings
    from app.models import Document, utcnow

    settings = get_settings()
    cutoff = utcnow() - timedelta(days=settings.retention_social_days)
    docs = db.scalars(
        select(Document).where(Document.source_level.in_([7, 8, 9]),
                               Document.first_seen_at < cutoff)
    ).all()
    purged = 0
    for d in docs:
        if d.excerpt is not None or d.author is not None:
            d.excerpt = None
            d.author = None
            purged += 1
    audit(db, actor=user, action="retention_apply",
          details={"purged": purged, "cutoff": cutoff.isoformat(),
                   "levels": [7, 8, 9]})
    db.commit()
    return {"purged": purged, "cutoff": cutoff.isoformat()}

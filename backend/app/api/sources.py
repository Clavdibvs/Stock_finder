"""Fonti, claim e correzioni manuali (con audit trail)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serialize import claim_dict, document_dict
from app.constants import CLAIM_STATUSES
from app.core.audit import audit
from app.core.security import require_auth
from app.db import get_db
from app.models import Claim, Document, DocumentSource, ManualOverride

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("/registry")
def source_registry(db: Session = Depends(get_db), _: str = Depends(require_auth)):
    sources = db.scalars(select(DocumentSource).order_by(DocumentSource.default_source_level)).all()
    return [{
        "id": s.id, "name": s.name, "domain": s.domain, "publisher": s.publisher,
        "default_source_level": s.default_source_level,
        "license_status": s.license_status, "retention_policy": s.retention_policy,
        "configured": s.configured, "enabled": s.enabled, "notes": s.notes,
    } for s in sources]


@router.get("/documents")
def documents(db: Session = Depends(get_db), _: str = Depends(require_auth),
              security_id: int | None = None, include_duplicates: bool = True,
              limit: int = 200):
    q = select(Document).order_by(Document.first_seen_at.desc()).limit(min(limit, 500))
    if security_id is not None:
        q = q.where(Document.security_id == security_id)
    if not include_duplicates:
        q = q.where(Document.is_duplicate.is_(False))
    return [document_dict(db, d) for d in db.scalars(q)]


@router.get("/claims")
def claims(db: Session = Depends(get_db), _: str = Depends(require_auth),
           security_id: int | None = None):
    q = select(Claim).order_by(Claim.created_at.desc())
    if security_id is not None:
        q = q.where(Claim.security_id == security_id)
    return [claim_dict(db, c) for c in db.scalars(q)]


class ClaimOverride(BaseModel):
    status: str = Field(description="Nuovo stato del claim")
    reason: str = Field(min_length=5, max_length=1000)


@router.post("/claims/{claim_id}/override")
def override_claim(claim_id: int, payload: ClaimOverride,
                   db: Session = Depends(get_db), user: str = Depends(require_auth)):
    """Correzione manuale con audit trail: mai silenziosa."""
    if payload.status not in CLAIM_STATUSES:
        raise HTTPException(status_code=422, detail=f"Stato non valido: {payload.status}")
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim non trovato")
    old = claim.status
    if old == payload.status:
        return claim_dict(db, claim)
    claim.status = payload.status
    claim.extracted_by = "manual"
    db.add(ManualOverride(
        entity_type="claim", entity_id=claim.id, field="status",
        old_value=old, new_value=payload.status, reason=payload.reason, created_by=user,
    ))
    audit(db, actor=user, action="manual_override", entity_type="claim",
          entity_id=claim.id,
          details={"field": "status", "old": old, "new": payload.status,
                   "reason": payload.reason})
    db.commit()
    return claim_dict(db, claim)


@router.get("/overrides")
def overrides(db: Session = Depends(get_db), _: str = Depends(require_auth)):
    rows = db.scalars(select(ManualOverride).order_by(ManualOverride.created_at.desc())).all()
    return [{
        "id": o.id, "entity_type": o.entity_type, "entity_id": o.entity_id,
        "field": o.field, "old_value": o.old_value, "new_value": o.new_value,
        "reason": o.reason, "created_by": o.created_by,
        "created_at": o.created_at.isoformat(),
    } for o in rows]

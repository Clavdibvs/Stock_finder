"""Audit log append-only con catena di hash.

Ogni record incorpora l'hash del precedente: la manomissione di una riga
invalida tutte le successive. Nessun endpoint di modifica o cancellazione.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, utcnow


def _row_hash(prev_hash: str | None, actor: str, action: str,
              entity_type: str | None, entity_id: str | None,
              details: dict | None, ts: str) -> str:
    payload = json.dumps(
        {"prev": prev_hash, "actor": actor, "action": action,
         "etype": entity_type, "eid": entity_id, "details": details, "ts": ts},
        sort_keys=True, default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def audit(db: Session, actor: str, action: str,
          entity_type: str | None = None, entity_id: str | int | None = None,
          details: dict | None = None) -> AuditLog:
    last = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    prev_hash = last.hash if last else None
    ts = utcnow()
    entry = AuditLog(
        ts=ts,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details,
        prev_hash=prev_hash,
        hash=_row_hash(prev_hash, actor, action, entity_type,
                       str(entity_id) if entity_id is not None else None,
                       details, ts.isoformat()),
    )
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session) -> bool:
    """Verifica l'integrità dell'intera catena."""
    prev_hash: str | None = None
    for row in db.scalars(select(AuditLog).order_by(AuditLog.id)):
        expected = _row_hash(prev_hash, row.actor, row.action, row.entity_type,
                             row.entity_id, row.details, row.ts.isoformat())
        if row.hash != expected or row.prev_hash != prev_hash:
            return False
        prev_hash = row.hash
    return True

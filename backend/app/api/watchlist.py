"""Watchlist personale: aggiunta/rimozione manuale, note. Nessun trading."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serialize import score_row, security_brief
from app.core.audit import audit
from app.core.security import require_auth
from app.db import get_db
from app.models import Notification, RiskScore, Security, WatchlistItem, utcnow

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("")
def list_watchlist(db: Session = Depends(get_db), _: str = Depends(require_auth)):
    items = db.scalars(
        select(WatchlistItem).where(WatchlistItem.removed_at.is_(None))
        .order_by(WatchlistItem.created_at.desc())
    ).all()
    out = []
    for item in items:
        sec = db.get(Security, item.security_id)
        latest = db.scalar(
            select(RiskScore).where(RiskScore.security_id == item.security_id)
            .order_by(RiskScore.score_date.desc()).limit(1)
        )
        out.append({
            "item_id": item.id,
            "note": item.note,
            "added_at": item.created_at.isoformat(),
            "security": security_brief(db, sec),
            "latest_score": score_row(db, latest) if latest else None,
        })
    return out


class WatchlistAdd(BaseModel):
    security_id: int
    note: str | None = Field(default=None, max_length=2000)


@router.post("")
def add_item(payload: WatchlistAdd, db: Session = Depends(get_db),
             user: str = Depends(require_auth)):
    sec = db.get(Security, payload.security_id)
    if sec is None:
        raise HTTPException(status_code=404, detail="Titolo non trovato")
    existing = db.scalar(
        select(WatchlistItem).where(WatchlistItem.security_id == payload.security_id,
                                    WatchlistItem.removed_at.is_(None))
    )
    if existing is not None:
        return {"item_id": existing.id, "already_present": True}
    item = WatchlistItem(security_id=payload.security_id, note=payload.note)
    db.add(item)
    audit(db, actor=user, action="watchlist_add", entity_type="security",
          entity_id=payload.security_id)
    db.commit()
    return {"item_id": item.id, "already_present": False}


class NoteUpdate(BaseModel):
    note: str = Field(max_length=2000)


@router.put("/{item_id}/note")
def update_note(item_id: int, payload: NoteUpdate, db: Session = Depends(get_db),
                user: str = Depends(require_auth)):
    item = db.get(WatchlistItem, item_id)
    if item is None or item.removed_at is not None:
        raise HTTPException(status_code=404, detail="Elemento non trovato")
    item.note = payload.note
    db.commit()
    return {"item_id": item.id, "note": item.note}


@router.delete("/{item_id}")
def remove_item(item_id: int, db: Session = Depends(get_db),
                user: str = Depends(require_auth)):
    item = db.get(WatchlistItem, item_id)
    if item is None or item.removed_at is not None:
        raise HTTPException(status_code=404, detail="Elemento non trovato")
    item.removed_at = utcnow()
    audit(db, actor=user, action="watchlist_remove", entity_type="security",
          entity_id=item.security_id)
    db.commit()
    return {"removed": True}


@router.get("/alerts")
def alert_history(db: Session = Depends(get_db), _: str = Depends(require_auth),
                  limit: int = 100):
    rows = db.scalars(
        select(Notification).order_by(Notification.created_at.desc()).limit(min(limit, 300))
    ).all()
    out = []
    for n in rows:
        sec = db.get(Security, n.security_id) if n.security_id else None
        out.append({
            "id": n.id, "rule": n.rule, "title": n.title, "body": n.body,
            "created_at": n.created_at.isoformat(),
            "read_at": n.read_at.isoformat() if n.read_at else None,
            "security": security_brief(db, sec) if sec else None,
        })
    return out

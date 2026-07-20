"""Adapter reale per il feed Nasdaq Trade Halts (RSS ufficiale, gratuito).

Il feed è aggiornato ogni minuto; noi lo interroghiamo solo nei job
schedulati (mai più spesso del feed). Ogni halt su un titolo dell'universo
diventa un Event `halt` (idempotente per simbolo+data).
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterStatus
from app.config import get_settings
from app.core.http import safe_fetch
from app.models import Event, SecurityListing

logger = logging.getLogger(__name__)

FEED_URL = "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts"


def halts_status() -> AdapterStatus:
    if get_settings().nasdaq_halts_enabled:
        return AdapterStatus.OK
    return AdapterStatus.NOT_CONFIGURED


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_halts(xml_text: str) -> list[dict]:
    """Estrae [{symbol, reason, halt_ts}] dal feed (parsing difensivo)."""
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("Feed halt non parsabile: %s", exc)
        return out
    for item in root.iter():
        if _local(item.tag) != "item":
            continue
        fields: dict[str, str] = {}
        for child in item.iter():
            fields[_local(child.tag)] = (child.text or "").strip()
        symbol = fields.get("issuesymbol") or fields.get("symbol")
        if not symbol:
            continue
        halt_date = fields.get("haltdate", "")
        # il feed usa "HH:MM:SS.mmm": si scarta la parte frazionaria
        halt_time = fields.get("halttime", "").split(".")[0]
        ts = None
        for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
                    "%m/%d/%Y %I:%M:%S %p"):
            try:
                ts = datetime.strptime(f"{halt_date} {halt_time}".strip(), fmt)
                break
            except ValueError:
                continue
        out.append({
            "symbol": symbol.upper(),
            "reason": fields.get("reasoncode") or "n/d",
            "halt_ts": ts.replace(tzinfo=UTC) if ts else None,  # ET≈UTC qui è solo etichetta feed
            "resumption": fields.get("resumptiondate") or None,
        })
    return out


def ingest_halts(db: Session) -> dict:
    """Scarica il feed e registra gli halt dei titoli in universo."""
    resp = safe_fetch(FEED_URL)
    halts = parse_halts(resp.text)
    listings = {
        lst.ticker: lst for lst in db.scalars(
            select(SecurityListing).where(SecurityListing.status == "active")
        )
    }
    created = 0
    for h in halts:
        listing = listings.get(h["symbol"])
        if listing is None:
            continue
        day = h["halt_ts"].date().isoformat() if h["halt_ts"] else "n/d"
        title = f"Halt {h['symbol']} ({h['reason']}) — {day}"
        exists = db.scalar(
            select(Event).where(Event.security_id == listing.security_id,
                                Event.event_type == "halt",
                                Event.title == title)
        )
        if exists is not None:
            continue
        db.add(Event(
            security_id=listing.security_id, event_type="halt", title=title,
            status="occurred", is_binary=False, materiality="high",
            announced_at=h["halt_ts"], classified_by="rule",
            details={"reason_code": h["reason"], "resumption": h["resumption"]},
        ))
        created += 1
    db.flush()
    return {"halts_in_feed": len(halts), "created": created}

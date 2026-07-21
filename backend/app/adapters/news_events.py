"""Classificazione DETERMINISTICA di eventi dalle news (senza AI).

Euristica a parole chiave sui titoli dei documenti di news già ingeriti:
rileva segnali di M&A, evento clinico/FDA e offering e crea Event con
`classified_by="rule_news"`. Filosofia:

- errore verso la CAUTELA: un accenno di M&A/FDA alza il gate
  "EVENTO BINARIO — EVITARE" (direzione sicura per un tool di rischio);
- mai converte un rumor in fatto: gli eventi restano NON confermati
  (`status=pending`), i claim restano `rumor` finché una fonte di livello 1-2
  (filing SEC) non li conferma;
- richiede più origini indipendenti per gli eventi binari (non un singolo
  titolo), riducendo i falsi positivi;
- tutto è tracciabile: ogni evento riporta la parola chiave e il numero di
  origini. È un'euristica trasparente, non una scatola nera.

Limite dichiarato: non legge il merito (es. "endpoint raggiunto" vs "mancato"),
solo la PRESENZA del tema. La lettura fine del contenuto richiede l'AI layer
(opzionale, spento di default).
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, Event, Security, utcnow

logger = logging.getLogger(__name__)

_MATCH_WINDOW_DAYS = 7  # considera solo news recenti

# (regex, event_type, is_binary, materiality, min_origini_indipendenti)
_PATTERNS: list[tuple[re.Pattern, str, bool, str, int]] = [
    (re.compile(
        r"\b(to be acquired|to acquire|acquisition of|acquires|buyout|takeover|"
        r"merger|agrees to (buy|acquire)|in (advanced )?talks to (buy|acquire|merge)|"
        r"nears (a )?deal|bid to acquire|going private)\b", re.I),
     "ma_rumor", True, "high", 2),
    (re.compile(
        r"\b(fda approv|fda reject|fda decision|pdufa|complete response letter|\bcrl\b|"
        r"advisory committee|phase [23] (data|results|readout|trial|study)|"
        r"topline (data|results)|breakthrough therapy|clinical hold|"
        r"meets primary endpoint|misses primary endpoint)\b", re.I),
     "clinical_readout_pending", True, "high", 2),
    (re.compile(
        r"\b(public offering|priced (its )?offering|registered direct offering|"
        r"at[- ]the[- ]market|atm offering|proposed (public )?offering|"
        r"secondary offering|convertible (senior )?notes offering|shelf registration|"
        r"prices \$?\d)\b", re.I),
     "offering_or_dilution", False, "high", 1),
]


def _recent_docs(db: Session, security_id: int) -> list[Document]:
    cutoff = utcnow() - timedelta(days=_MATCH_WINDOW_DAYS)
    return list(db.scalars(
        select(Document).where(Document.security_id == security_id,
                               Document.first_seen_at >= cutoff)
    ))


def _matching_origins(docs: list[Document], pattern: re.Pattern) -> tuple[set, list[Document]]:
    fams: set[int] = set()
    matched: list[Document] = []
    for d in docs:
        text = f"{d.title} {d.excerpt or ''}"
        if pattern.search(text):
            fams.add(d.duplicate_family_id or d.id)
            matched.append(d)
    return fams, matched


def classify_news_events(db: Session, security: Security) -> dict:
    """Crea eventi da segnali news deterministici. Idempotente per tipo evento."""
    docs = _recent_docs(db, security.id)
    if not docs:
        return {"events": 0}
    created = 0
    for pattern, event_type, is_binary, materiality, min_origins in _PATTERNS:
        fams, matched = _matching_origins(docs, pattern)
        if len(fams) < min_origins:
            continue
        # idempotenza: evento news di questo tipo già presente?
        exists = db.scalar(
            select(Event).where(
                Event.security_id == security.id,
                Event.event_type == event_type,
                Event.classified_by == "rule_news",
            ).limit(1)
        )
        if exists is not None:
            continue
        announced = max((d.published_at or d.first_seen_at for d in matched),
                        default=utcnow())
        db.add(Event(
            security_id=security.id, event_type=event_type,
            title=f"Segnale news ({len(fams)} origini indipendenti): {event_type}",
            status="pending" if is_binary else "occurred",
            is_binary=is_binary, materiality=materiality,
            announced_at=announced, classified_by="rule_news",
            classifier_confidence=round(min(1.0, len(fams) / 5), 2),
            details={
                "origins": len(fams),
                "source": "keyword_news_classifier",
                "sample_title": matched[0].title[:200] if matched else None,
                "note": ("Segnale euristico dai titoli news; NON confermato. "
                         "Un rumor resta rumor finché una fonte di livello 1-2 "
                         "(filing SEC) non lo conferma."),
            },
        ))
        created += 1
    db.flush()
    return {"events": created}

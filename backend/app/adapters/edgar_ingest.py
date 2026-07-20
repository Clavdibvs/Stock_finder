"""Ingestione live dei filing SEC EDGAR.

Per ogni security con CIK: scarica i filing recenti, li salva come documenti
(livello 1, dedup su URL canonico) e classifica gli EVENTI con regole
deterministiche sulla tassonomia chiusa:

  S-1 / S-3 / 424B*  -> offering_or_dilution (S-3/424B: shelf/ATM)
  8-K                -> other_material
  Form 4 / 144       -> insider_activity (contesto, non segnale bearish)

Un filing è capacità potenziale, non vendita avvenuta: la nota resta nei
dettagli dell'evento. Idempotente: un URL già visto non crea nulla.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import NotConfiguredError
from app.adapters.sec_edgar import SECEdgarAdapter
from app.claims.dedup import normalize_url
from app.claims.graph import assign_duplicate_family
from app.models import Document, DocumentSource, Event, Security, SecurityListing, utcnow

logger = logging.getLogger(__name__)

# prefisso del titolo documento ("8-K — ...") -> classificazione evento
FORM_EVENT_RULES: list[tuple[str, str, str, dict]] = [
    ("424B", "offering_or_dilution", "high", {"shelf_open": True,
     "nota": "Prospectus supplement: capacità di emissione, non vendita già avvenuta"}),
    ("S-3", "offering_or_dilution", "high", {"shelf_open": True,
     "nota": "Shelf registration: capacità potenziale"}),
    ("S-1", "offering_or_dilution", "high", {"nota": "Registrazione titoli"}),
    ("8-K", "other_material", "high", {}),
    ("4 —", "insider_activity", "low", {"nota": "Form 4: variazione proprietà insider"}),
    ("144", "insider_activity", "low", {"nota": "Form 144: vendita proposta"}),
]


def _sec_source(db: Session) -> DocumentSource:
    src = db.scalar(select(DocumentSource).where(DocumentSource.name == "SEC EDGAR"))
    if src is None:
        src = DocumentSource(
            name="SEC EDGAR", domain="sec.gov",
            publisher="U.S. Securities and Exchange Commission",
            default_source_level=1, license_status="full_allowed",
            configured=True, enabled=True,
            notes="Documenti pubblici federali; fair access con User-Agent identificabile",
        )
        db.add(src)
        db.flush()
    return src


def classify_filing(title: str) -> tuple[str, str, dict] | None:
    """(event_type, materiality, details) dal titolo del filing, o None."""
    for prefix, event_type, materiality, details in FORM_EVENT_RULES:
        if title.startswith(prefix):
            return event_type, materiality, dict(details)
    return None


def ingest_filings(db: Session, security: Security, listing: SecurityListing) -> dict:
    """Scarica e registra i filing di una security. Ritorna i conteggi."""
    if not security.cik:
        return {"documents": 0, "events": 0, "skipped": "cik mancante"}
    adapter = SECEdgarAdapter()
    try:
        filings = adapter.fetch_documents(listing.ticker, security.cik)
    except NotConfiguredError:
        raise
    except Exception as exc:  # noqa: BLE001 - errore di rete: nessun segnale inventato
        logger.warning("EDGAR errore per %s: %s", listing.ticker, exc)
        return {"documents": 0, "events": 0, "error": str(exc)[:200]}

    src = _sec_source(db)
    new_docs, new_events = 0, 0
    for meta in filings:
        canonical = normalize_url(meta.url)
        exists = db.scalar(
            select(Document).where(Document.url_canonical == canonical,
                                   Document.security_id == security.id)
        )
        if exists is not None:
            continue
        doc = Document(
            security_id=security.id, source_id=src.id,
            url_canonical=canonical, url_original=meta.url,
            title=meta.title, publisher=meta.publisher,
            published_at=meta.published_at,
            first_seen_at=utcnow(), retrieved_at=utcnow(),
            original_timezone=meta.original_timezone,
            source_level=meta.source_level, excerpt=meta.excerpt,
            license_state="full_allowed",
        )
        db.add(doc)
        db.flush()
        assign_duplicate_family(db, doc)
        new_docs += 1

        rule = classify_filing(meta.title)
        if rule is not None:
            event_type, materiality, details = rule
            db.add(Event(
                security_id=security.id, event_type=event_type,
                title=meta.title, status="occurred", is_binary=False,
                materiality=materiality,
                announced_at=meta.published_at, effective_at=meta.published_at,
                source_document_id=doc.id, classified_by="rule",
                details=details or None,
            ))
            new_events += 1
    db.flush()
    return {"documents": new_docs, "events": new_events}

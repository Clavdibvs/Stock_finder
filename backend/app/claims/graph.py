"""Claim graph: assegnazione famiglie duplicati e statistiche narrative.

Invarianti:
- un rumor resta rumor finché una fonte di livello 1-2 non lo conferma;
- i duplicati NON contano come conferme indipendenti;
- il conteggio rilevante è il numero di ORIGINI INDIPENDENTI (famiglie),
  non il numero di pagine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.claims.dedup import content_hash, is_near_duplicate, normalize_url, simhash
from app.constants import PRIMARY_SOURCE_LEVELS
from app.models import Claim, ClaimRelation, Document


def assign_duplicate_family(db: Session, doc: Document) -> Document:
    """Assegna il documento a una famiglia di duplicati.

    Confronta con i documenti della stessa security: URL canonico identico,
    hash esatto o quasi-duplicato (SimHash + Jaccard). Il documento radice
    (primo visto) fa da id di famiglia.
    """
    doc.url_canonical = normalize_url(doc.url_canonical)
    text = f"{doc.title} {doc.excerpt or ''}"
    if doc.content_hash is None:
        doc.content_hash = content_hash(text)
    if doc.simhash is None:
        doc.simhash = simhash(text)

    candidates = db.scalars(
        select(Document)
        .where(Document.security_id == doc.security_id,
               Document.id != doc.id)
        .order_by(Document.first_seen_at)
    ).all()

    for other in candidates:
        other_text = f"{other.title} {other.excerpt or ''}"
        same_url = other.url_canonical == doc.url_canonical
        same_hash = other.content_hash is not None and other.content_hash == doc.content_hash
        near = is_near_duplicate(text, other_text, doc.simhash, other.simhash)
        if same_url or same_hash or near:
            root_id = other.duplicate_family_id or other.id
            doc.duplicate_family_id = root_id
            doc.is_duplicate = True
            return doc

    doc.duplicate_family_id = doc.id
    doc.is_duplicate = False
    return doc


@dataclass
class NarrativeStats:
    """Statistiche del claim graph per una security (input del componente C)."""
    total_documents: int = 0
    duplicate_documents: int = 0
    independent_origins: int = 0     # famiglie distinte, non pagine
    primary_sources: int = 0         # documenti origine di livello 1-2
    rumor_claims: int = 0
    fact_claims: int = 0
    opinion_claims: int = 0
    contradictions: int = 0
    confirmations: int = 0
    promo_documents: int = 0
    post_move_documents: int = 0     # pubblicati dopo il movimento: non predittivi
    best_confirmation_level: int | None = None
    central_claim_status: str | None = None
    claims: list[Claim] = field(default_factory=list)

    @property
    def duplicate_share(self) -> float | None:
        if self.total_documents == 0:
            return None
        return self.duplicate_documents / self.total_documents


def compute_narrative_stats(db: Session, security_id: int,
                            move_start: datetime | None = None,
                            asof_ts: datetime | None = None) -> NarrativeStats:
    """Statistiche point-in-time: con `asof_ts` considera SOLO documenti già
    visti (first_seen_at <= asof_ts) e claim già estratti. Nessun look-ahead:
    una smentita futura non può entrare in uno score passato."""
    stats = NarrativeStats()
    doc_q = select(Document).where(Document.security_id == security_id)
    if asof_ts is not None:
        doc_q = doc_q.where(Document.first_seen_at <= asof_ts)
    docs = db.scalars(doc_q).all()
    stats.total_documents = len(docs)
    stats.duplicate_documents = sum(1 for d in docs if d.is_duplicate)

    families: set[int] = set()
    for d in docs:
        fam = d.duplicate_family_id or d.id
        families.add(fam)
        if not d.is_duplicate:
            if d.source_level in PRIMARY_SOURCE_LEVELS:
                stats.primary_sources += 1
            if d.source_level == 9:
                stats.promo_documents += 1
        if move_start is not None and d.published_at is not None and d.published_at > move_start:
            stats.post_move_documents += 1
    stats.independent_origins = len(families)

    claim_q = select(Claim).where(Claim.security_id == security_id)
    if asof_ts is not None:
        # un claim esiste solo se il suo documento sorgente era già stato visto
        visible_doc_ids = {d.id for d in docs}
        claims = [c for c in db.scalars(claim_q)
                  if c.source_document_id is None or c.source_document_id in visible_doc_ids]
    else:
        claims = list(db.scalars(claim_q))
    stats.claims = list(claims)
    for c in claims:
        if c.status == "rumor":
            stats.rumor_claims += 1
        elif c.status == "fatto":
            stats.fact_claims += 1
        elif c.status in ("opinione", "interpretazione", "previsione"):
            stats.opinion_claims += 1
        if c.confirmation_level is not None:
            if stats.best_confirmation_level is None or c.confirmation_level < stats.best_confirmation_level:
                stats.best_confirmation_level = c.confirmation_level

    if claims:
        # claim centrale = quello della narrativa DOMINANTE: la famiglia di
        # duplicati con più copie (ciò che il mercato sta effettivamente
        # leggendo), tie-break sul claim più recente. Un fatto di contesto
        # con una sola copia non scavalca il rumor ripetuto da cento pagine.
        family_of_doc = {d.id: (d.duplicate_family_id or d.id) for d in docs}
        family_size: dict[int, int] = {}
        for d in docs:
            fam = d.duplicate_family_id or d.id
            family_size[fam] = family_size.get(fam, 0) + 1

        def dominance(c: Claim) -> tuple[int, int]:
            fam = family_of_doc.get(c.source_document_id or -1)
            return (family_size.get(fam, 0), c.id)

        central = max(claims, key=dominance)
        stats.central_claim_status = central.status

    claim_ids = [c.id for c in claims]
    if claim_ids:
        relations = db.scalars(
            select(ClaimRelation).where(ClaimRelation.claim_id.in_(claim_ids))
        ).all()
        stats.contradictions = sum(1 for r in relations if r.relation == "contraddice")
        stats.confirmations = sum(1 for r in relations if r.relation == "conferma")

    return stats


def confirm_claim(db: Session, claim: Claim, confirming_doc: Document) -> Claim:
    """Promuove un claim a `fatto` SOLO se il documento è di livello 1-2
    e non è un duplicato. I duplicati non modificano mai lo stato."""
    if confirming_doc.is_duplicate:
        return claim
    if confirming_doc.source_level in PRIMARY_SOURCE_LEVELS:
        claim.status = "fatto"
        claim.confirmation_level = confirming_doc.source_level
    else:
        if claim.confirmation_level is None or confirming_doc.source_level < claim.confirmation_level:
            claim.confirmation_level = confirming_doc.source_level
    return claim

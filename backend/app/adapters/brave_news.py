"""Brave News discovery (reale, key-gated): metadati e link, MAI contenuti
integrali. I diritti sui contenuti terzi non vengono trasferiti (SOURCE_REGISTRY).

Uso: SOLO per i candidati del giorno (bounded, entro il credito gratuito).
Ogni risultato diventa un Document (titolo, URL, estratto breve, timestamp)
che alimenta attenzione (A), origini indipendenti e dedup (C). Un rumor visto
qui resta un claim non confermato finché una fonte 1-2 non lo conferma.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import urlencode, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterStatus, NotConfiguredError
from app.claims.dedup import normalize_url
from app.claims.graph import assign_duplicate_family
from app.config import get_settings
from app.core.http import safe_fetch
from app.models import Document, DocumentSource, Security, utcnow

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.search.brave.com/res/v1/news/search"

# livello fonte per dominio (gerarchia D.1); sconosciuto -> 8 (opinione)
_DOMAIN_LEVELS = {
    "reuters.com": 3, "bloomberg.com": 3, "wsj.com": 3, "ft.com": 3,
    "cnbc.com": 4, "marketwatch.com": 4, "barrons.com": 4, "finance.yahoo.com": 4,
    "prnewswire.com": 2, "businesswire.com": 2, "globenewswire.com": 2,
    "accesswire.com": 2, "sec.gov": 1,
    "seekingalpha.com": 5, "fool.com": 5, "investorplace.com": 8,
    "benzinga.com": 4, "stocktwits.com": 7, "reddit.com": 7,
}


def brave_status() -> AdapterStatus:
    s = get_settings()
    if s.news_discovery_provider == "brave" and s.news_discovery_api_key:
        return AdapterStatus.OK
    return AdapterStatus.NOT_CONFIGURED


def _source(db: Session) -> DocumentSource:
    src = db.scalar(select(DocumentSource).where(DocumentSource.name == "Brave News discovery"))
    if src is None:
        src = DocumentSource(
            name="Brave News discovery", domain="search.brave.com",
            publisher="Brave Search API", default_source_level=8,
            license_status="metadata_only", configured=True, enabled=True,
            notes="Solo discovery: metadati, link ed estratti brevi; nessuna copia integrale",
        )
        db.add(src)
        db.flush()
    return src


def _level_for(url: str) -> int:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for domain, level in _DOMAIN_LEVELS.items():
        if host == domain or host.endswith("." + domain):
            return level
    return 8


def search_news(ticker: str, company_name: str | None = None,
                count: int = 15) -> list[dict]:
    """Risultati news recenti per un ticker (ultimo giorno)."""
    s = get_settings()
    if brave_status() is not AdapterStatus.OK:
        raise NotConfiguredError(
            "Brave discovery non configurata: DDR_NEWS_DISCOVERY_PROVIDER=brave "
            "e DDR_NEWS_DISCOVERY_API_KEY (https://brave.com/search/api/)."
        )
    query = f'"{ticker}" stock'
    if company_name and len(company_name) > 3:
        query = f'"{ticker}" OR "{company_name}"'
    params = {"q": query, "count": min(count, 20), "freshness": "pd",
              "search_lang": "en"}
    resp = safe_fetch(f"{SEARCH_URL}?{urlencode(params)}",
                      headers={"X-Subscription-Token": s.news_discovery_api_key,
                               "Accept": "application/json"})
    return resp.json().get("results", [])


def ingest_news_for_security(db: Session, security: Security,
                             ticker: str) -> dict:
    """Discovery news per un candidato: salva metadati, dedup, mai full text."""
    try:
        results = search_news(ticker, security.name)
    except NotConfiguredError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Brave discovery errore per %s: %s", ticker, exc)
        return {"documents": 0, "error": str(exc)[:200]}

    src = _source(db)
    created = 0
    for r in results:
        url = r.get("url") or ""
        title = (r.get("title") or "").strip()
        if not url or not title:
            continue
        canonical = normalize_url(url)
        exists = db.scalar(
            select(Document).where(Document.url_canonical == canonical,
                                   Document.security_id == security.id)
        )
        if exists is not None:
            continue
        published = None
        page_age = r.get("page_age") or r.get("age")
        if page_age and re_iso(page_age):
            try:
                published = datetime.fromisoformat(
                    page_age.replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                published = None
        doc = Document(
            security_id=security.id, source_id=src.id,
            url_canonical=canonical, url_original=url,
            title=title[:512],
            publisher=(r.get("meta_url") or {}).get("hostname") or None,
            published_at=published, first_seen_at=utcnow(), retrieved_at=utcnow(),
            source_level=_level_for(url),
            excerpt=(r.get("description") or "")[:500] or None,
            license_state="metadata_only",
        )
        db.add(doc)
        db.flush()
        assign_duplicate_family(db, doc)
        created += 1
    db.flush()
    return {"documents": created, "results": len(results)}


def re_iso(value: str) -> bool:
    return len(value) >= 10 and value[4] == "-" and value[7] == "-"

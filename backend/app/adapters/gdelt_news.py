"""News discovery via GDELT DOC 2.0 (gratuito, aperto, NESSUNA chiave).

GDELT è un progetto open pensato per l'uso programmatico (già indicato dalla
ricerca D.6 come fonte di discovery). Regole rispettate:
- max 1 richiesta ogni 5 secondi (throttle interno 5,5 s);
- solo metadati e titoli: mai contenuti integrali;
- rumore elevato per design -> la dedup (famiglie di duplicati) è obbligatoria
  e già attiva a valle.

Alternative verificate e scartate: Google News RSS (vietato dal loro
robots.txt), feed RSS Yahoo Finance (dismesso, 404), Brave (richiede piano a
pagamento: resta supportato come provider opzionale).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterStatus
from app.adapters.brave_news import _level_for  # gerarchia dominio -> livello
from app.claims.dedup import normalize_url
from app.claims.graph import assign_duplicate_family
from app.core.http import safe_fetch
from app.models import Document, DocumentSource, Security, utcnow

logger = logging.getLogger(__name__)

DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

_MIN_INTERVAL_S = 6.5   # fair use GDELT (dichiarato 1/5s; margine prudente)
_RETRY_WAIT_S = 20.0    # attesa dopo un 429 prima dell'unico retry
_last_call = 0.0
_consecutive_failures = 0
_CIRCUIT_LIMIT = 3      # dopo 3 fallimenti consecutivi si ferma per il run


def _throttle() -> None:
    global _last_call
    elapsed = time.monotonic() - _last_call
    if elapsed < _MIN_INTERVAL_S:
        time.sleep(_MIN_INTERVAL_S - elapsed)
    _last_call = time.monotonic()


def reset_circuit() -> None:
    """Chiamata all'inizio di ogni run di enrichment."""
    global _consecutive_failures
    _consecutive_failures = 0


def circuit_open() -> bool:
    return _consecutive_failures >= _CIRCUIT_LIMIT


def gdelt_status() -> AdapterStatus:
    return AdapterStatus.OK  # nessuna chiave richiesta


def _source(db: Session) -> DocumentSource:
    src = db.scalar(select(DocumentSource).where(DocumentSource.name == "GDELT discovery"))
    if src is None:
        src = DocumentSource(
            name="GDELT discovery", domain="gdeltproject.org",
            publisher="The GDELT Project", default_source_level=8,
            license_status="metadata_only", configured=True, enabled=True,
            notes="Discovery aperta: solo metadati/titoli; rumore alto, dedup obbligatoria; "
                  "fair use 1 req/5s",
        )
        db.add(src)
        db.flush()
    return src


_NAME_NOISE = re.compile(
    r"\b(common stock|class [a-c]|ordinary shares?|inc\.?|corp\.?|corporation|"
    r"ltd\.?|plc|llc|holdings?|group|company|co\.?|the)\b\.?,?",
    re.IGNORECASE,
)


def clean_company_name(name: str) -> str:
    """Rimuove suffissi legali/di listino dal nome (es. 'Inc. Common Stock')."""
    cleaned = _NAME_NOISE.sub("", name)
    cleaned = re.sub(r"[,.]+\s*$", "", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _build_query(ticker: str, company_name: str | None) -> str:
    """Query GDELT: nome società ripulito (se significativo) + ticker+stock."""
    clean_ticker = ticker.split("/")[0]
    name = clean_company_name(company_name or "")
    # nomi troppo generici o uguali al ticker non aiutano
    if len(name) > 4 and name.upper() != clean_ticker:
        # GDELT: le frasi vanno tra virgolette; OR fra alternative
        return f'("{name}" OR "{clean_ticker} stock") sourcelang:english'
    return f'"{clean_ticker} stock" sourcelang:english'


def search_news(ticker: str, company_name: str | None = None,
                max_records: int = 20) -> list[dict]:
    """Articoli recenti (48h) da GDELT, con retry singolo su 429 e circuito.

    Ritorna [] su qualsiasi limite: mai un crash, mai dati inventati.
    """
    global _consecutive_failures
    if circuit_open():
        return []
    params = {
        "query": _build_query(ticker, company_name),
        "mode": "artlist",
        "maxrecords": min(max_records, 30),
        "timespan": "2d",
        "sort": "datedesc",
        "format": "json",
    }
    url = f"{DOC_URL}?{urlencode(params)}"
    for attempt in (1, 2):
        _throttle()
        try:
            resp = safe_fetch(url)
        except Exception as exc:  # noqa: BLE001 - include 429 via raise_for_status
            if "429" in str(exc) and attempt == 1:
                logger.info("GDELT 429 per %s: attendo %.0fs e riprovo", ticker, _RETRY_WAIT_S)
                time.sleep(_RETRY_WAIT_S)
                continue
            _consecutive_failures += 1
            if circuit_open():
                logger.warning("GDELT: %d fallimenti consecutivi, discovery sospesa per il run",
                               _consecutive_failures)
            raise
        try:
            payload = resp.json()
        except ValueError:
            # GDELT risponde con testo semplice quando il rate limit è superato
            logger.warning("GDELT risposta non-JSON (rate limit?): %s", resp.text[:120])
            _consecutive_failures += 1
            return []
        _consecutive_failures = 0
        return payload.get("articles", []) or []
    return []


def _parse_seendate(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def ingest_news_for_security(db: Session, security: Security, ticker: str) -> dict:
    """Discovery GDELT per un candidato: metadati, dedup, mai full text."""
    try:
        articles = search_news(ticker, security.name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("GDELT discovery errore per %s: %s", ticker, exc)
        return {"documents": 0, "error": str(exc)[:200]}

    src = _source(db)
    created = 0
    for a in articles:
        url = a.get("url") or ""
        title = (a.get("title") or "").strip()
        if not url or not title or not url.startswith("https://"):
            continue
        canonical = normalize_url(url)
        exists = db.scalar(
            select(Document).where(Document.url_canonical == canonical,
                                   Document.security_id == security.id)
        )
        if exists is not None:
            continue
        doc = Document(
            security_id=security.id, source_id=src.id,
            url_canonical=canonical, url_original=url,
            title=title[:512],
            publisher=a.get("domain") or None,
            published_at=_parse_seendate(a.get("seendate")),
            first_seen_at=utcnow(), retrieved_at=utcnow(),
            source_level=_level_for(url),
            excerpt=None,  # GDELT artlist non fornisce estratti: solo metadati
            license_state="metadata_only",
        )
        db.add(doc)
        db.flush()
        assign_duplicate_family(db, doc)
        created += 1
    db.flush()
    return {"documents": created, "results": len(articles)}

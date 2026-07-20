"""Adapter reale per SEC EDGAR (fonte gratuita e ufficiale, livello 1).

Rispetta la fair-access policy SEC:
- User-Agent identificabile obbligatorio (DDR_SEC_USER_AGENT, es.
  "Nome Cognome email@example.com");
- max ~10 richieste/secondo: qui si applica un rate limit conservativo;
- solo domini sec.gov (allowlist + validazione SSRF in core.http).

Se DDR_SEC_EDGAR_ENABLED è false o manca lo user agent, l'adapter risponde
NOT_CONFIGURED: nessun dato fittizio, nessuna chiamata di rete.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime

from app.adapters.base import AdapterStatus, DocumentSourceAdapter, NewsMetadata, NotConfiguredError
from app.config import get_settings
from app.core.http import safe_fetch

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"

# Form rilevanti per la tassonomia (diluizione, eventi materiali, insider)
RELEVANT_FORMS = {
    "8-K": ("evento materiale", 1),
    "10-Q": ("bilancio trimestrale", 1),
    "10-K": ("bilancio annuale", 1),
    "S-1": ("registrazione titoli", 1),
    "S-3": ("shelf registration", 1),
    "424B5": ("prospectus supplement (offering)", 1),
    "424B3": ("prospectus supplement", 1),
    "4": ("insider ownership (Form 4)", 1),
    "144": ("vendita proposta (Form 144)", 1),
}

_MIN_INTERVAL_S = 0.2  # max 5 req/s, sotto il limite fair-access
_last_call = 0.0


def _throttle() -> None:
    global _last_call
    elapsed = time.monotonic() - _last_call
    if elapsed < _MIN_INTERVAL_S:
        time.sleep(_MIN_INTERVAL_S - elapsed)
    _last_call = time.monotonic()


class SECEdgarAdapter(DocumentSourceAdapter):
    name = "sec_edgar"

    def status(self) -> AdapterStatus:
        settings = get_settings()
        if not settings.sec_edgar_enabled or not settings.sec_user_agent:
            return AdapterStatus.NOT_CONFIGURED
        return AdapterStatus.OK

    def fetch_documents(self, ticker: str, cik: str | None = None) -> list[NewsMetadata]:
        settings = get_settings()
        if self.status() is not AdapterStatus.OK:
            raise NotConfiguredError(
                "SEC EDGAR non configurata: impostare DDR_SEC_EDGAR_ENABLED=true e "
                "DDR_SEC_USER_AGENT ('Nome Cognome email@example.com')."
            )
        if not cik:
            return []

        _throttle()
        resp = safe_fetch(
            SUBMISSIONS_URL.format(cik=cik),
            headers={"User-Agent": settings.sec_user_agent,
                     "Accept-Encoding": "gzip, deflate"},
        )
        data = resp.json()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])

        out: list[NewsMetadata] = []
        for i, form in enumerate(forms):
            if form not in RELEVANT_FORMS:
                continue
            desc, level = RELEVANT_FORMS[form]
            accession = accessions[i].replace("-", "")
            doc = primary_docs[i] if i < len(primary_docs) else ""
            url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{doc}"
                   if doc else f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}")
            published = None
            if i < len(dates) and dates[i]:
                published = datetime.strptime(dates[i], "%Y-%m-%d").replace(tzinfo=UTC)
            title = f"{form} — {descriptions[i] if i < len(descriptions) and descriptions[i] else desc}"
            out.append(NewsMetadata(
                url=url, title=title, published_at=published,
                publisher="SEC EDGAR", source_level=level,
                original_timezone="America/New_York",
                excerpt=f"Filing {form} depositato il {dates[i] if i < len(dates) else 'n/d'}.",
            ))
        return out

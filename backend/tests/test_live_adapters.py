"""Adapter live: Alpaca, universo SEC, ingestione EDGAR, halt Nasdaq.

Tutte le chiamate di rete sono simulate (monkeypatch di safe_fetch):
i test non toccano mai internet.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from app.models import Document, Event, Security, SecurityListing


class FakeResponse:
    def __init__(self, payload, text: str | None = None):
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        return self._payload


# ------------------------------------------------------------------ Alpaca ---

ALPACA_PAGE_1 = {
    "bars": {
        "AAPL": [
            {"t": "2026-07-15T04:00:00Z", "o": 210.0, "h": 214.0, "l": 209.0,
             "c": 213.5, "v": 1_000_000, "vw": 212.1},
        ],
    },
    "next_page_token": "tok123",
}
ALPACA_PAGE_2 = {
    "bars": {
        "AAPL": [
            {"t": "2026-07-16T04:00:00Z", "o": 213.5, "h": 216.0, "l": 212.0,
             "c": 215.0, "v": 900_000, "vw": 214.2},
        ],
        "MSFT": [
            {"t": "2026-07-16T04:00:00Z", "o": 500.0, "h": 505.0, "l": 498.0,
             "c": 503.0, "v": 700_000, "vw": 501.5},
        ],
    },
    "next_page_token": None,
}


class TestAlpacaAdapter:
    def test_not_configured_without_keys(self, monkeypatch):
        from app.adapters.alpaca import AlpacaMarketDataAdapter
        from app.adapters.base import AdapterStatus, NotConfiguredError
        from app.config import get_settings
        monkeypatch.delenv("DDR_ALPACA_KEY_ID", raising=False)
        monkeypatch.delenv("DDR_ALPACA_SECRET_KEY", raising=False)
        get_settings.cache_clear()
        try:
            adapter = AlpacaMarketDataAdapter()
            assert adapter.status() is AdapterStatus.NOT_CONFIGURED
            with pytest.raises(NotConfiguredError):
                adapter.get_daily_bars("AAPL", date(2026, 7, 1), date(2026, 7, 16))
        finally:
            get_settings.cache_clear()

    def test_bulk_bars_with_pagination(self, monkeypatch):
        import app.adapters.alpaca as mod
        from app.config import get_settings
        monkeypatch.setenv("DDR_ALPACA_KEY_ID", "k")
        monkeypatch.setenv("DDR_ALPACA_SECRET_KEY", "s")
        get_settings.cache_clear()
        calls = []

        def fake_fetch(url, headers=None):
            calls.append(url)
            assert headers["APCA-API-KEY-ID"] == "k"
            return FakeResponse(ALPACA_PAGE_2 if "page_token" in url else ALPACA_PAGE_1)

        monkeypatch.setattr(mod, "safe_fetch", fake_fetch)
        try:
            adapter = mod.AlpacaMarketDataAdapter()
            out = adapter.get_daily_bars_bulk(["AAPL", "MSFT"],
                                              date(2026, 7, 14), date(2026, 7, 16))
            assert len(calls) == 2  # paginazione seguita
            assert [b.bar_date for b in out["AAPL"]] == [date(2026, 7, 15), date(2026, 7, 16)]
            assert out["AAPL"][0].close == 213.5
            assert out["AAPL"][0].vwap == 212.1
            assert out["MSFT"][0].volume == 700_000
            assert all(b.session == "regular" for b in out["AAPL"])
        finally:
            get_settings.cache_clear()


# ------------------------------------------------------------- universo SEC ---

SEC_TICKERS = {
    "fields": ["cik", "name", "ticker", "exchange"],
    "data": [
        [320193, "Apple Inc.", "AAPL", "Nasdaq"],
        [1840904, "AtaiBeckley Inc.", "ATAI", "Nasdaq"],
    ],
}
SEC_SHARES = {
    "units": {"shares": [
        {"end": "2026-03-31", "val": 180_000_000},
        {"end": "2026-06-30", "val": 182_000_000},
    ]},
}


class TestUniverseSync:
    def _configure_sec(self, monkeypatch):
        from app.config import get_settings
        monkeypatch.setenv("DDR_SEC_EDGAR_ENABLED", "true")
        monkeypatch.setenv("DDR_SEC_USER_AGENT", "Test User test@example.com")
        get_settings.cache_clear()

    def test_sync_creates_security_with_cik(self, db, monkeypatch):
        import app.adapters.sec_universe as mod
        from app.config import get_settings
        self._configure_sec(monkeypatch)

        def fake_fetch(url, headers=None):
            if "company_tickers" in url:
                return FakeResponse(SEC_TICKERS)
            return FakeResponse(SEC_SHARES)

        monkeypatch.setattr(mod, "safe_fetch", fake_fetch)
        try:
            result = mod.sync_universe(db, ["atai", "ATAI", "ZZZZFAKE"])
            assert "ATAI" in result["created"]
            assert "ZZZZFAKE" in result["created"]        # creato comunque
            assert "ZZZZFAKE" in result["unknown_to_sec"]  # ma segnalato
            from sqlalchemy import select
            listing = db.scalar(select(SecurityListing).where(SecurityListing.ticker == "ATAI"))
            sec = db.get(Security, listing.security_id)
            assert sec.cik == "0001840904"                 # CIK zero-padded
            assert sec.name == "AtaiBeckley Inc."
            assert listing.shares_outstanding == 182_000_000  # ultimo valore XBRL
            # idempotente
            result2 = mod.sync_universe(db, ["ATAI"])
            assert result2["created"] == []
            # benchmark creato come index
            bench = db.scalar(select(Security).where(Security.security_type == "index"))
            assert bench is not None
        finally:
            get_settings.cache_clear()

    def test_sync_without_sec_still_creates(self, db, monkeypatch):
        from app.config import get_settings
        monkeypatch.setenv("DDR_SEC_EDGAR_ENABLED", "false")
        get_settings.cache_clear()
        try:
            from app.adapters.sec_universe import sync_universe
            result = sync_universe(db, ["NOSEC"])
            assert result["sec_configured"] is False
            assert "NOSEC" in result["created"]  # senza CIK, mai dati inventati
        finally:
            get_settings.cache_clear()


# ------------------------------------------------------------ EDGAR ingest ---

class TestEdgarIngest:
    def test_form_classification(self):
        from app.adapters.edgar_ingest import classify_filing
        assert classify_filing("424B5 — Prospectus supplement")[0] == "offering_or_dilution"
        assert classify_filing("S-3 — shelf registration")[0] == "offering_or_dilution"
        assert classify_filing("8-K — evento materiale")[0] == "other_material"
        assert classify_filing("4 — insider ownership")[0] == "insider_activity"
        assert classify_filing("10-Q — bilancio trimestrale") is None  # solo documento

    def test_ingest_creates_documents_and_events_idempotently(self, db, monkeypatch):
        from app.adapters.base import NewsMetadata
        import app.adapters.edgar_ingest as mod

        sec = Security(name="Test Corp", cik="0000320193", is_demo=False)
        db.add(sec)
        db.flush()
        listing = SecurityListing(security_id=sec.id, ticker="TST", exchange="NASDAQ",
                                  status="active", valid_from=date(2026, 1, 1))
        db.add(listing)
        db.flush()

        filings = [
            NewsMetadata(url="https://www.sec.gov/Archives/edgar/data/320193/acc1/doc1.htm",
                         title="424B5 — Prospectus supplement (offering)",
                         published_at=datetime(2026, 7, 15, 21, 0, tzinfo=UTC),
                         publisher="SEC EDGAR", source_level=1,
                         excerpt="Filing 424B5 depositato il 2026-07-15."),
            NewsMetadata(url="https://www.sec.gov/Archives/edgar/data/320193/acc2/doc2.htm",
                         title="4 — insider ownership (Form 4)",
                         published_at=datetime(2026, 7, 14, 18, 0, tzinfo=UTC),
                         publisher="SEC EDGAR", source_level=1,
                         excerpt="Filing 4 depositato il 2026-07-14."),
        ]

        monkeypatch.setattr(mod.SECEdgarAdapter, "fetch_documents",
                            lambda self, t, c: filings)
        r1 = mod.ingest_filings(db, sec, listing)
        assert r1 == {"documents": 2, "events": 2}
        r2 = mod.ingest_filings(db, sec, listing)  # idempotente
        assert r2 == {"documents": 0, "events": 0}

        from sqlalchemy import select
        events = db.scalars(select(Event).where(Event.security_id == sec.id)).all()
        types = {e.event_type for e in events}
        assert types == {"offering_or_dilution", "insider_activity"}
        dilution = next(e for e in events if e.event_type == "offering_or_dilution")
        assert dilution.details["shelf_open"] is True
        assert dilution.classified_by == "rule"
        docs = db.scalars(select(Document).where(Document.security_id == sec.id)).all()
        assert all(d.source_level == 1 for d in docs)


# ------------------------------------------------------------- halt Nasdaq ---

HALTS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:ndaq="http://www.nasdaqtrader.com/">
  <channel>
    <item>
      <title>QNTC halted</title>
      <ndaq:IssueSymbol>QNTC</ndaq:IssueSymbol>
      <ndaq:ReasonCode>LUDP</ndaq:ReasonCode>
      <ndaq:HaltDate>07/16/2026</ndaq:HaltDate>
      <ndaq:HaltTime>09:45:12</ndaq:HaltTime>
    </item>
    <item>
      <title>ALTRO halted</title>
      <ndaq:IssueSymbol>NOTINUNIVERSE</ndaq:IssueSymbol>
      <ndaq:ReasonCode>T1</ndaq:ReasonCode>
      <ndaq:HaltDate>07/16/2026</ndaq:HaltDate>
      <ndaq:HaltTime>10:00:00</ndaq:HaltTime>
    </item>
  </channel>
</rss>"""


class TestNasdaqHalts:
    def test_parse_and_ingest(self, db, monkeypatch):
        import app.adapters.nasdaq_halts as mod
        sec = Security(name="Quantum Corp", is_demo=False)
        db.add(sec)
        db.flush()
        db.add(SecurityListing(security_id=sec.id, ticker="QNTC", exchange="NASDAQ",
                               status="active", valid_from=date(2026, 1, 1)))
        db.flush()

        monkeypatch.setattr(mod, "safe_fetch",
                            lambda url, headers=None: FakeResponse({}, text=HALTS_XML))
        r1 = mod.ingest_halts(db)
        assert r1["halts_in_feed"] == 2
        assert r1["created"] == 1  # solo il titolo in universo
        r2 = mod.ingest_halts(db)
        assert r2["created"] == 0  # idempotente

        from sqlalchemy import select
        ev = db.scalar(select(Event).where(Event.event_type == "halt"))
        assert ev.security_id == sec.id
        assert ev.details["reason_code"] == "LUDP"
        assert ev.announced_at.date() == date(2026, 7, 16)

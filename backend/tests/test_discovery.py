"""Auto-discovery full-market, screening crypto, Brave news (rete simulata)."""
from __future__ import annotations

import json
from datetime import date


from app.models import Security, SecurityListing


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


ASSETS = [
    {"symbol": "GOOD", "name": "Good Operating Co", "exchange": "NASDAQ",
     "status": "active", "tradable": True},
    {"symbol": "NYSEOK", "name": "NY Industrial Corp", "exchange": "NYSE",
     "status": "active", "tradable": True},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "exchange": "ARCA",
     "status": "active", "tradable": True},              # exchange escluso
    {"symbol": "QQQX", "name": "Nuveen Nasdaq Fund", "exchange": "NASDAQ",
     "status": "active", "tradable": True},              # name "Fund"
    {"symbol": "ABCD.WS", "name": "ABCD Warrant", "exchange": "NYSE",
     "status": "active", "tradable": True},              # warrant
    {"symbol": "BAC-PB", "name": "Bank Preferred Series B", "exchange": "NYSE",
     "status": "active", "tradable": True},              # preferred
    {"symbol": "HALT", "name": "Suspended Inc", "exchange": "NASDAQ",
     "status": "active", "tradable": False},             # non tradable
    {"symbol": "LEV3", "name": "Direxion 3x Bull Shares", "exchange": "NYSE",
     "status": "active", "tradable": True},              # leveraged
]

CRYPTO_ASSETS = [
    {"symbol": "BTC/USD", "name": "Bitcoin", "status": "active", "tradable": True},
    {"symbol": "DOGE/USD", "name": "Dogecoin", "status": "active", "tradable": True},
    {"symbol": "BTC/EUR", "name": "Bitcoin EUR", "status": "active", "tradable": True},  # non USD
]


class TestEquityDiscovery:
    def test_filters_non_common_stock(self):
        from app.adapters.discovery import filter_equity_assets
        filtered = filter_equity_assets(ASSETS)
        symbols = {a["symbol"] for a in filtered}
        assert symbols == {"GOOD", "NYSEOK"}  # ETF/warrant/preferred/fund/3x esclusi

    def test_discover_creates_securities(self, db, monkeypatch):
        import app.adapters.discovery as mod
        monkeypatch.setattr(mod.AlpacaMarketDataAdapter, "list_assets",
                            lambda self, ac="us_equity": ASSETS)
        r1 = mod.discover_equities(db)
        assert r1["created"] == 2
        assert r1["in_perimeter"] == 2
        r2 = mod.discover_equities(db)  # idempotente
        assert r2["created"] == 0
        from sqlalchemy import select
        sec = db.scalar(select(Security).join(
            SecurityListing, SecurityListing.security_id == Security.id
        ).where(SecurityListing.ticker == "GOOD"))
        assert sec is not None and sec.security_type == "common_stock"
        assert sec.cik is None  # anagrafica SEC lazy: solo per i candidati


class TestCryptoDiscovery:
    def test_disabled_by_default(self, db, monkeypatch):
        from app.config import get_settings
        monkeypatch.delenv("DDR_CRYPTO_ENABLED", raising=False)
        get_settings.cache_clear()
        try:
            from app.adapters.discovery import discover_crypto
            assert discover_crypto(db)["created"] == 0
        finally:
            get_settings.cache_clear()

    def test_discover_usd_pairs_only(self, db, monkeypatch):
        import app.adapters.discovery as mod
        from app.config import get_settings
        monkeypatch.setenv("DDR_CRYPTO_ENABLED", "true")
        get_settings.cache_clear()
        try:
            monkeypatch.setattr(mod.AlpacaMarketDataAdapter, "list_assets",
                                lambda self, ac="us_equity": CRYPTO_ASSETS)
            r = mod.discover_crypto(db)
            assert r["created"] == 2  # BTC/USD e DOGE/USD, non BTC/EUR
            from sqlalchemy import select
            btc = db.scalar(select(Security).join(
                SecurityListing, SecurityListing.security_id == Security.id
            ).where(SecurityListing.ticker == "BTC/USD"))
            assert btc.security_type == "crypto"
        finally:
            get_settings.cache_clear()


class TestCryptoScoring:
    def _crypto_with_rally(self, db, price_start=0.30):
        """Crypto sub-$1 con rally: NON deve finire in shadow_price."""
        from app.models import MarketBar
        from app.seed.demo import business_days_back
        sec = Security(name="Dogecoin", security_type="crypto", is_demo=False)
        db.add(sec)
        db.flush()
        db.add(SecurityListing(security_id=sec.id, ticker="DOGE/USD",
                               exchange="CRYPTO", status="active",
                               valid_from=date(2026, 1, 1)))
        days = business_days_back(date(2026, 7, 16), 80)
        price = price_start
        for i, d in enumerate(days):
            ret = 0.25 if i == len(days) - 1 else 0.001
            vol = 900_000_000 if i == len(days) - 1 else 80_000_000
            new_price = price * (1 + ret)
            db.add(MarketBar(security_id=sec.id, bar_date=d, session="regular",
                             open=price, high=new_price * 1.01, low=price * 0.99,
                             close=new_price, volume=vol, provider="test"))
            price = new_price
        db.flush()
        return sec

    def test_crypto_sub_dollar_not_shadow(self, db):
        from app.candidates.features import compute_features
        from app.candidates.generator import evaluate
        sec = self._crypto_with_rally(db)
        f = compute_features(db, sec.id, date(2026, 7, 16))
        assert f.asset_type == "crypto"
        decision = evaluate(f, date(2026, 7, 16))
        assert decision.universe_status == "in_universe"  # niente gate sub-$1
        assert decision.is_candidate is True

    def test_crypto_confidence_capped_and_never_elevated(self, db):
        """Senza market cap/filing la crypto resta al massimo C/MONITORARE."""
        from app.constants import STATE_ELEVATED
        from app.scoring.pipeline import run_for_security
        sec = self._crypto_with_rally(db)
        score = run_for_security(db, sec, date(2026, 7, 16))
        assert score is not None
        assert score.confidence_grade in ("C", "D")   # mai A/B senza cap
        assert score.state != STATE_ELEVATED          # richiede A/B
        assert score.execution_hazard is None         # non modellato: sconosciuto
        assert score.squeeze_unknown is True


class TestBraveNews:
    def test_not_configured(self):
        from app.adapters.base import AdapterStatus
        from app.adapters.brave_news import brave_status
        assert brave_status() is AdapterStatus.NOT_CONFIGURED

    def test_ingest_news_metadata(self, db, monkeypatch):
        import app.adapters.brave_news as mod
        from app.config import get_settings
        monkeypatch.setenv("DDR_NEWS_DISCOVERY_PROVIDER", "brave")
        monkeypatch.setenv("DDR_NEWS_DISCOVERY_API_KEY", "test-key")
        get_settings.cache_clear()
        try:
            sec = Security(name="Rally Corp", is_demo=False)
            db.add(sec)
            db.flush()
            payload = {"results": [
                {"title": "Rally Corp in talks to be acquired, sources say",
                 "url": "https://www.reuters.com/markets/rally-corp-talks?utm_source=x",
                 "description": "People familiar with the matter said talks are advanced.",
                 "page_age": "2026-07-17T08:00:00Z",
                 "meta_url": {"hostname": "www.reuters.com"}},
                {"title": "Rally Corp in talks to be acquired, sources say",
                 "url": "https://aggregator-copy.com/rewrite-1",
                 "description": "People familiar with the matter said talks are advanced.",
                 "page_age": "2026-07-17T08:30:00Z",
                 "meta_url": {"hostname": "aggregator-copy.com"}},
            ]}
            monkeypatch.setattr(mod, "safe_fetch",
                                lambda url, headers=None, max_bytes=None: FakeResponse(payload))
            r1 = mod.ingest_news_for_security(db, sec, "RLLY")
            assert r1["documents"] == 2
            r2 = mod.ingest_news_for_security(db, sec, "RLLY")  # idempotente
            assert r2["documents"] == 0
            from sqlalchemy import select
            from app.models import Document
            docs = db.scalars(select(Document).where(
                Document.security_id == sec.id)).all()
            reuters = next(d for d in docs if "reuters" in d.url_canonical)
            copy = next(d for d in docs if "aggregator" in d.url_canonical)
            assert reuters.source_level == 3          # gerarchia per dominio
            assert copy.is_duplicate is True          # riscrittura -> stessa famiglia
            assert copy.duplicate_family_id == reuters.id
            assert all(d.license_state == "metadata_only" for d in docs)
        finally:
            get_settings.cache_clear()


class TestGdeltNews:
    GDELT_PAYLOAD = {"articles": [
        {"url": "https://www.fool.com/2026/07/16/why-ataibeckley-stock-soared/",
         "title": "Why AtaiBeckley Stock Soared Today",
         "domain": "fool.com", "seendate": "20260716T231500Z"},
        {"url": "https://finance.yahoo.com/news/ataibeckley-acquired-lilly",
         "title": "AtaiBeckley to be acquired by Lilly in deal valued at up to $3.8 billion",
         "domain": "finance.yahoo.com", "seendate": "20260716T131500Z"},
        {"url": "http://insecure-site.com/x", "title": "No https", "domain": "x.com",
         "seendate": "20260716T120000Z"},  # scartato: non https
    ]}

    def test_status_ok_without_key(self, monkeypatch):
        from app.adapters.base import AdapterStatus
        from app.adapters.news_discovery import news_status
        from app.config import get_settings
        monkeypatch.setenv("DDR_NEWS_DISCOVERY_PROVIDER", "gdelt")
        get_settings.cache_clear()
        try:
            assert news_status() is AdapterStatus.OK  # nessuna chiave richiesta
        finally:
            get_settings.cache_clear()

    def test_ingest_gdelt_metadata(self, db, monkeypatch):
        import app.adapters.gdelt_news as mod
        from datetime import UTC, datetime

        class R:
            text = "{}"
            def json(self): return TestGdeltNews.GDELT_PAYLOAD

        monkeypatch.setattr(mod, "safe_fetch", lambda url, headers=None, max_bytes=None: R())
        monkeypatch.setattr(mod, "_throttle", lambda: None)
        sec = Security(name="AtaiBeckley Inc.", is_demo=False)
        db.add(sec)
        db.flush()
        r1 = mod.ingest_news_for_security(db, sec, "ATAI")
        assert r1["documents"] == 2  # il non-https viene scartato
        r2 = mod.ingest_news_for_security(db, sec, "ATAI")
        assert r2["documents"] == 0  # idempotente
        from sqlalchemy import select
        from app.models import Document
        docs = db.scalars(select(Document).where(Document.security_id == sec.id)).all()
        yahoo = next(d for d in docs if "yahoo" in d.url_canonical)
        assert yahoo.source_level == 4  # gerarchia per dominio
        assert yahoo.published_at == datetime(2026, 7, 16, 13, 15, tzinfo=UTC)
        assert all(d.license_state == "metadata_only" for d in docs)
        assert all(d.excerpt is None for d in docs)  # solo metadati

    def test_rate_limit_text_response_handled(self, monkeypatch):
        import app.adapters.gdelt_news as mod

        class R:
            text = "Please limit requests to one every 5 seconds"
            def json(self): raise ValueError("not json")

        monkeypatch.setattr(mod, "safe_fetch", lambda url, headers=None, max_bytes=None: R())
        monkeypatch.setattr(mod, "_throttle", lambda: None)
        mod.reset_circuit()
        assert mod.search_news("ATAI", "AtaiBeckley") == []  # mai un crash, mai dati inventati

    def test_circuit_breaker_stops_after_failures(self, monkeypatch):
        """Dopo 3 fallimenti consecutivi la discovery si sospende per il run."""
        import app.adapters.gdelt_news as mod

        class R:
            text = "rate limited"
            def json(self): raise ValueError("not json")

        monkeypatch.setattr(mod, "safe_fetch", lambda url, headers=None, max_bytes=None: R())
        monkeypatch.setattr(mod, "_throttle", lambda: None)
        mod.reset_circuit()
        for _ in range(3):
            mod.search_news("ATAI", "AtaiBeckley")
        assert mod.circuit_open() is True
        assert mod.search_news("ATAI", "AtaiBeckley") == []  # nessuna nuova richiesta
        mod.reset_circuit()
        assert mod.circuit_open() is False

    def test_query_builder(self):
        from app.adapters.gdelt_news import _build_query, clean_company_name
        assert clean_company_name("Crinetics Pharmaceuticals, Inc. Common Stock") == \
            "Crinetics Pharmaceuticals"
        assert clean_company_name("AtaiBeckley Inc.") == "AtaiBeckley"
        q = _build_query("ATAI", "AtaiBeckley Inc.")
        assert '"AtaiBeckley"' in q and '"ATAI stock"' in q
        assert _build_query("BTC/USD", "Bitcoin") == '("Bitcoin" OR "BTC stock") sourcelang:english'
        assert _build_query("XY", "XY") == '"XY stock" sourcelang:english'

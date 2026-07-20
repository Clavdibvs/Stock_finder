"""Pipeline live end-to-end con rete simulata:
universe_sync -> backfill -> ingest filing -> ranking -> dashboard.
"""
from __future__ import annotations

import os
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from app.adapters.base import Bar, NewsMetadata
from app.seed.demo import business_days_back, last_business_day


@pytest.fixture
def live_client(monkeypatch):
    from app.config import get_settings
    from app.db import reset_engine
    env = {
        "DDR_DATABASE_URL": "sqlite://",
        "DDR_APP_MODE": "live",
        "DDR_AUTH_DISABLED": "true",
        "DDR_COOKIE_SECURE": "false",
        "DDR_MARKET_DATA_PROVIDER": "alpaca",
        "DDR_ALPACA_KEY_ID": "test-key",
        "DDR_ALPACA_SECRET_KEY": "test-secret",
        "DDR_SEC_EDGAR_ENABLED": "true",
        "DDR_SEC_USER_AGENT": "Test User test@example.com",
        "DDR_BENCHMARK_TICKER": "IWM",
        # niente rete nei test: la news discovery resta spenta
        "DDR_NEWS_DISCOVERY_PROVIDER": "",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    reset_engine()
    from app.main import app
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()
    reset_engine()
    # ripristina l'ambiente demo per gli altri test
    os.environ.update({"DDR_APP_MODE": "demo", "DDR_MARKET_DATA_PROVIDER": "demo",
                       "DDR_ALPACA_KEY_ID": "", "DDR_ALPACA_SECRET_KEY": "",
                       "DDR_SEC_EDGAR_ENABLED": "false"})
    get_settings.cache_clear()


def _synthetic_bars(days: list[date], rally: bool) -> list[Bar]:
    """80 sedute flat; se rally: ultime due +20%/+12% con volume 6x."""
    bars = []
    price = 10.0
    for i, d in enumerate(days):
        ret, vol = 0.001, 500_000
        if rally and i == len(days) - 2:
            ret, vol = 0.20, 3_000_000
        elif rally and i == len(days) - 1:
            ret, vol = 0.12, 2_800_000
        new_price = price * (1 + ret)
        bars.append(Bar(bar_date=d, session="regular",
                        open=round(price, 4), high=round(new_price * 1.01, 4),
                        low=round(price * 0.99, 4), close=round(new_price, 4),
                        volume=vol, vwap=round((price + new_price) / 2, 4)))
        price = new_price
    return bars


def test_live_flow_produces_ranked_candidate(live_client, monkeypatch):
    asof = last_business_day()
    days = business_days_back(asof, 90)

    # --- mock SEC universe/anagrafica ---
    import app.adapters.sec_universe as uni
    monkeypatch.setattr(uni, "fetch_ticker_map", lambda: {
        "RLLY": {"cik": "0001111111", "name": "Rally Corp", "exchange": "NASDAQ"},
        "FLAT": {"cik": "0002222222", "name": "Flatline Inc", "exchange": "NYSE"},
    })
    monkeypatch.setattr(uni, "fetch_shares_outstanding", lambda cik: 50_000_000)

    # --- mock barre Alpaca ---
    from app.adapters.alpaca import AlpacaMarketDataAdapter

    def fake_bulk(self, tickers, start, end):
        window = [d for d in days if start <= d <= end]
        return {t: _synthetic_bars(window, rally=(t == "RLLY")) for t in tickers}

    monkeypatch.setattr(AlpacaMarketDataAdapter, "get_daily_bars_bulk", fake_bulk)

    # --- mock filing EDGAR: offering per RLLY ---
    from app.adapters.sec_edgar import SECEdgarAdapter

    def fake_filings(self, ticker, cik):
        if cik != "0001111111":
            return []
        return [NewsMetadata(
            url="https://www.sec.gov/Archives/edgar/data/1111111/acc9/424b5.htm",
            title="424B5 — Prospectus supplement (offering)",
            published_at=datetime.combine(days[-2], datetime.min.time(), tzinfo=UTC),
            publisher="SEC EDGAR", source_level=1,
            excerpt="Programma ATM ai sensi della shelf S-3 esistente.",
        )]

    monkeypatch.setattr(SECEdgarAdapter, "fetch_documents", fake_filings)

    # 1. universo
    r = live_client.post("/api/settings/universe",
                         json={"tickers": ["RLLY", "FLAT"]})
    assert r.status_code == 200
    assert set(r.json()["created"]) == {"RLLY", "FLAT"}

    # 2. backfill storico + ingestione filing
    r = live_client.post("/api/quality/jobs/backfill_history/run").json()
    assert r["result"]["status"] == "success"
    assert r["result"]["bars"] > 150  # 2 titoli + benchmark
    r = live_client.post("/api/quality/jobs/ingest_eod/run").json()
    assert r["result"]["status"] == "success"
    assert r["result"]["filings"] == 1

    # 3. ranking deterministico
    r = live_client.post("/api/quality/jobs/ranking_eod/run").json()
    assert r["result"]["status"] == "success"

    # 4. dashboard: RLLY è candidato, FLAT no
    d = live_client.get("/api/dashboard").json()
    tickers = [i["ticker"] for i in d["items"]]
    assert "RLLY" in tickers
    assert "FLAT" not in tickers
    rlly = next(i for i in d["items"] if i["ticker"] == "RLLY")
    assert rlly["is_demo"] is False
    assert rlly["risk_index"] is not None
    assert rlly["catalyst_type"] == "offering_or_dilution"
    assert rlly["confidence"] in ("B", "C")  # float assente: mai grade A
    assert rlly["squeeze_unknown"] is True   # niente short interest: sconosciuto

    # 5. scheda titolo completa
    detail = live_client.get(f"/api/securities/{rlly['id']}").json()
    assert detail["why_entered"]["candidate_reasons"]
    assert any(e["type"] == "offering_or_dilution" for e in detail["timeline"]["events"])
    assert "short_interest_pct_float" in (detail["thesis_risks"]["missing_data"] or []) or \
           "short_interest_pct_float" in detail["why_entered"]["missing_fields"]

    # 6. idempotenza del ranking live
    before = {i["ticker"]: i["risk_index"] for i in d["items"]}
    live_client.post("/api/quality/jobs/ranking_eod/run")
    after = {i["ticker"]: i["risk_index"]
             for i in live_client.get("/api/dashboard").json()["items"]}
    assert before == after

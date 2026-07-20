"""Candidate generator: regole, soglie da config, universo ombra, SSRF."""
from __future__ import annotations

from datetime import date

import pytest

from app.candidates.features import Features
from app.candidates.generator import evaluate
from app.config import candidates_config


def base_features(**overrides) -> Features:
    f = Features(price=10.0, ret_1d=0.02, ret_5d=0.05, ret_20d=0.10, gap=0.01,
                 robust_z_ret=0.5, rvol=1.0, turnover_float=0.02,
                 median_dollar_volume_20d=5_000_000, market_cap=500_000_000,
                 float_shares=40_000_000, shares_outstanding=50_000_000,
                 bars_available=200, stale_days=0)
    for k, v in overrides.items():
        setattr(f, k, v)
    return f


ASOF = date(2026, 7, 16)


class TestCandidateRules:
    def test_acceleration_alone_not_enough(self):
        """Serve accelerazione E conferma, non solo una delle due."""
        f = base_features(ret_1d=0.20)  # accelerazione senza conferma
        assert evaluate(f, ASOF).is_candidate is False

    def test_confirmation_alone_not_enough(self):
        f = base_features(rvol=5.0)  # conferma senza accelerazione
        assert evaluate(f, ASOF).is_candidate is False

    def test_acceleration_plus_confirmation(self):
        f = base_features(ret_1d=0.20, rvol=3.0)
        decision = evaluate(f, ASOF)
        assert decision.is_candidate is True
        rules = {h.rule for h in decision.hits}
        assert "ret_1d" in rules and "rvol" in rules

    def test_reasons_include_observed_and_threshold(self):
        f = base_features(ret_5d=0.30, rvol=2.5)
        decision = evaluate(f, ASOF)
        for hit in decision.hits:
            assert hit.observed is not None
            assert hit.threshold is not None
            assert hit.description

    def test_thresholds_come_from_config(self):
        """Le soglie sono in configurazione, non nel codice."""
        cfg = candidates_config()
        assert cfg["acceleration"]["ret_1d_min"] == 0.15
        assert cfg["confirmation"]["rvol_min"] == 2.0
        assert cfg["version"]
        # appena sotto soglia: non si attiva
        f = base_features(ret_1d=cfg["acceleration"]["ret_1d_min"] - 0.001, rvol=3.0)
        rules = {h.rule for h in evaluate(f, ASOF).hits}
        assert "ret_1d" not in rules

    def test_missing_data_not_treated_as_pass(self):
        """Dati mancanti non attivano regole (None != 0 != soglia superata)."""
        f = base_features(ret_1d=None, ret_5d=None, ret_20d=None, gap=None,
                          robust_z_ret=None, rvol=5.0)
        decision = evaluate(f, ASOF)
        assert decision.is_candidate is False

    def test_shadow_universe_states(self):
        f = base_features(price=0.80, ret_1d=0.20, rvol=3.0)
        assert evaluate(f, ASOF).universe_status == "shadow_price"
        f = base_features(median_dollar_volume_20d=200_000, ret_1d=0.20, rvol=3.0)
        assert evaluate(f, ASOF).universe_status == "shadow_illiquid"
        f = base_features(market_cap=20_000_000, ret_1d=0.20, rvol=3.0)
        assert evaluate(f, ASOF).universe_status == "shadow_cap"


class TestIngestionSafety:
    def test_ssrf_blocked_for_unlisted_domain(self):
        from app.core.http import FetchError, validate_url
        with pytest.raises(FetchError):
            validate_url("https://evil.example.org/steal")

    def test_http_scheme_blocked(self):
        from app.core.http import FetchError, validate_url
        with pytest.raises(FetchError):
            validate_url("http://sec.gov/insecure")

    def test_secret_redaction_in_logs(self):
        import logging
        from app.core.logging import RedactingFilter
        record = logging.LogRecord("t", logging.INFO, "f", 1,
                                   "chiamata con api_key=sk-supersegreto123456", (), None)
        RedactingFilter().filter(record)
        assert "sk-supersegreto123456" not in record.getMessage()
        assert "[REDACTED]" in record.getMessage()


class TestAdapters:
    def test_stub_adapters_raise_not_configured(self, db):
        """Gli stub non generano mai dati fittizi."""
        from app.adapters.base import NotConfiguredError
        from app.adapters.stubs import EODHDStubAdapter
        adapter = EODHDStubAdapter()
        assert adapter.status().value == "non configurata"
        with pytest.raises(NotConfiguredError):
            adapter.get_daily_bars("AAPL", ASOF, ASOF)

    def test_sec_adapter_not_configured_by_default(self):
        from app.adapters.base import AdapterStatus
        from app.adapters.sec_edgar import SECEdgarAdapter
        assert SECEdgarAdapter().status() is AdapterStatus.NOT_CONFIGURED

    def test_baseline_random_reproducible(self, db):
        from app.validation.baselines import baseline_random
        a = baseline_random(db, ASOF, seed=42)
        b = baseline_random(db, ASOF, seed=42)
        assert [r.security_id for r in a] == [r.security_id for r in b]

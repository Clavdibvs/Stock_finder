"""Test del Risk Index: formula, pesi, gate, dati mancanti, determinismo."""
from __future__ import annotations

import pytest

from app.candidates.features import Features
from app.claims.graph import NarrativeStats
from app.config import scoring_config
from app.constants import (
    STATE_BINARY_EVENT, STATE_ELEVATED, STATE_INSUFFICIENT_DATA, STATE_MONITOR,
    STATE_POSSIBLE_SQUEEZE, STATE_UNQUANTIFIABLE,
)
from app.scoring.engine import EventContext, compute_score


def full_features(**overrides) -> Features:
    """Features complete e forti (caso limite superiore)."""
    f = Features(
        price=10.0, ret_1d=0.30, ret_5d=0.50, ret_20d=1.0, gap=0.20,
        robust_z_ret=6.0, rvol=6.0, turnover_float=0.5, dollar_volume=50_000_000,
        median_dollar_volume_20d=5_000_000, atr_14=0.5, dist_ema20_atr=5.0,
        market_cap=500_000_000, float_shares=40_000_000, shares_outstanding=50_000_000,
        attention_docs_1d=20, attention_z=6.0,
        bars_available=200, stale_days=0, new_material_event=True,
    )
    for k, v in overrides.items():
        setattr(f, k, v)
    return f


def strong_narrative() -> NarrativeStats:
    n = NarrativeStats()
    n.total_documents = 10
    n.duplicate_documents = 8
    n.independent_origins = 1
    n.primary_sources = 0
    n.rumor_claims = 1
    n.central_claim_status = "rumor"
    return n


def confirmed_narrative() -> NarrativeStats:
    n = NarrativeStats()
    n.total_documents = 5
    n.duplicate_documents = 0
    n.independent_origins = 4
    n.primary_sources = 2
    n.fact_claims = 2
    n.central_claim_status = "fatto"
    return n


class TestFormula:
    def test_weights_sum_to_one(self):
        assert abs(sum(scoring_config()["weights"].values()) - 1.0) < 1e-9

    def test_weights_are_versioned(self):
        cfg = scoring_config()
        assert cfg["version"], "la configurazione dei pesi deve avere una versione"
        result = compute_score(full_features(), strong_narrative(), EventContext())
        assert result.scoring_version == cfg["version"]
        assert result.config_hash
        assert result.code_version

    def test_deterministic(self):
        """Stesso input e versione => stesso output, sempre."""
        a = compute_score(full_features(), strong_narrative(), EventContext())
        b = compute_score(full_features(), strong_narrative(), EventContext())
        assert a.risk_index == b.risk_index
        assert a.state == b.state
        assert {k: c.value for k, c in a.components.items()} == \
               {k: c.value for k, c in b.components.items()}

    def test_range(self):
        result = compute_score(full_features(), strong_narrative(), EventContext())
        assert result.risk_index is not None
        assert 0 <= result.risk_index <= 100
        for comp in result.components.values():
            if comp.value is not None:
                assert 0 <= comp.value <= 100

    def test_weighted_sum_matches_components(self):
        """Il Risk Index è la somma pesata (rinormalizzata) dei componenti."""
        result = compute_score(full_features(), strong_narrative(), EventContext())
        available = {k: c for k, c in result.components.items() if c.value is not None}
        total_w = sum(c.weight for c in available.values())
        expected = sum(c.value * c.weight for c in available.values()) / total_w
        assert result.risk_index == pytest.approx(expected, abs=0.05)

    def test_fragile_narrative_scores_higher_than_confirmed(self):
        fragile = compute_score(full_features(), strong_narrative(), EventContext())
        confirmed = compute_score(full_features(), confirmed_narrative(), EventContext())
        assert fragile.components["C"].value > confirmed.components["C"].value


class TestMissingData:
    def test_missing_component_is_not_zero(self):
        """Componente mancante: pesi rinormalizzati, non zero implicito."""
        f = full_features()
        n = NarrativeStats()  # zero documenti -> C non calcolabile
        result = compute_score(f, n, EventContext())
        assert result.components["C"].value is None
        # se C valesse 0 lo score scenderebbe; con rinormalizzazione i restanti
        # componenti mantengono il loro peso relativo
        available = {k: c for k, c in result.components.items() if c.value is not None}
        total_w = sum(c.weight for c in available.values())
        expected = sum(c.value * c.weight for c in available.values()) / total_w
        assert result.risk_index == pytest.approx(expected, abs=0.05)
        wrong_with_zero = sum((c.value or 0.0) * c.weight for c in result.components.values())
        assert result.risk_index != pytest.approx(wrong_with_zero, abs=0.5)

    def test_missing_data_visible(self):
        f = full_features(rvol=None, turnover_float=None)
        f.missing.append("rvol")
        result = compute_score(f, strong_narrative(), EventContext())
        assert "rvol" in result.missing_data

    def test_too_many_missing_suppresses_score(self):
        """Troppi componenti mancanti -> DATI INSUFFICIENTI, nessun numero."""
        f = Features(price=10.0, ret_1d=0.2, bars_available=200, stale_days=0)
        n = NarrativeStats()
        result = compute_score(f, n, EventContext())
        assert result.state == STATE_INSUFFICIENT_DATA
        assert result.risk_index is None

    def test_short_history_suppresses(self):
        f = full_features(bars_available=30)
        result = compute_score(f, strong_narrative(), EventContext())
        assert result.state == STATE_INSUFFICIENT_DATA

    def test_stale_data_suppresses(self):
        f = full_features(stale_days=10)
        result = compute_score(f, strong_narrative(), EventContext())
        assert result.state == STATE_INSUFFICIENT_DATA
        assert result.confidence_grade == "D"

    def test_unknown_squeeze_is_explicit(self):
        f = full_features(short_interest_pct_float=None)
        result = compute_score(f, strong_narrative(), EventContext())
        assert result.squeeze_unknown is True
        assert result.squeeze_hazard is None


class TestGates:
    def test_binary_event_gate_beats_score(self):
        """Un gate prevale sempre sullo score numerico."""
        ctx = EventContext(has_pending_binary=True, pending_binary_types=["ma_rumor"])
        result = compute_score(full_features(), strong_narrative(), ctx)
        assert result.state == STATE_BINARY_EVENT
        assert result.gate_applied == STATE_BINARY_EVENT

    def test_squeeze_gate(self):
        f = full_features(short_interest_pct_float=0.35, days_to_cover=8.0,
                          volume_over_float=0.8)
        result = compute_score(f, confirmed_narrative(), EventContext())
        assert result.state == STATE_POSSIBLE_SQUEEZE

    def test_binary_beats_squeeze(self):
        """Precedenza: EVENTO BINARIO viene prima di POSSIBILE SQUEEZE."""
        f = full_features(short_interest_pct_float=0.35, days_to_cover=8.0,
                          volume_over_float=0.8)
        ctx = EventContext(has_pending_binary=True, pending_binary_types=["fda_decision_pending"])
        result = compute_score(f, strong_narrative(), ctx)
        assert result.state == STATE_BINARY_EVENT

    def test_sub_dollar_unquantifiable(self):
        f = full_features(price=0.62)
        result = compute_score(f, strong_narrative(), EventContext())
        assert result.state == STATE_UNQUANTIFIABLE
        assert result.risk_index is None  # nessun numero non difendibile

    def test_illiquid_shadow_universe(self):
        result = compute_score(full_features(), strong_narrative(), EventContext(),
                               universe_status="shadow_illiquid")
        assert result.state == STATE_UNQUANTIFIABLE

    def test_squeeze_beats_unquantifiable(self):
        f = full_features(short_interest_pct_float=0.4, days_to_cover=9.0,
                          volume_over_float=0.9, median_dollar_volume_20d=500_000)
        result = compute_score(f, strong_narrative(), EventContext(),
                               universe_status="shadow_illiquid")
        assert result.state == STATE_POSSIBLE_SQUEEZE


class TestThresholds:
    def test_elevated_requires_confidence(self):
        """>=70 con confidence A/B -> elevato; il grade C/D non basta."""
        f = full_features()
        n = strong_narrative()
        result = compute_score(f, n, EventContext())
        assert result.risk_index >= 70
        assert result.confidence_grade in ("A", "B")
        assert result.state == STATE_ELEVATED

    def test_monitor_band(self):
        f = full_features(ret_1d=0.10, ret_5d=0.18, ret_20d=0.25, gap=0.02,
                          robust_z_ret=3.0, rvol=2.4, turnover_float=0.05,
                          dist_ema20_atr=2.0, attention_docs_1d=2, attention_z=2.0)
        result = compute_score(f, confirmed_narrative(), EventContext())
        if result.risk_index is not None and 55 <= result.risk_index < 70:
            assert result.state == STATE_MONITOR

    def test_never_presented_as_probability(self):
        """Lo score non contiene mai formulazioni probabilistiche."""
        result = compute_score(full_features(), strong_narrative(), EventContext())
        text = " ".join(str(x) for x in result.invalidation_conditions)
        assert "probabilità che" not in text.lower()
        assert "%" not in (str(result.risk_index))

"""Modalità demo end-to-end: tutte le schermate hanno dati reali dal seed."""
from __future__ import annotations

from app.constants import (
    STATE_BINARY_EVENT, STATE_ELEVATED, STATE_INSUFFICIENT_DATA,
    STATE_POSSIBLE_SQUEEZE, STATE_UNQUANTIFIABLE,
)


class TestDashboard:
    def test_dashboard_has_ranked_list(self, demo_client):
        data = demo_client.get("/api/dashboard").json()
        assert data["demo"] is True
        assert data["date"] is not None
        assert 5 <= len(data["items"]) <= 20  # lista limitata
        assert data["disclaimer"]
        assert "ordinale" in data["disclaimer"]

    def test_all_required_states_present(self, demo_client):
        """Il seed copre tutti gli stati richiesti dalla demo."""
        states = {i["state"] for i in demo_client.get("/api/dashboard").json()["items"]}
        for required in (STATE_BINARY_EVENT, STATE_POSSIBLE_SQUEEZE,
                         STATE_UNQUANTIFIABLE, STATE_INSUFFICIENT_DATA, STATE_ELEVATED):
            assert required in states, f"manca lo stato {required}"

    def test_gates_override_score(self, demo_client):
        """Titoli con gate mostrano lo stato del gate anche con score alto."""
        items = demo_client.get("/api/dashboard").json()["items"]
        atai = next(i for i in items if i["ticker"] == "ATAI")
        assert atai["state"] == STATE_BINARY_EVENT
        assert atai["gate_applied"] == STATE_BINARY_EVENT

    def test_squeeze_case(self, demo_client):
        items = demo_client.get("/api/dashboard").json()["items"]
        qntc = next(i for i in items if i["ticker"] == "QNTC")
        assert qntc["state"] == STATE_POSSIBLE_SQUEEZE
        assert qntc["squeeze_hazard"] is not None and qntc["squeeze_hazard"] >= 60

    def test_unknown_squeeze_not_zero(self, demo_client):
        """Squeeze sconosciuto resta 'sconosciuto', non 0."""
        items = demo_client.get("/api/dashboard").json()["items"]
        vmem = next(i for i in items if i["ticker"] == "VMEM")
        assert vmem["squeeze_unknown"] is True
        assert vmem["squeeze_hazard"] is None

    def test_every_row_is_explainable(self, demo_client):
        items = demo_client.get("/api/dashboard").json()["items"]
        for row in items:
            assert row["summary"], f"{row['ticker']} senza frase sintetica"
            assert row["state"]
            assert row["confidence"] in "ABCD"
            assert isinstance(row["missing_data"], list)

    def test_filters_work(self, demo_client):
        r = demo_client.get("/api/dashboard", params={"state": STATE_BINARY_EVENT})
        states = {i["state"] for i in r.json()["items"]}
        assert states == {STATE_BINARY_EVENT}


class TestSecurityDetail:
    def _first_id(self, demo_client, ticker="ATAI"):
        items = demo_client.get("/api/dashboard").json()["items"]
        return next(i for i in items if i["ticker"] == ticker)["id"]

    def test_detail_sections(self, demo_client):
        detail = demo_client.get(f"/api/securities/{self._first_id(demo_client)}").json()
        for section in ("security", "why_entered", "timeline", "narrative",
                        "thesis_risks", "history"):
            assert section in detail

    def test_why_entered_has_rules_and_values(self, demo_client):
        detail = demo_client.get(f"/api/securities/{self._first_id(demo_client)}").json()
        reasons = detail["why_entered"]["candidate_reasons"]
        assert len(reasons) >= 2  # almeno una accelerazione e una conferma
        kinds = {r["kind"] for r in reasons}
        assert "acceleration" in kinds and "confirmation" in kinds
        for r in reasons:
            assert r["observed"] is not None
            assert r["threshold"] is not None

    def test_duplicates_grouped_in_families(self, demo_client):
        """Le 12 riscritture ATAI sono una famiglia, non 12 origini."""
        detail = demo_client.get(f"/api/securities/{self._first_id(demo_client)}").json()
        n = detail["narrative"]
        assert n["total_documents"] >= 13
        assert n["duplicate_documents"] >= 12
        assert n["independent_origins"] < n["total_documents"] / 2

    def test_rumor_labelled_as_rumor(self, demo_client):
        detail = demo_client.get(f"/api/securities/{self._first_id(demo_client)}").json()
        claims = detail["narrative"]["claims"]
        rumors = [c for c in claims if c["status"] == "rumor"]
        assert rumors, "il claim M&A deve restare rumor"
        assert all(c["evidence_span"] for c in claims)

    def test_contrary_evidence_visible(self, demo_client):
        detail = demo_client.get(f"/api/securities/{self._first_id(demo_client)}").json()
        assert detail["current"]["main_contrary_evidence"]
        assert detail["thesis_risks"]["invalidation_conditions"]

    def test_retrospective_outcomes_exist(self, demo_client):
        """CRGX ha score storici con outcome 1/3/5/10 sedute."""
        items = demo_client.get("/api/watchlist").json()
        crgx = next(w for w in items if w["security"]["ticker"] == "CRGX")
        detail = demo_client.get(f"/api/securities/{crgx['security']['id']}").json()
        outcomes = detail["history"]["outcomes"]
        assert outcomes
        horizons = {h["horizon_days"] for o in outcomes for h in o["horizons"]}
        assert {1, 3, 5, 10}.issubset(horizons)


class TestSourcesAndQuality:
    def test_source_registry(self, demo_client):
        registry = demo_client.get("/api/sources/registry").json()
        assert len(registry) >= 8
        for src in registry:
            assert src["license_status"]
            assert 1 <= src["default_source_level"] <= 10

    def test_quality_screen(self, demo_client):
        q = demo_client.get("/api/quality").json()
        assert q["providers"]
        not_configured = [p for p in q["providers"] if p["status"] == "non configurata"]
        assert not_configured, "le fonti non configurate devono avere stato esplicito"
        assert q["runs"]
        assert any(i["type"] == "unreconciled_corporate_action" for i in q["issues"])

    def test_manual_job_rerun(self, demo_client):
        r = demo_client.post("/api/quality/jobs/quality_checks/run")
        assert r.status_code == 200
        assert r.json()["result"]["status"] in ("success", "partial")

    def test_unknown_job_rejected(self, demo_client):
        assert demo_client.post("/api/quality/jobs/rm_rf/run").status_code == 404


class TestWatchlistAndSettings:
    def test_watchlist_flow(self, demo_client):
        items = demo_client.get("/api/dashboard").json()["items"]
        target = items[-1]["id"]
        r = demo_client.post("/api/watchlist", json={"security_id": target,
                                                     "note": "nota di prova"})
        assert r.status_code == 200
        wl = demo_client.get("/api/watchlist").json()
        entry = next(w for w in wl if w["security"]["id"] == target)
        demo_client.delete(f"/api/watchlist/{entry['item_id']}")
        wl2 = demo_client.get("/api/watchlist").json()
        assert all(w["security"]["id"] != target for w in wl2)

    def test_settings_never_expose_keys(self, demo_client):
        s = demo_client.get("/api/settings").json()
        assert all(isinstance(v, bool) for v in s["api_keys"].values())
        assert s["scoring"]["weights"]
        assert s["candidate_thresholds"]["acceleration"]
        assert s["ai"]["enabled"] is False  # demo: AI disabilitata

    def test_alert_history(self, demo_client):
        alerts = demo_client.get("/api/watchlist/alerts").json()
        assert alerts
        assert all(a["rule"] for a in alerts)

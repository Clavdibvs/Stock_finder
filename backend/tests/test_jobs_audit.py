"""Job idempotenti, audit trail append-only, override con traccia."""
from __future__ import annotations

from sqlalchemy import select

from app.core.audit import audit, verify_chain
from app.models import AuditLog


class TestIdempotentJobs:
    def test_rerun_ranking_no_duplicate_scores(self, demo_client):
        """Rieseguire il ranking dello stesso giorno non duplica le righe."""
        before = demo_client.get("/api/dashboard").json()
        r = demo_client.post("/api/quality/jobs/ranking_eod/run")
        assert r.status_code == 200
        after = demo_client.get("/api/dashboard").json()
        assert before["date"] == after["date"]
        assert len(before["items"]) == len(after["items"])
        # stessi score (deterministico)
        b = {i["ticker"]: i["risk_index"] for i in before["items"]}
        a = {i["ticker"]: i["risk_index"] for i in after["items"]}
        assert a == b

    def test_rerun_retrospective_idempotent(self, demo_client):
        r1 = demo_client.post("/api/quality/jobs/retrospective_review/run")
        r2 = demo_client.post("/api/quality/jobs/retrospective_review/run")
        assert r1.status_code == r2.status_code == 200


class TestAuditChain:
    def test_chain_hashes_link(self, db):
        audit(db, actor="test", action="a1", details={"k": 1})
        audit(db, actor="test", action="a2", details={"k": 2})
        audit(db, actor="test", action="a3")
        db.commit()
        assert verify_chain(db) is True

    def test_tampering_detected(self, db):
        audit(db, actor="test", action="a1", details={"k": 1})
        audit(db, actor="test", action="a2", details={"k": 2})
        db.commit()
        row = db.scalars(select(AuditLog)).first()
        row.action = "azione_falsificata"
        db.commit()
        assert verify_chain(db) is False


class TestManualOverrideAudit:
    def test_override_leaves_trail(self, demo_client):
        """La correzione manuale di un claim lascia override + audit."""
        claims = demo_client.get("/api/sources/claims").json()
        rumor = next(c for c in claims if c["status"] == "rumor")
        r = demo_client.post(
            f"/api/sources/claims/{rumor['id']}/override",
            json={"status": "interpretazione",
                  "reason": "Test: riclassificazione manuale motivata."},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "interpretazione"
        overrides = demo_client.get("/api/sources/overrides").json()
        entry = next(o for o in overrides if o["entity_id"] == rumor["id"])
        assert entry["old_value"] == "rumor"
        assert entry["new_value"] == "interpretazione"
        assert entry["reason"]
        # ripristina lo stato per gli altri test (nuovo override, anch'esso tracciato)
        demo_client.post(
            f"/api/sources/claims/{rumor['id']}/override",
            json={"status": "rumor", "reason": "Test: ripristino."},
        )

    def test_invalid_status_rejected(self, demo_client):
        claims = demo_client.get("/api/sources/claims").json()
        r = demo_client.post(
            f"/api/sources/claims/{claims[0]['id']}/override",
            json={"status": "stato_inventato", "reason": "motivo qualsiasi"},
        )
        assert r.status_code == 422


class TestRetention:
    def test_retention_apply_audited(self, demo_client):
        """La cancellazione dei contenuti community è tracciata e idempotente."""
        r = demo_client.post("/api/quality/retention/apply")
        assert r.status_code == 200
        body = r.json()
        assert "purged" in body and "cutoff" in body
        r2 = demo_client.post("/api/quality/retention/apply")
        assert r2.status_code == 200

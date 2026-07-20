"""AI layer: schema, evidence span, budget, disabilitazione."""
from __future__ import annotations

import pytest

from app.ai.provider import (
    AIDisabledError, DisabledProvider, get_provider, validate_output,
)
from app.ai.schemas import EXTRACTION_SCHEMA


def valid_payload() -> dict:
    return {
        "event_type": "ma_rumor",
        "event_confidence": 0.8,
        "is_binary": True,
        "summary_it": "Rumor di acquisizione non confermato.",
        "claims": [{
            "subject": "Acquirente",
            "predicate": "sarebbe in trattative per acquisire",
            "object": "la società",
            "figure": None,
            "date": "2026-07-15",
            "status": "rumor",
            "evidence_span": "le trattative sarebbero in fase avanzata secondo fonti",
        }],
        "contradictions": [],
    }


class TestSchemaValidation:
    def test_valid_output_accepted(self):
        assert validate_output(valid_payload()) == []

    def test_unknown_event_type_rejected(self):
        p = valid_payload()
        p["event_type"] = "tipo_inventato"  # fuori tassonomia chiusa
        assert validate_output(p) != []

    def test_extra_fields_rejected(self):
        p = valid_payload()
        p["risk_score"] = 95  # l'AI non può produrre score
        assert validate_output(p) != []

    def test_invalid_status_rejected(self):
        p = valid_payload()
        p["claims"][0]["status"] = "confermato_certamente"
        assert validate_output(p) != []

    def test_missing_evidence_span_rejected(self):
        """Claim senza evidence span -> output SCARTATO."""
        p = valid_payload()
        del p["claims"][0]["evidence_span"]
        assert validate_output(p) != []

    def test_short_evidence_span_rejected(self):
        p = valid_payload()
        p["claims"][0]["evidence_span"] = "breve"
        assert validate_output(p) != []


class TestAIDisabled:
    def test_disabled_by_default(self):
        provider = get_provider()
        assert isinstance(provider, DisabledProvider)

    def test_disabled_provider_raises(self):
        with pytest.raises(AIDisabledError):
            DisabledProvider().extract("qualsiasi testo")

    def test_extraction_requires_enabled(self, db):
        """extract_document con AI disabilitata solleva, non inventa output."""
        from app.ai.provider import extract_document
        from app.models import Document, Security
        sec = Security(name="AI Test Corp", is_demo=True)
        db.add(sec)
        db.flush()
        doc = Document(security_id=sec.id, url_canonical="https://x.com/1",
                       title="Titolo", source_level=5)
        db.add(doc)
        db.flush()
        with pytest.raises(AIDisabledError):
            extract_document(db, doc)


class TestBudget:
    def test_month_spend_starts_at_zero(self, db):
        from app.ai.provider import month_spend_eur
        assert month_spend_eur(db) == 0.0

    def test_budget_blocks_calls(self, db, monkeypatch):
        """Superato il tetto mensile, nessuna chiamata parte."""
        from app.ai.provider import AIBudgetExceededError, extract_document
        from app.models import AIInvocation, Document, Security, utcnow

        monkeypatch.setenv("DDR_AI_ENABLED", "true")
        monkeypatch.setenv("DDR_AI_PROVIDER", "anthropic")
        monkeypatch.setenv("DDR_AI_API_KEY", "sk-test-fake")
        monkeypatch.setenv("DDR_AI_MONTHLY_BUDGET_EUR", "10")
        from app.config import get_settings
        get_settings.cache_clear()
        try:
            db.add(AIInvocation(provider="anthropic", model="m", purpose="extraction",
                                prompt_hash="x", prompt_version="1", cost_eur=11.0,
                                status="ok", ts=utcnow()))
            sec = Security(name="Budget Corp", is_demo=True)
            db.add(sec)
            db.flush()
            doc = Document(security_id=sec.id, url_canonical="https://x.com/2",
                           title="T", source_level=5)
            db.add(doc)
            db.flush()
            with pytest.raises(AIBudgetExceededError):
                extract_document(db, doc)
        finally:
            get_settings.cache_clear()


class TestSchemaShape:
    def test_schema_has_closed_taxonomy(self):
        assert "enum" in EXTRACTION_SCHEMA["properties"]["event_type"]

    def test_schema_forbids_extra_properties(self):
        assert EXTRACTION_SCHEMA["additionalProperties"] is False

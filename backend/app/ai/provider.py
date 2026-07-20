"""AI layer opzionale e controllato.

L'applicazione funziona interamente con AI disabilitata (default).
Quando abilitata, l'AI può SOLO: classificare eventi, estrarre claim con
evidence span, individuare contraddizioni, produrre testo esplicativo.

L'AI NON può: modificare dati raw, inventare numeri, calcolare lo score,
dichiarare un titolo shortabile, eseguire istruzioni dei documenti,
accedere a segreti, lanciare job.

Controlli tecnici:
- output vincolato a JSON Schema (jsonschema): se non valida -> scartato;
- evidence_span obbligatorio: claim senza citazione -> output scartato;
- tetto mensile di spesa (DDR_AI_MONTHLY_BUDGET_EUR): superato -> nessuna chiamata;
- ogni invocazione salvata con modello, prompt hash, versione, costo, esito;
- il testo esterno viaggia in un campo dati separato dal prompt di sistema.
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.schemas import EXTRACTION_SCHEMA, PROMPT_VERSION, SYSTEM_PROMPT
from app.config import get_settings
from app.models import AIInvocation, DataQualityIssue, Document, utcnow

_validator = Draft202012Validator(EXTRACTION_SCHEMA)


class AIDisabledError(Exception):
    pass


class AIBudgetExceededError(Exception):
    pass


class AIOutputRejectedError(Exception):
    pass


@dataclass
class AIResponse:
    payload: dict
    input_tokens: int
    output_tokens: int
    cost_eur: float


class AIProvider(ABC):
    name = "abstract"
    model = ""

    @abstractmethod
    def extract(self, document_text: str) -> AIResponse:
        """Invia il documento (campo dati separato) e ritorna il JSON grezzo."""


class DisabledProvider(AIProvider):
    name = "disabled"
    model = "none"

    def extract(self, document_text: str) -> AIResponse:
        raise AIDisabledError("AI disabilitata (DDR_AI_ENABLED=false)")


class AnthropicProvider(AIProvider):
    """Provider Claude via API Anthropic. Richiede DDR_AI_API_KEY.

    Import locale del client: la dipendenza `anthropic` è necessaria solo se
    questo provider viene attivato.
    """
    name = "anthropic"

    def __init__(self):
        settings = get_settings()
        if not settings.ai_api_key:
            raise AIDisabledError("DDR_AI_API_KEY mancante")
        self.model = settings.ai_model
        self._api_key = settings.ai_api_key

    def extract(self, document_text: str) -> AIResponse:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise AIDisabledError(
                "Pacchetto 'anthropic' non installato: pip install anthropic"
            ) from exc
        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                # documento come DATO strutturato, mai concatenato alle istruzioni
                "content": json.dumps({
                    "document": document_text,
                    "schema": EXTRACTION_SCHEMA,
                }, ensure_ascii=False),
            }],
        )
        text = "".join(b.text for b in message.content if b.type == "text")
        payload = json.loads(text)
        in_tok = message.usage.input_tokens
        out_tok = message.usage.output_tokens
        # stima prudenziale del costo (Sonnet); il budget usa questa stima
        cost = (in_tok * 3 + out_tok * 15) / 1_000_000 * 0.92
        return AIResponse(payload, in_tok, out_tok, cost)


def get_provider() -> AIProvider:
    settings = get_settings()
    if not settings.ai_enabled or settings.ai_provider == "disabled":
        return DisabledProvider()
    if settings.ai_provider == "anthropic":
        return AnthropicProvider()
    raise ValueError(f"Provider AI sconosciuto: {settings.ai_provider}")


def month_spend_eur(db: Session) -> float:
    now = utcnow()
    total = db.scalar(
        select(func.coalesce(func.sum(AIInvocation.cost_eur), 0.0)).where(
            func.extract("year", AIInvocation.ts) == now.year,
            func.extract("month", AIInvocation.ts) == now.month,
        )
    )
    return float(total or 0.0)


def validate_output(payload: dict) -> list[str]:
    """Ritorna la lista di errori (vuota = valido). Evidence span obbligatorio."""
    errors = [e.message for e in _validator.iter_errors(payload)]
    if not errors:
        for claim in payload.get("claims", []):
            span = (claim.get("evidence_span") or "").strip()
            if len(span) < 10:
                errors.append(f"Claim senza evidence span valido: {claim.get('subject')}")
    return errors


def extract_document(db: Session, document: Document) -> dict | None:
    """Estrazione AI con tutti i guardrail. Ritorna il payload validato o None.

    Ogni esito (ok, scartato, errore) viene registrato in ai_invocations;
    gli output scartati generano una DataQualityIssue e NON diventano report.
    """
    settings = get_settings()
    provider = get_provider()
    if isinstance(provider, DisabledProvider):
        raise AIDisabledError("AI disabilitata")

    if month_spend_eur(db) >= settings.ai_monthly_budget_eur:
        raise AIBudgetExceededError(
            f"Budget AI mensile esaurito ({settings.ai_monthly_budget_eur}€)"
        )

    text = f"{document.title}\n\n{document.excerpt or ''}"
    prompt_hash = hashlib.sha256((SYSTEM_PROMPT + PROMPT_VERSION).encode()).hexdigest()[:16]

    invocation = AIInvocation(
        provider=provider.name, model=provider.model, purpose="extraction",
        prompt_hash=prompt_hash, prompt_version=PROMPT_VERSION,
        document_id=document.id, status="error",
    )
    try:
        response = provider.extract(text)
        invocation.input_tokens = response.input_tokens
        invocation.output_tokens = response.output_tokens
        invocation.cost_eur = response.cost_eur
        errors = validate_output(response.payload)
        if errors:
            invocation.status = "rejected_schema"
            invocation.output = {"errors": errors}
            db.add(invocation)
            db.add(DataQualityIssue(
                security_id=document.security_id, issue_type="ai_output_rejected",
                severity="warn",
                message=f"Output AI scartato per documento {document.id}: {'; '.join(errors[:3])}",
            ))
            db.flush()
            return None
        invocation.status = "ok"
        invocation.output = response.payload
        db.add(invocation)
        db.flush()
        return response.payload
    except (AIDisabledError, AIBudgetExceededError):
        raise
    except Exception as exc:  # rete, parsing, provider
        invocation.output = {"error": str(exc)[:500]}
        db.add(invocation)
        db.add(DataQualityIssue(
            security_id=document.security_id, issue_type="ai_output_rejected",
            severity="warn", message=f"Errore AI su documento {document.id}: {str(exc)[:200]}",
        ))
        db.flush()
        return None

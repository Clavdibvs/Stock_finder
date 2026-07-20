"""Modello dati. Identificatore stabile della security separato dal ticker.

Convenzioni:
- tutti i timestamp sono UTC (datetime timezone-aware);
- i campi JSON usano tipi portabili (PostgreSQL JSONB-compatibile, SQLite nei test);
- nessun dato mancante viene mai rappresentato come 0: i campi sono nullable
  e la mancanza è esplicita.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """DateTime sempre timezone-aware UTC, anche su backend che perdono la tz (SQLite)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


def new_stable_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


# ---------------------------------------------------------------- accesso ---

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    # si salva SOLO l'hash del token, mai il token in chiaro
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


# --------------------------------------------------------------- anagrafe ---

class Security(Base):
    __tablename__ = "securities"
    id: Mapped[int] = mapped_column(primary_key=True)
    stable_id: Mapped[str] = mapped_column(String(32), unique=True, default=new_stable_id)
    name: Mapped[str] = mapped_column(String(256))
    cik: Mapped[str | None] = mapped_column(String(10), index=True)
    sector: Mapped[str | None] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(128))
    security_type: Mapped[str] = mapped_column(String(32), default="common_stock")
    country: Mapped[str] = mapped_column(String(2), default="US")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    listings: Mapped[list[SecurityListing]] = relationship(back_populates="security")


class SecurityListing(Base):
    __tablename__ = "security_listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(12), index=True)
    exchange: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | delisted
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    shares_outstanding: Mapped[float | None] = mapped_column(Float)
    float_shares: Mapped[float | None] = mapped_column(Float)
    # short interest ufficiale (FINRA, bimensile): None = sconosciuto, mai 0
    short_interest_shares: Mapped[float | None] = mapped_column(Float)
    short_interest_date: Mapped[date | None] = mapped_column(Date)

    security: Mapped[Security] = relationship(back_populates="listings")


class MarketBar(Base):
    __tablename__ = "market_bars"
    __table_args__ = (
        UniqueConstraint("security_id", "bar_date", "session", "provider", name="uq_bar"),
        Index("ix_bars_sec_date", "security_id", "bar_date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"))
    bar_date: Mapped[date] = mapped_column(Date)
    session: Mapped[str] = mapped_column(String(12), default="regular")  # regular|premarket|afterhours
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    vwap: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    adjusted: Mapped[bool] = mapped_column(Boolean, default=True)
    provider: Mapped[str] = mapped_column(String(32))
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CorporateAction(Base):
    __tablename__ = "corporate_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(32))  # split|reverse_split|ticker_change|merger|delisting|redomiciliation
    ratio: Mapped[float | None] = mapped_column(Float)  # es. 0.1 per reverse split 1:10
    effective_date: Mapped[date] = mapped_column(Date)
    reconciled: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


# ------------------------------------------------------- eventi/documenti ---

class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(24), default="occurred")  # pending|occurred|resolved_positive|resolved_negative
    is_binary: Mapped[bool] = mapped_column(Boolean, default=False)
    materiality: Mapped[str] = mapped_column(String(8), default="high")  # high|medium|low
    effective_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    announced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    classified_by: Mapped[str] = mapped_column(String(16), default="rule")  # rule|ai|manual
    classifier_confidence: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class DocumentSource(Base):
    """Registro delle fonti: produttore, livello di default, stato licenza."""
    __tablename__ = "document_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    domain: Mapped[str | None] = mapped_column(String(128))
    publisher: Mapped[str | None] = mapped_column(String(128))
    default_source_level: Mapped[int] = mapped_column(Integer, default=8)
    license_status: Mapped[str] = mapped_column(String(24), default="metadata_only")
    retention_policy: Mapped[str | None] = mapped_column(String(256))
    configured: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_docs_sec_pub", "security_id", "published_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int | None] = mapped_column(ForeignKey("securities.id"))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("document_sources.id"))
    url_canonical: Mapped[str] = mapped_column(String(1024))
    url_original: Mapped[str | None] = mapped_column(String(1024))
    title: Mapped[str] = mapped_column(String(512))
    author: Mapped[str | None] = mapped_column(String(256))
    publisher: Mapped[str | None] = mapped_column(String(256))
    # timestamp separati e obbligatori dove disponibili (D.3)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    effective_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    original_timezone: Mapped[str | None] = mapped_column(String(48))
    source_level: Mapped[int] = mapped_column(Integer, default=8)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    simhash: Mapped[int | None] = mapped_column(BigInteger)
    excerpt: Mapped[str | None] = mapped_column(Text)  # estratto breve, mai articolo completo protetto
    license_state: Mapped[str] = mapped_column(String(24), default="metadata_only")
    # famiglia duplicati: id del documento radice; il root punta a se stesso
    duplicate_family_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    subject: Mapped[str] = mapped_column(String(256))
    predicate: Mapped[str] = mapped_column(String(256))
    object: Mapped[str] = mapped_column(String(512))
    figure: Mapped[str | None] = mapped_column(String(128))  # cifra eventuale, come testo sorgente
    claim_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="rumor")  # fatto|rumor|opinione|interpretazione|previsione
    confirmation_level: Mapped[int | None] = mapped_column(Integer)  # miglior source level che lo supporta
    evidence_span: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    extracted_by: Mapped[str] = mapped_column(String(16), default="manual")  # rule|ai|manual
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ClaimRelation(Base):
    __tablename__ = "claim_relations"
    __table_args__ = (UniqueConstraint("claim_id", "related_claim_id", "relation", name="uq_claim_rel"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    related_claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"))
    relation: Mapped[str] = mapped_column(String(16))  # conferma|contraddice|cita|riscrive|deriva_da
    note: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


# ------------------------------------------------------- feature e score ----

class FeatureSnapshot(Base):
    """Snapshot point-in-time immutabile delle feature usate per lo scoring."""
    __tablename__ = "feature_snapshots"
    __table_args__ = (UniqueConstraint("security_id", "snapshot_date", name="uq_snapshot"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    asof_ts: Mapped[datetime] = mapped_column(UTCDateTime)
    features: Mapped[dict] = mapped_column(JSON)          # valori osservati (null = mancante)
    missing_fields: Mapped[list | None] = mapped_column(JSON)
    is_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    candidate_reasons: Mapped[list | None] = mapped_column(JSON)  # regole attivate + valori + soglie
    provider: Mapped[str | None] = mapped_column(String(32))
    pipeline_version: Mapped[str] = mapped_column(String(16))
    config_version: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RiskScore(Base):
    __tablename__ = "risk_scores"
    __table_args__ = (UniqueConstraint("security_id", "score_date", name="uq_score"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    feature_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("feature_snapshots.id"))
    score_date: Mapped[date] = mapped_column(Date, index=True)
    risk_index: Mapped[float | None] = mapped_column(Float)       # None = non pubblicabile
    squeeze_hazard: Mapped[float | None] = mapped_column(Float)   # None = sconosciuto
    squeeze_unknown: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_hazard: Mapped[float | None] = mapped_column(Float)
    dilution_risk: Mapped[float | None] = mapped_column(Float)    # componente D esposta in dashboard
    confidence_grade: Mapped[str] = mapped_column(String(1))
    state: Mapped[str] = mapped_column(String(64), index=True)
    gate_applied: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(Text)             # frase sintetica
    main_contrary_evidence: Mapped[str | None] = mapped_column(Text)
    invalidation_conditions: Mapped[list | None] = mapped_column(JSON)
    missing_data: Mapped[list | None] = mapped_column(JSON)
    independent_origins: Mapped[int | None] = mapped_column(Integer)
    catalyst_type: Mapped[str | None] = mapped_column(String(48))
    scoring_version: Mapped[str] = mapped_column(String(16))
    config_hash: Mapped[str] = mapped_column(String(16))
    code_version: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    factors: Mapped[list[ScoreFactor]] = relationship(back_populates="risk_score")


class ScoreFactor(Base):
    __tablename__ = "score_factors"
    id: Mapped[int] = mapped_column(primary_key=True)
    risk_score_id: Mapped[int] = mapped_column(ForeignKey("risk_scores.id"), index=True)
    component: Mapped[str] = mapped_column(String(2))   # R|V|A|C|D|F|B
    name: Mapped[str] = mapped_column(String(128))
    direction: Mapped[int] = mapped_column(Integer)     # +1 alza lo score, -1 lo riduce, 0 informativo
    value: Mapped[float | None] = mapped_column(Float)  # percentile 0-100; None = mancante
    weight: Mapped[float] = mapped_column(Float)
    missing: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str | None] = mapped_column(Text)

    risk_score: Mapped[RiskScore] = relationship(back_populates="factors")


# ------------------------------------------------------------- operativo ----

class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    removed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int | None] = mapped_column(ForeignKey("securities.id"))
    rule: Mapped[str] = mapped_column(String(48))  # condizione che l'ha generata
    title: Mapped[str] = mapped_column(String(256))
    body: Mapped[str | None] = mapped_column(Text)
    dedup_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(48), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|success|partial|failed
    items_processed: Mapped[int] = mapped_column(Integer, default=0)
    triggered_by: Mapped[str] = mapped_column(String(16), default="schedule")  # schedule|manual
    idempotency_key: Mapped[str | None] = mapped_column(String(128), index=True)
    errors: Mapped[list | None] = mapped_column(JSON)
    run_metadata: Mapped[dict | None] = mapped_column(JSON)


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_runs.id"))
    security_id: Mapped[int | None] = mapped_column(ForeignKey("securities.id"))
    issue_type: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(8), default="warn")  # info|warn|error
    message: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ManualOverride(Base):
    __tablename__ = "manual_overrides"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int] = mapped_column(Integer)
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RetrospectiveOutcome(Base):
    __tablename__ = "retrospective_outcomes"
    __table_args__ = (UniqueConstraint("risk_score_id", "horizon_days", name="uq_retro"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    risk_score_id: Mapped[int] = mapped_column(ForeignKey("risk_scores.id"), index=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    reference_price: Mapped[float] = mapped_column(Float)      # P0 coerente col momento del segnale
    reference_date: Mapped[date] = mapped_column(Date)
    horizon_days: Mapped[int] = mapped_column(Integer)         # 1|3|5|10|20 sedute
    dd_intraday: Mapped[float | None] = mapped_column(Float)   # min(Low_d/P0 - 1)
    dd_close: Mapped[float | None] = mapped_column(Float)
    ret_close: Mapped[float | None] = mapped_column(Float)
    ret_vs_benchmark: Mapped[float | None] = mapped_column(Float)
    ret_vs_sector: Mapped[float | None] = mapped_column(Float)
    max_adverse_up: Mapped[float | None] = mapped_column(Float)  # massimo rialzo contrario alla tesi
    hit_minus10: Mapped[bool | None] = mapped_column(Boolean)
    hit_minus20: Mapped[bool | None] = mapped_column(Boolean)
    hit_minus30: Mapped[bool | None] = mapped_column(Boolean)
    hit_minus40: Mapped[bool | None] = mapped_column(Boolean)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)  # finestra chiusa
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    """Append-only: ogni riga concatena l'hash della precedente."""
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(32))
    details: Mapped[dict | None] = mapped_column(JSON)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class AIInvocation(Base):
    """Audit delle chiamate AI: modello, prompt, versione, costo, esito."""
    __tablename__ = "ai_invocations"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(48))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(16))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_eur: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24))  # ok|rejected_schema|rejected_evidence|error
    output: Mapped[dict | None] = mapped_column(JSON)

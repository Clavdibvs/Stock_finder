"""Contratti degli adapter — anti lock-in.

Ogni provider di mercato implementa MarketDataAdapter; ogni fonte documentale
implementa DocumentSourceAdapter. Nessun identificativo proprietario è chiave
primaria nei dati normalizzati.

Se una fonte non è configurata: stato NOT_CONFIGURED, nessun dato fittizio
silenzioso, confidence ridotta a valle, il dato mancante resta mancante.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class AdapterStatus(str, Enum):
    OK = "ok"
    NOT_CONFIGURED = "non configurata"
    ERROR = "errore"
    STALE = "stale"


@dataclass
class Bar:
    bar_date: date
    session: str  # regular | premarket | afterhours
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    vwap: float | None = None


@dataclass
class ReferenceData:
    ticker: str
    name: str
    exchange: str | None = None
    cik: str | None = None
    sector: str | None = None
    shares_outstanding: float | None = None
    float_shares: float | None = None
    security_type: str = "common_stock"


@dataclass
class CorporateActionData:
    action_type: str
    effective_date: date
    ratio: float | None = None
    details: dict = field(default_factory=dict)


@dataclass
class NewsMetadata:
    """Solo metadati e estratti brevi: mai articoli completi protetti."""
    url: str
    title: str
    published_at: datetime | None
    publisher: str | None = None
    author: str | None = None
    excerpt: str | None = None
    source_level: int = 8
    original_timezone: str | None = None


class MarketDataAdapter(ABC):
    """Interfaccia comune per i provider di mercato (sostituibili)."""
    name: str = "abstract"

    @abstractmethod
    def status(self) -> AdapterStatus: ...

    @abstractmethod
    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[Bar]: ...

    @abstractmethod
    def get_intraday_bars(self, ticker: str, day: date) -> list[Bar]: ...

    @abstractmethod
    def get_reference_data(self, ticker: str) -> ReferenceData | None: ...

    @abstractmethod
    def get_corporate_actions(self, ticker: str, start: date, end: date) -> list[CorporateActionData]: ...

    @abstractmethod
    def get_delisted(self) -> list[ReferenceData]: ...

    @abstractmethod
    def get_news_metadata(self, ticker: str, start: date, end: date) -> list[NewsMetadata]: ...


class DocumentSourceAdapter(ABC):
    """Fonte documentale ufficiale (SEC, FDA, ClinicalTrials, IR, halt...)."""
    name: str = "abstract"

    @abstractmethod
    def status(self) -> AdapterStatus: ...

    @abstractmethod
    def fetch_documents(self, ticker: str, cik: str | None = None) -> list[NewsMetadata]: ...


class NotConfiguredError(Exception):
    """La fonte non è configurata: il chiamante registra l'issue e prosegue
    senza inventare dati."""

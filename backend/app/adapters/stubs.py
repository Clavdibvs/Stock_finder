"""Stub documentati per i provider commerciali e le altre fonti ufficiali.

Ogni stub implementa l'interfaccia comune ma risponde NOT_CONFIGURED finché
non viene fornita una API key e completata l'integrazione. NESSUNO stub
genera dati fittizi: la mancanza di configurazione è uno stato esplicito
che riduce la confidence, non uno zero silenzioso.

Prima di attivare un provider commerciale leggere SOURCE_REGISTRY.md:
serve conferma scritta su retention, feature derivate, backtest e
cancellazione alla cessazione (hard gate del progetto).
"""
from __future__ import annotations

from datetime import date

from app.adapters.base import (
    AdapterStatus, Bar, CorporateActionData, DocumentSourceAdapter,
    MarketDataAdapter, NewsMetadata, NotConfiguredError, ReferenceData,
)
from app.config import get_settings


class _UnconfiguredMarketAdapter(MarketDataAdapter):
    """Base per gli stub di mercato: tutte le chiamate sollevano NotConfiguredError."""
    name = "unconfigured"
    docs_url = ""

    def _key(self) -> str:
        return get_settings().market_data_api_key

    def status(self) -> AdapterStatus:
        return AdapterStatus.NOT_CONFIGURED

    def _raise(self):
        raise NotConfiguredError(
            f"Provider '{self.name}' non configurato. Serve API key (DDR_MARKET_DATA_API_KEY), "
            f"completare l'integrazione e verificare la licenza ({self.docs_url}). "
            "Vedi SOURCE_REGISTRY.md."
        )

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[Bar]:
        self._raise()

    def get_intraday_bars(self, ticker: str, day: date) -> list[Bar]:
        self._raise()

    def get_reference_data(self, ticker: str) -> ReferenceData | None:
        self._raise()

    def get_corporate_actions(self, ticker: str, start: date, end: date) -> list[CorporateActionData]:
        self._raise()

    def get_delisted(self) -> list[ReferenceData]:
        self._raise()

    def get_news_metadata(self, ticker: str, start: date, end: date) -> list[NewsMetadata]:
        self._raise()


class EODHDStubAdapter(_UnconfiguredMarketAdapter):
    """EODHD (candidato principale del bake-off, vedi ricerca D.5).

    Integrazione prevista: REST https://eodhd.com/api/eod/{TICKER}.US,
    /api/fundamentals, /api/splits. Prima di attivare: conferma scritta su
    conservazione storica, feature derivate, backtest personale, backup,
    cancellazione alla cessazione, uso non-display.
    """
    name = "eodhd_stub"
    docs_url = "https://eodhd.com/"


class TiingoStubAdapter(_UnconfiguredMarketAdapter):
    """Tiingo (secondo candidato del bake-off).

    Integrazione prevista: https://api.tiingo.com/tiingo/daily/{ticker}/prices.
    Nota: IEX intraday non equivale al consolidato SIP; il volume pre-market
    non è completo.
    """
    name = "tiingo_stub"
    docs_url = "https://www.tiingo.com/about/pricing"


class AlpacaStubAdapter(_UnconfiguredMarketAdapter):
    """Alpaca Market Data (POC e fallback; free tier = IEX, non consolidato)."""
    name = "alpaca_stub"
    docs_url = "https://alpaca.markets/data"


class _UnconfiguredDocAdapter(DocumentSourceAdapter):
    name = "unconfigured"
    hint = ""

    def status(self) -> AdapterStatus:
        return AdapterStatus.NOT_CONFIGURED

    def fetch_documents(self, ticker: str, cik: str | None = None) -> list[NewsMetadata]:
        raise NotConfiguredError(f"Fonte '{self.name}' non configurata. {self.hint}")


class ClinicalTrialsStubAdapter(_UnconfiguredDocAdapter):
    """ClinicalTrials.gov API v2 (gratuita): https://clinicaltrials.gov/data-api/api.
    Conservare sia submission date sia posting date (possono differire)."""
    name = "clinicaltrials"
    hint = "Impostare DDR_CLINICALTRIALS_ENABLED=true e completare l'integrazione."


class OpenFDAStubAdapter(_UnconfiguredDocAdapter):
    """openFDA (gratuita con chiave: 240 req/min): https://open.fda.gov/apis/authentication/."""
    name = "openfda"
    hint = "Impostare DDR_OPENFDA_API_KEY."


class IRRssStubAdapter(_UnconfiguredDocAdapter):
    """RSS investor relations per singola società (config per-security)."""
    name = "ir_rss"
    hint = "Aggiungere i feed RSS IR delle società seguite nell'allowlist."


class NasdaqHaltsStubAdapter(_UnconfiguredDocAdapter):
    """Nasdaq Trade Halt RSS (gratuito, aggiornato ogni minuto):
    https://nasdaqtrader.com/Trader.aspx?id=TradeHaltRSS. Non interrogare
    più frequentemente del feed."""
    name = "nasdaq_halts"
    hint = "Impostare DDR_NASDAQ_HALTS_ENABLED=true."


class FINRAStubAdapter(_UnconfiguredDocAdapter):
    """FINRA short interest (ufficiale, due volte al mese). Il daily short
    volume NON è short interest e non va convertito in 'percentuale short'."""
    name = "finra"
    hint = "Impostare DDR_FINRA_ENABLED=true."


class BraveDiscoveryStubAdapter(_UnconfiguredDocAdapter):
    """Brave Search API per discovery news (metadata + link, mai contenuto
    integrale). I diritti sui contenuti terzi non vengono trasferiti."""
    name = "brave_discovery"
    hint = "Impostare DDR_NEWS_DISCOVERY_PROVIDER=brave e la relativa API key."

"""Adapter reale per Alpaca Market Data (piano free, feed IEX).

Motivazione (ricerca D.5): Alpaca free è il POC/fallback a costo zero con API
ufficiale. Limiti dichiarati e non aggirati:
- il feed IEX è una frazione del consolidato SIP: i volumi (specie pre-market)
  sono parziali;
- niente delisted né float/short interest: quei campi restano mancanti
  (mai zero) e la confidence si riduce;
- le barre arrivano GIÀ rettificate (adjustment=all): la riconciliazione degli
  split è delegata al provider (vedi DECISIONS.md).

SOLO dati: questo adapter usa esclusivamente endpoint di market data e
metadati asset. Nessun endpoint di trading viene mai chiamato (invariante
del progetto: nessun collegamento operativo a broker).
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from urllib.parse import urlencode

from app.adapters.base import (
    AdapterStatus, Bar, CorporateActionData, MarketDataAdapter, NewsMetadata,
    NotConfiguredError, ReferenceData,
)
from app.config import get_settings
from app.core.http import FetchError, safe_fetch

logger = logging.getLogger(__name__)

DATA_HOST = "https://data.alpaca.markets"
# assets = metadati anagrafici (nome, exchange); NON è un endpoint di trading
ASSET_HOSTS = ["https://paper-api.alpaca.markets", "https://api.alpaca.markets"]

_CHUNK = 100          # simboli per richiesta bulk
_PAGE_LIMIT = 10_000  # barre per pagina


class AlpacaMarketDataAdapter(MarketDataAdapter):
    name = "alpaca"

    def status(self) -> AdapterStatus:
        s = get_settings()
        if s.alpaca_key_id and s.alpaca_secret_key:
            return AdapterStatus.OK
        return AdapterStatus.NOT_CONFIGURED

    def _headers(self) -> dict[str, str]:
        s = get_settings()
        if not (s.alpaca_key_id and s.alpaca_secret_key):
            raise NotConfiguredError(
                "Alpaca non configurato: impostare DDR_ALPACA_KEY_ID e "
                "DDR_ALPACA_SECRET_KEY (piano free su alpaca.markets)."
            )
        return {
            "APCA-API-KEY-ID": s.alpaca_key_id,
            "APCA-API-SECRET-KEY": s.alpaca_secret_key,
            "Accept": "application/json",
        }

    # ------------------------------------------------------------- barre ---

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[Bar]:
        return self.get_daily_bars_bulk([ticker], start, end).get(ticker, [])

    def get_daily_bars_bulk(self, tickers: list[str], start: date,
                            end: date) -> dict[str, list[Bar]]:
        """Barre giornaliere per molti simboli (chunk + paginazione)."""
        headers = self._headers()
        out: dict[str, list[Bar]] = {t: [] for t in tickers}
        for i in range(0, len(tickers), _CHUNK):
            chunk = tickers[i:i + _CHUNK]
            page_token: str | None = None
            while True:
                params = {
                    "symbols": ",".join(chunk),
                    "timeframe": "1Day",
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "adjustment": "all",
                    "feed": "iex",
                    "limit": _PAGE_LIMIT,
                }
                if page_token:
                    params["page_token"] = page_token
                url = f"{DATA_HOST}/v2/stocks/bars?{urlencode(params)}"
                resp = safe_fetch(url, headers=headers)
                payload = resp.json()
                for symbol, bars in (payload.get("bars") or {}).items():
                    for b in bars:
                        out.setdefault(symbol, []).append(Bar(
                            bar_date=datetime.fromisoformat(
                                b["t"].replace("Z", "+00:00")
                            ).astimezone(UTC).date(),
                            session="regular",
                            open=b.get("o"), high=b.get("h"),
                            low=b.get("l"), close=b.get("c"),
                            volume=b.get("v"), vwap=b.get("vw"),
                        ))
                page_token = payload.get("next_page_token")
                if not page_token:
                    break
        return out

    def get_crypto_bars_bulk(self, pairs: list[str], start: date,
                             end: date) -> dict[str, list[Bar]]:
        """Barre giornaliere crypto (coppie tipo BTC/USD, feed us)."""
        headers = self._headers()
        out: dict[str, list[Bar]] = {p: [] for p in pairs}
        for i in range(0, len(pairs), _CHUNK):
            chunk = pairs[i:i + _CHUNK]
            page_token: str | None = None
            while True:
                params = {
                    "symbols": ",".join(chunk),
                    "timeframe": "1Day",
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "limit": _PAGE_LIMIT,
                }
                if page_token:
                    params["page_token"] = page_token
                url = f"{DATA_HOST}/v1beta3/crypto/us/bars?{urlencode(params)}"
                resp = safe_fetch(url, headers=headers)
                payload = resp.json()
                for symbol, bars in (payload.get("bars") or {}).items():
                    for b in bars:
                        out.setdefault(symbol, []).append(Bar(
                            bar_date=datetime.fromisoformat(
                                b["t"].replace("Z", "+00:00")
                            ).astimezone(UTC).date(),
                            session="regular",
                            open=b.get("o"), high=b.get("h"),
                            low=b.get("l"), close=b.get("c"),
                            volume=b.get("v"), vwap=b.get("vw"),
                        ))
                page_token = payload.get("next_page_token")
                if not page_token:
                    break
        return out

    def list_assets(self, asset_class: str = "us_equity") -> list[dict]:
        """Elenco asset attivi dal provider (metadati anagrafici, mai trading).

        L'elenco completo può superare i 5 MB: qui si usa un limite maggiore
        dedicato (30 MB) mantenendo tutte le altre protezioni.
        """
        headers = self._headers()
        for host in ASSET_HOSTS:
            try:
                resp = safe_fetch(
                    f"{host}/v2/assets?status=active&asset_class={asset_class}",
                    headers=headers, max_bytes=30_000_000,
                )
                return resp.json()
            except FetchError:
                continue
        return []

    def get_intraday_bars(self, ticker: str, day: date) -> list[Bar]:
        """Non usato nell'MVP live (niente pre-market col solo EOD)."""
        return []

    # ---------------------------------------------------------- anagrafe ---

    def get_reference_data(self, ticker: str) -> ReferenceData | None:
        headers = self._headers()
        for host in ASSET_HOSTS:
            try:
                resp = safe_fetch(f"{host}/v2/assets/{ticker}", headers=headers)
                a = resp.json()
                return ReferenceData(
                    ticker=ticker,
                    name=a.get("name") or ticker,
                    exchange=a.get("exchange"),
                    security_type="common_stock" if a.get("class") == "us_equity"
                                  else (a.get("class") or "common_stock"),
                    # Alpaca non fornisce shares/float: restano mancanti
                )
            except FetchError:
                continue
            except Exception:  # noqa: BLE001 - host successivo
                continue
        return None

    def get_corporate_actions(self, ticker: str, start: date, end: date) -> list[CorporateActionData]:
        """Le barre arrivano già rettificate (adjustment=all): gli split sono
        gestiti alla fonte e non vengono registrati come azioni da riconciliare."""
        return []

    def get_delisted(self) -> list[ReferenceData]:
        """Non disponibile sul piano free: limite documentato (survivorship
        bias nel backtest; per la Fase 0/3 serve un dataset point-in-time)."""
        return []

    def get_news_metadata(self, ticker: str, start: date, end: date) -> list[NewsMetadata]:
        return []

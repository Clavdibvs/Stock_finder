"""Configurazione applicativa.

Due livelli:
- variabili d'ambiente (segreti, connessioni, feature flag) via pydantic-settings;
- file YAML versionati in ./config per soglie candidate generator, pesi scoring e job.

Le YAML sono la fonte dei parametri quantitativi: niente soglie disperse nel codice.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

APP_VERSION = "0.2.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DDR_", extra="ignore")

    # --- modalità ---
    app_mode: str = "demo"  # "demo" | "live"
    debug: bool = False

    # --- database ---
    database_url: str = "postgresql+psycopg://ddr:ddr@localhost:5432/ddr"

    # --- accesso privato mono-utente ---
    admin_username: str = "admin"
    # password iniziale SOLO per bootstrap; al primo avvio viene hashata e
    # salvata; cambiala subito da .env o via bootstrap script.
    admin_password: str = ""
    # se l'istanza è dietro Tailscale/access proxy si può disabilitare il login
    auth_disabled: bool = False
    session_secret: str = ""  # obbligatoria se auth attiva; generata dal bootstrap
    session_ttl_hours: int = 12
    cookie_secure: bool = True
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    # --- provider (tutti sostituibili; vuoto = non configurato) ---
    market_data_provider: str = "demo"  # demo | alpaca | eodhd_stub | tiingo_stub
    market_data_api_key: str = ""
    # Alpaca Market Data (piano free, feed IEX): solo dati, MAI ordini
    alpaca_key_id: str = ""
    alpaca_secret_key: str = ""
    sec_edgar_enabled: bool = False
    # SEC fair access: user agent identificabile obbligatorio
    sec_user_agent: str = ""
    openfda_api_key: str = ""
    clinicaltrials_enabled: bool = False
    nasdaq_halts_enabled: bool = False
    finra_enabled: bool = False
    news_discovery_provider: str = "gdelt"  # gdelt (gratuito) | brave (chiave) | "" (off)
    news_discovery_api_key: str = ""

    # --- universo live ---
    # "auto": scoperta automatica dell'intero listino USA dal provider
    # "explicit": solo la lista DDR_UNIVERSE_TICKERS / UI
    universe_mode: str = "explicit"
    universe_tickers: str = ""          # es. "ATAI,SAVA,MARA,IONQ" (modalità explicit)
    benchmark_ticker: str = "IWM"       # proxy Russell 2000 per outcome relativi
    backfill_days: int = 400            # storico iniziale universo esplicito
    discover_backfill_days: int = 130   # storico iniziale in auto-discovery (full market)
    crypto_enabled: bool = False        # screening coppie crypto (confidence max C)

    # --- AI opzionale (default: disabilitata) ---
    ai_enabled: bool = False
    ai_provider: str = "disabled"  # disabled | anthropic
    ai_api_key: str = ""
    ai_model: str = "claude-sonnet-5"
    ai_monthly_budget_eur: float = 20.0
    ai_max_candidates: int = 10  # enrichment solo sui candidati principali

    # --- ingestion safety ---
    ingest_timeout_seconds: int = 20
    ingest_max_bytes: int = 5_000_000
    ingest_allowed_domains: str = (
        "sec.gov,data.sec.gov,efts.sec.gov,clinicaltrials.gov,api.fda.gov,"
        "nasdaqtrader.com,finra.org,api.finra.org,alpaca.markets,search.brave.com,"
        "gdeltproject.org"
    )

    # --- retention / export ---
    data_dir: str = str(BASE_DIR / "data")
    retention_documents_days: int = 730
    retention_social_days: int = 30

    # --- notifiche ---
    notify_channel: str = "none"  # none (solo in-app) | telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def allowed_domains(self) -> list[str]:
        return [d.strip().lower() for d in self.ingest_allowed_domains.split(",") if d.strip()]

    @property
    def universe_ticker_list(self) -> list[str]:
        return [t.strip().upper() for t in self.universe_tickers.split(",") if t.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache
def scoring_config() -> dict[str, Any]:
    cfg = _load_yaml("scoring.yaml")
    weights = cfg["weights"]
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"I pesi dello scoring devono sommare a 1.0, trovato {total}")
    return cfg


@lru_cache
def candidates_config() -> dict[str, Any]:
    return _load_yaml("candidates.yaml")


@lru_cache
def jobs_config() -> dict[str, Any]:
    return _load_yaml("jobs.yaml")


def config_hash() -> str:
    """Hash deterministico della configurazione quantitativa, salvato negli score."""
    payload = json.dumps(
        {"scoring": scoring_config(), "candidates": candidates_config()},
        sort_keys=True, default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def clear_config_cache() -> None:
    """Per i test: ricarica le YAML."""
    scoring_config.cache_clear()
    candidates_config.cache_clear()
    jobs_config.cache_clear()

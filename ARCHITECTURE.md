# Architettura

## Principi

- **Il più piccolo sistema che funziona**: un VPS, un database, un backend, una
  SPA statica. Niente Kubernetes, Kafka, vector DB, multi-agent framework,
  modelli locali, microservizi o monitoraggio tick-by-tick.
- **Determinismo**: ogni numero mostrato è ricalcolabile da codice
  deterministico + configurazione versionata + dati point-in-time.
- **Provider sostituibili**: ogni fonte implementa un contratto comune; nessun
  identificativo proprietario è chiave primaria.
- **La mancanza di dati è uno stato esplicito**, mai uno zero.

## Componenti

```
                      ┌────────────────────────── VPS ──────────────────────────┐
   Internet ──443──▶  │  Caddy (TLS, security headers, SPA statica)             │
                      │    │  /api/*                                            │
                      │    ▼                                                    │
                      │  FastAPI (uvicorn, rete interna, utente non-root)       │
                      │    ├─ API private (sessione+CSRF, rate limit login)     │
                      │    ├─ APScheduler (job giornalieri, orari ET)           │
                      │    ├─ Feature engine + candidate generator              │
                      │    ├─ Claim graph + dedup                               │
                      │    ├─ Scoring engine + gate                             │
                      │    ├─ Retrospective + baseline + export DuckDB/Parquet  │
                      │    └─ Adapters (demo, SEC EDGAR, stub commerciali)      │
                      │    ▼                                                    │
                      │  PostgreSQL 16 (volume persistente, rete interna)       │
                      │                                                         │
                      │  Restic ──▶ repository di backup cifrato (esterno)      │
                      └─────────────────────────────────────────────────────────┘
```

- **Caddy** è l'unico servizio esposto. Serve la SPA compilata e fa da reverse
  proxy per `/api/*`. TLS automatico con dominio reale; `:80` per uso dietro
  Tailscale/VPN.
- **FastAPI** non espone porte sull'host. Migrazioni Alembic all'avvio del
  container.
- **PostgreSQL** solo sulla rete interna Docker, volume `pgdata`.
- **DuckDB** è una libreria embedded usata per l'export Parquet/CSV (backtest e
  freeze giornaliero), non un servizio.
- **Scheduler**: APScheduler in-process con orari da `config/jobs.yaml`
  (timezone di mercato `America/New_York`, visualizzazione `Europe/Rome`).
  Due soli sweep intraday previsti dal disegno; nell'MVP sono un no-op
  documentato finché non esiste un provider intraday.

## Flusso giornaliero

| Orario ET | Job | Note |
|---|---|---|
| 05:45 | `ingest_eod` | barre EOD, corporate actions, filing (live); no-op in demo |
| 06:30 | `quality_checks` | barre mancanti, OHLC impossibili, stale, azioni non riconciliate |
| 08:30 | `premarket_snapshot` | gap/RVOL pre-market ritardato (con provider intraday) |
| 08:40 | `claim_enrichment` | discovery/dedup SOLO sui candidati |
| 09:10 | `ai_extraction` | solo se AI abilitata; output vincolato a schema |
| 16:15 | `ranking_eod` | feature complete, scoring deterministico, notifiche materiali |
| 16:45 | `daily_report` | report leggibile (ogni claim con source ID) |
| 17:15 | `retrospective_review` | outcome 1/3/5/10/20 sedute |
| 18:00 | `freeze_and_backup` | snapshot Parquet riproducibile |

Comportamento in errore (invarianti):
- fonte indisponibile → issue `stale`/`provider_not_configured`, mai valore 0;
- barra mancante → nessun segnale;
- corporate action non riconciliata → titolo bloccato;
- output AI non valido → scartato, mai nel report;
- DB parzialmente aggiornato → il ranking non viene pubblicato per quei titoli.

## Contratti degli adapter (anti lock-in)

`MarketDataAdapter`: `get_daily_bars`, `get_intraday_bars`,
`get_reference_data`, `get_corporate_actions`, `get_delisted`,
`get_news_metadata`. `DocumentSourceAdapter`: `fetch_documents`, `status()`.

Stati: `ok` | `non configurata` | `errore` | `stale`. Uno stub non configurato
solleva `NotConfiguredError`: il chiamante registra una issue e prosegue senza
inventare dati.

## Frontend

SvelteKit 2 + Svelte 5 (TypeScript), **adapter-static**: la SPA è un insieme di
file statici serviti da Caddy — nessun processo Node in produzione. Font
self-hosted (`@fontsource`), nessuna richiesta a host esterni (CSP `default-src
'self'`). Chiamate API con cookie di sessione `HttpOnly` + header
`X-CSRF-Token`.

## Scelte escluse e perché

| Escluso | Motivo |
|---|---|
| Kubernetes, microservizi | un VPS mono-utente non li giustifica |
| Redis/Celery/Kafka | APScheduler in-process basta per ~10 job/giorno |
| Vector DB | dedup con hash+SimHash+Jaccard è sufficiente e verificabile |
| Serverless | job lunghi, costi imprevedibili, lock-in |
| Modelli ML locali | Fase 3+: prima serve la validazione contro baseline |
| Monitoraggio continuo | il disegno prevede EOD + pre-market ritardato |

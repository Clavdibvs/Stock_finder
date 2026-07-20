# Modello dati

Convenzioni: timestamp UTC timezone-aware ovunque (visualizzazione
`Europe/Rome`); campi nullable = dato mancante esplicito (mai 0 implicito);
JSON portabile (PostgreSQL in produzione, SQLite nei test).

## Anagrafe

### `securities`
Identità stabile della società/strumento. `stable_id` (UUID) è l'identificatore
**separato dal ticker**: ticker change e redomiciliation non spezzano la storia.
Campi: `name`, `cik`, `sector`, `security_type` (`common_stock`|`index`),
`is_demo` (i dati dimostrativi sono sempre etichettati).

### `security_listings`
Storia dei listing: `ticker`, `exchange`, `status` (`active`|`delisted`),
`valid_from`/`valid_to`, `shares_outstanding`, `float_shares`,
`short_interest_shares` + `short_interest_date` (FINRA, bimensile; `NULL` =
sconosciuto). Un titolo delistato resta nel dataset (anti survivorship bias).

### `market_bars`
OHLCV per (`security_id`, `bar_date`, `session`, `provider`) univoci.
`session`: `regular` | `premarket` | `afterhours`. `vwap` opzionale,
`adjusted` flag, `retrieved_at` per audit.

### `corporate_actions`
`action_type` (`split`, `reverse_split`, `ticker_change`, `merger`,
`delisting`, …), `ratio`, `effective_date`, **`reconciled`**: finché è `false`
il titolo è bloccato e non produce segnali.

## Eventi e documenti

### `events`
Tassonomia chiusa (26 tipi, v. `app/constants.py`). `status`
(`pending`|`occurred`|`resolved_positive`|`resolved_negative`), `is_binary`,
`materiality`, `announced_at` vs `effective_at`, `classified_by`
(`rule`|`ai`|`manual`) + confidence del classificatore.

### `document_sources` (registro fonti)
`name`, `domain`, `default_source_level` (1–10), `license_status`
(`metadata_only`|`excerpt_allowed`|`full_allowed`|`unknown`),
`retention_policy`, `configured`, `enabled`, note.

### `documents`
Per ogni documento: `url_canonical` (normalizzato, senza tracking) e
`url_original`; `title`, `author`, `publisher`; **quattro timestamp separati**
`published_at`, `effective_at`, `first_seen_at`, `retrieved_at` +
`original_timezone`; `source_level` 1–10; `content_hash` (SHA-256 sul testo
normalizzato), `simhash` (64 bit); `excerpt` breve (mai l'articolo completo
protetto), `license_state`; `duplicate_family_id` (self-FK al documento radice)
e `is_duplicate`. **Una famiglia = una origine informativa.**

### `claims`
Soggetto/predicato/oggetto + `figure` (cifra testuale), `claim_date`, `status`
(`fatto`|`rumor`|`opinione`|`interpretazione`|`previsione`),
`confirmation_level` (miglior source level che lo supporta), `evidence_span`
(citazione testuale obbligatoria), `source_document_id`, `extracted_by`.

### `claim_relations`
`conferma` | `contraddice` | `cita` | `riscrive` | `deriva_da`
(claim → related_claim, con nota).

## Feature e score

### `feature_snapshots`
Snapshot **point-in-time immutabile** per (`security_id`, `snapshot_date`):
`asof_ts`, `features` JSON (null = mancante), `missing_fields`,
`is_candidate`, `candidate_reasons` (regole attivate con valori osservati e
soglie), `provider`, `pipeline_version`, `config_version`.

### `risk_scores`
Per (`security_id`, `score_date`): `risk_index` (nullable: non pubblicato se
non difendibile), `squeeze_hazard` + `squeeze_unknown`, `execution_hazard`,
`dilution_risk`, `confidence_grade` A–D, `state`, `gate_applied`, `summary`,
`main_contrary_evidence`, `invalidation_conditions`, `missing_data`,
`independent_origins`, `catalyst_type`, e versioning completo:
`scoring_version`, `config_hash`, `code_version`.

### `score_factors`
Explainability riga per riga: `component` (R/V/A/C/D/F/B), `name`,
`direction` (+1 alza, −1 riduce, 0 informativo), `value` (percentile o NULL),
`weight`, `missing`, `explanation`.

## Operatività

### `watchlist_items` — nota personale, `removed_at` soft-delete. Nessun trading.
### `notifications` — `rule` (condizione materiale), `dedup_key` univoca: mai due notifiche per lo stesso evento, mai notifiche per duplicati.
### `ingestion_runs` — ogni esecuzione job: stato, elementi, errori, `idempotency_key` = `job:data`.
### `data_quality_issues` — `issue_type` (missing_bar, stale_source, provider_not_configured, unreconciled_corporate_action, impossible_ohlc, ai_output_rejected, …), severità, risoluzione.
### `manual_overrides` — correzioni manuali: entità, campo, valore prima/dopo, motivo, autore.
### `retrospective_outcomes`
Per (`risk_score_id`, `horizon_days` ∈ {1,3,5,10,20}): `reference_price` (P0 =
apertura/VWAP della seduta successiva al segnale), `dd_intraday`
(min Low/P0−1), `dd_close`, `ret_close`, `ret_vs_benchmark`, `ret_vs_sector`,
`max_adverse_up` (massimo rialzo contrario alla tesi), flag `hit_minus10/20/30/40`,
`complete` (finestra chiusa). Calcolati **solo dopo** la chiusura della finestra.

### `audit_logs`
Append-only con catena di hash: ogni riga incorpora `prev_hash`; `verify_chain`
rileva qualsiasi manomissione. Nessun endpoint di modifica/cancellazione.

## Accesso e AI

### `users` — un solo admin; `failed_attempts`, `locked_until` per il lockout.
### `auth_sessions` — si salva solo l'hash SHA-256 del token; `csrf_token`, scadenza, revoca.
### `app_settings` — chiave/valore JSON per stato applicativo (es. marcatore seed).
### `ai_invocations` — ogni chiamata AI: provider, modello, `prompt_hash`, `prompt_version`, token, `cost_eur`, `status` (`ok`|`rejected_schema`|`rejected_evidence`|`error`), output.

## Migrazioni

Alembic (`backend/alembic/`). La revisione iniziale crea le 23 tabelle.
Nei test lo schema è creato da `Base.metadata` su SQLite in-memory.

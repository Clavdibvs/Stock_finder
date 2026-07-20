# Drawdown Radar

Sistema **privato, personale, mono-utente e non commerciale** di early warning:
individua ogni giorno titoli statunitensi che, dopo un'accelerazione anomala di
prezzo, volume o attenzione, presentano un rischio relativo elevato di forte
correzione nei successivi 1–20 giorni.

> **Non è consulenza finanziaria.** Non promette rendimenti, non prevede crolli
> con certezza. Il Risk Index è un **indice ordinale 0–100, non una probabilità**.
> Un rischio elevato di drawdown **non** implica che il titolo sia shortabile:
> eventi binari e squeeze possono rendere estremamente pericolosa qualsiasi
> operazione. **Nessuna funzione esegue ordini o si collega operativamente a broker.**

## Cosa fa

1. **Candidate generator deterministico** — regole di accelerazione (rendimento,
   gap, robust-z) + conferma (RVOL, turnover, attenzione, evento materiale),
   con soglie in configurazione versionata.
2. **Ricostruzione del motivo del movimento** — eventi classificati con
   tassonomia chiusa, documenti con timestamp separati (`published_at`,
   `first_seen_at`), deduplicazione (URL canonico, hash, SimHash): cento
   riscritture della stessa notizia contano come **una** origine informativa.
3. **Claim graph** — fatti, rumor, opinioni, interpretazioni e previsioni con
   evidence span e relazioni (`conferma`, `contraddice`, `cita`, `riscrive`,
   `deriva_da`). Un rumor resta rumor finché una fonte di livello 1–2 non lo
   conferma.
4. **Risk Index deterministico** — `0.20R + 0.15V + 0.10A + 0.20C + 0.15D +
   0.10F + 0.10B`, pesi versionati; stesso input e versione ⇒ stesso score.
5. **Gate di sicurezza** che prevalgono sul punteggio, in precedenza:
   `EVENTO BINARIO — EVITARE` → `POSSIBILE SQUEEZE — NON ADATTO ALLO SHORT` →
   `RISCHIO NON QUANTIFICABILE` → `DATI INSUFFICIENTI` → poi
   `RISCHIO DI CORREZIONE ELEVATO` / `MONITORARE` dal punteggio.
6. **Classifica giornaliera spiegabile** (max 20 titoli), pagina titolo con
   timeline, claim, controevidenze, dati mancanti e condizioni di invalidazione.
7. **Retrospective review** — outcome a 1/3/5/10/20 sedute con etichetta
   primaria `drawdown intraday ≤ −20% entro 10 sedute` dal prezzo eseguibile P0.
8. **Audit trail append-only** (catena di hash) e correzioni manuali tracciate.
9. **AI opzionale e controllata** — disabilitata di default; quando attiva può
   solo classificare/estrarre con JSON Schema ed evidence span obbligatorio,
   con tetto mensile di spesa. L'app funziona interamente senza.

## Avvio rapido (modalità demo, un solo comando)

Richiede Docker. Nessuna API key necessaria.

```bash
./scripts/bootstrap.sh
```

Lo script genera `.env` con segreti casuali (stampa la password admin una sola
volta), builda e avvia lo stack. Interfaccia su `http://localhost/`.

Al primo avvio in modalità demo viene caricato un **dataset dimostrativo
etichettato** (12 titoli fittizi o ricostruiti, tra cui un caso ispirato ad
ATAI): niente è presentato come dato in tempo reale. Il dataset copre tutti gli
stati: rischio elevato, evento binario, squeeze, non quantificabile, dati
insufficienti, monitorare, titolo bloccato da corporate action non riconciliata
e titolo delistato con outcome storico.

## Sviluppo locale (senza Docker)

```bash
# backend (Python 3.12)
cd backend && python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd .. && make dev-api          # API su :8000 con SQLite + demo seed

# frontend (Node 20+), in un altro terminale
cd frontend && npm install
cd .. && make dev-web          # SPA su :5173 con proxy verso :8000

# test (103 test)
make test
```

Login sviluppo: `admin` / `demo-password`.

## Modalità live (operativa)

La demo non chiama mai la rete. La modalità live funziona con **due sole fonti
gratuite** (Alpaca free + SEC) e resta estendibile ai provider a pagamento.

**Passo 1 — chiavi (una volta sola, ~10 minuti):**

1. Crea un account gratuito su [alpaca.markets](https://alpaca.markets) (basta
   il paper account; l'app usa SOLO gli endpoint di market data — mai ordini),
   genera le chiavi API dalla dashboard e mettile in `.env`:
   `DDR_ALPACA_KEY_ID` e `DDR_ALPACA_SECRET_KEY`.
2. Configura la SEC (gratuita, serve solo identificarsi per la fair access
   policy): `DDR_SEC_EDGAR_ENABLED=true` e
   `DDR_SEC_USER_AGENT="Nome Cognome email@example.com"`.
3. In `.env`: `DDR_APP_MODE=live`, `DDR_MARKET_DATA_PROVIDER=alpaca`,
   `DDR_NASDAQ_HALTS_ENABLED=true` (feed halt ufficiale, gratuito).
4. Riavvia: `docker compose up -d --build`.

**Passo 2 — universo (due modalità):**

- **Auto-discovery (consigliata)** — `DDR_UNIVERSE_MODE=auto` (+ opzionale
  `DDR_CRYPTO_ENABLED=true`): l'intero listino USA (~10.000 azioni ordinarie,
  ETF/warrant/preferred esclusi) viene scoperto e sincronizzato ogni giorno;
  nessun ticker da inserire. L'anagrafica SEC e le news si arricchiscono solo
  sui candidati del giorno. Primo avvio: ▶ `universe_sync` poi
  ▶ `backfill_history` (~130 giorni full market, alcuni minuti) poi
  ▶ `ranking_eod` da Data quality.
- **Esplicita** — `DDR_UNIVERSE_MODE=explicit`: solo i ticker inseriti in
  Impostazioni → Universo (max 500), con backfill a 400 giorni.

Con `DDR_NEWS_DISCOVERY_PROVIDER=brave` + chiave
([brave.com/search/api](https://brave.com/search/api/), credito gratuito) i
candidati vengono arricchiti con metadati news (attenzione, origini
indipendenti, rumor come claim non confermati). I social (Reddit/X/Stocktwits)
restano esclusi: i loro ToS non consentono scraping automatico.

**Cosa fa ogni giorno in live:** barre EOD (bulk, rettificate), filing EDGAR
con classificazione deterministica (S-1/S-3/424B → diluizione, 8-K → evento
materiale, Form 4/144 → attività insider), halt Nasdaq, quality check,
ranking, retrospettive, freeze Parquet.

**Limiti dichiarati del piano gratuito** (mai aggirati con dati fittizi):
feed IEX parziale (volumi sottostimati, niente pre-market), niente float →
confidence massima B, niente short interest → squeeze sempre «sconosciuto»,
niente delisted (per il backtest storico serve un dataset point-in-time).
L'upgrade a EODHD/Tiingo passa dagli stub documentati **dopo** la verifica
scritta della licenza — vedi [SOURCE_REGISTRY.md](SOURCE_REGISTRY.md).

## Deploy su VPS europeo

Vedi [ARCHITECTURE.md](ARCHITECTURE.md) e [SECURITY.md](SECURITY.md). In sintesi:

```bash
# sul VPS (Debian/Ubuntu con Docker)
git clone <repo> /opt/ddr && cd /opt/ddr
cp .env.example .env   # compilare: dominio o Tailscale, password, ecc.
./scripts/bootstrap.sh
```

- Con `DDR_DOMAIN=radar.example.org` Caddy ottiene il TLS da Let's Encrypt.
- Con `DDR_DOMAIN=:80` l'istanza resta HTTP locale: usarla **solo** dietro
  Tailscale/WireGuard o access proxy (e in quel caso si può impostare
  `DDR_AUTH_DISABLED=true`).
- Backup cifrato: `scripts/backup.sh` (Restic); restore provato:
  `scripts/restore.sh`. Schedulare il backup via cron.

## Cosa è reale, cosa è demo, cosa richiede licenza

| Componente | Stato |
|---|---|
| Pipeline completa (candidati → claim graph → scoring → gate → retrospettiva) | **Reale**, esercitata anche dal seed demo |
| Dataset demo (12 titoli) | **Fittizio/ricostruito**, chiaramente etichettato |
| SEC EDGAR adapter | **Reale e gratuito** (richiede solo User-Agent) |
| FDA, ClinicalTrials, Nasdaq halt, FINRA, IR RSS, Brave discovery | **Stub documentati** (fonti gratuite; integrazione da completare) |
| Market data commerciali (EODHD, Tiingo, Alpaca) | **Stub documentati**; richiedono API key e verifica scritta della licenza |
| AI (Claude) | **Opzionale**; richiede API key e budget; disabilitata di default |
| Borrow/locate/short interest live | **Non disponibile nell'MVP**: lo squeeze hazard resta «sconosciuto» quando mancano i dati |
| Auto-discovery full-market (~10k azioni) + crypto | **Reale** via Alpaca assets; crypto con confidence max C (nessun filing/cap) |
| Brave News discovery | **Reale, key-gated**: metadati e link sui candidati, mai contenuti integrali |

## Documentazione

- [ARCHITECTURE.md](ARCHITECTURE.md) — architettura, componenti, flussi
- [DATA_MODEL.md](DATA_MODEL.md) — entità e vincoli
- [SCORING.md](SCORING.md) — formula, componenti, gate, confidence
- [SOURCE_REGISTRY.md](SOURCE_REGISTRY.md) — fonti, livelli, licenze, hard gate
- [SECURITY.md](SECURITY.md) — modello di minaccia, controlli, backup/restore
- [VALIDATION.md](VALIDATION.md) — etichette, baseline, export, anti-leakage
- [DECISIONS.md](DECISIONS.md) — assunzioni, decisioni prese e aperte

## Struttura del monorepo

```
backend/          FastAPI + SQLAlchemy + Alembic + scheduler + test
  app/adapters/   contratti provider + demo + SEC EDGAR + stub
  app/candidates/ feature engine + candidate generator
  app/claims/     dedup (URL/hash/SimHash) + claim graph
  app/scoring/    Risk Index, gate, confidence, pipeline
  app/validation/ retrospective, baseline, export DuckDB/Parquet
  app/seed/       dataset demo deterministico
  config/         soglie e pesi versionati (YAML)
frontend/         SvelteKit (SPA statica, dark mode)
deploy/           Caddyfile + Dockerfile web
scripts/          bootstrap, backup, restore
docker-compose.yml
```

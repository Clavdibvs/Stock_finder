# Decisioni e assunzioni

## Decisioni prese (con motivazione)

| # | Decisione | Motivazione |
|---|---|---|
| D1 | **SvelteKit + adapter-static** (SPA) invece di Next.js | zero processi Node in produzione: Caddy serve file statici; stack più piccolo e leggibile per un'app mono-utente |
| D2 | **APScheduler in-process** invece di cron di sistema | un solo container, job visibili/riesequibili dalla UI; gli orari restano in `config/jobs.yaml`; su VPS si può comunque affiancare cron per il backup |
| D3 | **Sessioni opache in DB** (hash del token) invece di JWT | revoca immediata al logout, nessun segreto di firma da ruotare, dump del DB non riutilizzabile |
| D4 | **Saturazioni fisse + `combine=0.6·max+0.4·media`** come proxy dei percentili robusti cross-section | con un universo demo di 12 titoli i percentili giornalieri sarebbero degeneri; il contratto (componenti 0–100) resta invariato quando si passerà ai percentili sull'universo live |
| D5 | Attenzione = **tutti** i documenti del giorno (copie incluse); conferma = **solo origini indipendenti** | l'attenzione misura "quante pagine ne parlano", la conferma misura l'informazione: sono grandezze diverse |
| D6 | Squeeze `sconosciuto` senza short interest ufficiale (il solo volume/float non basta) | FINRA è bimensile e il borrow non ha fonte low-cost: meglio dichiarare l'ignoranza che quantificarla male |
| D7 | Short interest su `security_listings` (point-in-time semplice) | granularità FINRA bimensile; una tabella dedicata sarebbe prematura |
| D8 | Migrazione iniziale Alembic autogenerata dai metadata | schema garantito coerente col codice; le successive saranno incrementali |
| D9 | SQLite consentito SOLO in sviluppo/test | i test girano ovunque in <5 s; produzione è PostgreSQL via compose |
| D10 | Il seed demo **esegue la pipeline reale** sui dati fittizi | la demo non è un mock: dashboard, gate, dedup e retrospettive escono dal codice di produzione |
| D11 | Caso ATAI ricostruito con ticker reale ma etichetta "demo ricostruito" | richiesto dal disegno; ogni schermata mostra il banner demo e `is_demo` |
| D12 | Ordinamento dashboard: RISCHIO ELEVATO prima dei gate | la lista è una classifica di rischio informativo; i gate restano visivamente dominanti tramite badge |
| D13 | CSP `default-src 'self'` + font self-hosted | nessuna dipendenza runtime esterna, privacy dell'istanza |
| D14 | Notifiche in-app con `dedup_key` univoca; canali esterni come stub | email/Telegram richiedono segreti e configurazione personale; la logica delle condizioni materiali è già completa |
| D15 | AI provider unico implementato: Anthropic (import lazy) | provider sostituibile via interfaccia; il pacchetto `anthropic` non è una dipendenza obbligatoria |
| D16 | **Alpaca free come primo provider live** | costo zero, API ufficiale, adatto al POC (ricerca D.5); IEX parziale e senza float/delisted: limiti dichiarati in UI/README, upgrade EODHD/Tiingo dietro hard gate licenze |
| D17 | Shares outstanding da SEC XBRL (`companyconcept` dei) | fonte ufficiale gratuita; market cap reale senza vendor; il float resta mancante (mai stimato) |
| D18 | Float mancante ⇒ confidence max **B** (non più C) se mercato+cap completi | senza fonte float commerciale il grade A resta irraggiungibile ma «RISCHIO ELEVATO» (che richiede A/B) torna possibile; deviazione documentata da E.8 |
| D19 | Barre Alpaca `adjustment=all`: split riconciliati alla fonte | l'adapter non registra corporate action da riconciliare; il blocco per azioni non riconciliate resta attivo per quelle inserite manualmente |
| D20 | Universo esplicito (max 500) **oppure** auto-discovery full-market (`DDR_UNIVERSE_MODE=auto`) | il bulk bars di Alpaca free regge l'intero listino (~10k titoli, ~130 giorni); l'anagrafica SEC resta lazy sui soli candidati per la fair access |
| D21 | Auto-discovery: filtri euristici per ETF/fondi/warrant/unit/preferred (exchange NYSE/NASDAQ/AMEX, regex sul nome, ticker senza `./-`) | imperfetti ma dichiarati; i falsi inclusi finiscono comunque nell'universo ombra via cap/liquidità |
| D22 | Crypto: screening prezzo/volume/attenzione con `security_type=crypto` | nessun filing, market cap ufficiale né claim graph ⇒ confidence max C, mai «RISCHIO ELEVATO», execution hazard non modellato (sconosciuto), gate sub-$1 non applicato |
| D23 | Score e snapshot SOLO per i candidati (accelerazione+conferma) | con 10k titoli lo shadow universe non deve inondare ranking e storage; i non-candidati non producono righe |
| D25 | Repo su GitHub (Clavdibvs/Stock_finder) con **CI Actions** (pytest+ruff+build); runtime su Docker locale/VPS, **NON su Vercel** | l'app è un processo persistente (scheduler APScheduler, job >5 min, PostgreSQL da ~500k righe): il modello serverless la spezzerebbe; la ricerca G.1 e il mandato originale prescrivono il VPS. Le env restano necessarie ovunque (segreti/DB) |
| D26 | Auto-miglioramento = **misurazione automatica + drift alert**, mai auto-tuning dei pesi | job settimanale validation_report (precision@5/@10 vs 9 baseline su finestre chiuse, storico 52 settimane, notifica se lift<0); la ricalibrazione resta manuale ai phase gate (pre-registrazione, F.9) |
| D24 | News discovery: **GDELT default** (gratuito, senza chiave, fair use 1 req/5s), Brave opzionale a pagamento | Brave non ha più un piano gratuito; GDELT è open e già indicato dalla ricerca (D.6); Google News RSS vietata da robots.txt e Yahoo RSS dismesso (verificati); Reddit/X/Stocktwits restano esclusi (ToS) |

## Assunzioni

- A1: l'utente opera da fuso `Europe/Rome`; i mercati USA seguono `America/New_York` (mai offset fissi).
- A2: in demo l'ultima seduta utile è l'ultimo giorno feriale; il calendario festività USA completo arriverà con il provider live (le date demo sono generate, non di mercato).
- A3: budget VPS ~€8–10/mese (CX33-class) sufficiente: lo stack usa <1 GB RAM.
- A4: il proxy dello spread (prezzo + ADV) è accettabile finché non esistono dati bid/ask.
- A5: la componente F (mismatch fondamentale) parte come proxy "rally senza catalizzatore fondamentale"; i fondamentali veri (ricavi, cash, EV) arrivano col provider.

## Decisioni aperte (richiedono dati o test)

- O1: etichetta primaria `−20%/10 sedute` contro le alternative (base rate reale ignoto).
- O2: soglie candidate generator e pesi del Risk Index: da contestare in walk-forward.
- O3: EODHD vs Tiingo vs Alpaca: bake-off di due settimane + risposte scritte sulle licenze (hard gate).
- O4: valore incrementale del pre-market rispetto al solo EOD.
- O5: percentili cross-section vs saturazioni fisse (D4) sull'universo reale.
- O6: modello generale vs modelli per tipo di evento (servono eventi sufficienti).
- O7: fonte per float/short interest point-in-time affidabile.
- O8: valore dell'LLM rispetto a regole di parsing sui documenti EDGAR.
- O9: canale di notifica personale (email vs Telegram) e suoi segreti.
- O10: se e quando pubblicare probabilità calibrate (mai prima della Fase 3).

## Non-goal permanenti

Esecuzione ordini, collegamenti broker, raccomandazioni short, multi-utente,
funzioni social, pagamenti, scraping in violazione di ToS/robots/paywall.

# Registro delle fonti

Il registro operativo vive nella tabella `document_sources` (visibile nella
schermata «Fonti e claim»); questo documento è la policy.

## Gerarchia dei livelli (affidabilità del produttore ≠ conferma del claim)

| Livello | Tipo | Uso |
|---:|---|---|
| 1 | Filing, autorità, documento giudiziario/regolatorio | Evidenza primaria |
| 2 | Dichiarazione diretta di società o autorità | Primaria, da confrontare col documento |
| 3 | Agenzia con reporting e fonti proprie | Origine giornalistica |
| 4 | Articolo che cita e collega una fonte primaria | Conferma derivata |
| 5 | Analisi finanziaria o scientifica | Interpretazione |
| 6 | Rumor attribuito a fonti anonime | Claim non confermato |
| 7 | Post di utente identificabile | Segnale di attenzione |
| 8 | Opinione non verificata | Contesto, non evidenza |
| 9 | Contenuto promozionale/sponsorizzato | Possibile rischio |
| 10 | Riscrittura automatica o duplicato | **Non conta mai come conferma** |

Una testata credibile (liv. 3) può pubblicare un rumor non confermato: il claim
resta `rumor` finché una fonte di livello 1–2 non lo conferma. Solo documenti
non-duplicati di livello 1–2 promuovono un claim a `fatto`.

## Fonti nell'MVP

| Fonte | Stato nel codice | Costo | Licenza/conservazione | Note |
|---|---|---|---|---|
| **SEC EDGAR** | **adapter reale** (`sec_edgar` + `edgar_ingest`) | gratuita | documenti federali pubblici; conservabili | fair access: User-Agent identificabile obbligatorio, ≤10 req/s (noi: ≤5); classificazione eventi deterministica dai form |
| **SEC company_tickers + XBRL** | **adapter reale** (`sec_universe`) | gratuita | pubblica | universo ticker→CIK→nome + shares outstanding (dei:EntityCommonStockSharesOutstanding); il float NON esiste qui: resta mancante |
| Investor relations / RSS | stub (`ir_rss`) | gratuita | URL, metadata, estratti; copie integrali solo se consentito | feed per-società da aggiungere all'allowlist |
| FDA / openFDA | stub (`openfda`) | gratuita (con chiave: 240 req/min) | pubblica; mantenere provenienza e data | non tutti i dati openFDA sono validati |
| ClinicalTrials.gov API v2 | stub (`clinicaltrials`) | gratuita | pubblica | conservare sia submission sia posting date |
| Nasdaq Trade Halt RSS | **adapter reale** (`nasdaq_halts`) | gratuita | feed pubblico | eventi `halt` idempotenti; mai interrogato più spesso dei job |
| FINRA short interest | stub (`finra`) | gratuita | pubblica | solo bimensile; il daily short volume NON è short interest e non va convertito in "percentuale short" |
| **GDELT DOC 2.0** | **adapter reale** (`gdelt_news`, default) | gratuita, senza chiave | progetto open: solo metadati/titoli | fair use 1 req/5s (throttle interno); rumore alto ⇒ dedup obbligatoria (attiva); discovery SOLO sui candidati |
| Brave Search API | adapter reale opzionale (`brave_news`) | richiede piano a pagamento | solo discovery: metadati/link | alternativa a GDELT se si vuole una chiave commerciale |
| Google News RSS | **esclusa** | — | vietata dal robots.txt di news.google.com (verificato 17/07/2026) | — |
| Yahoo Finance RSS | **esclusa** | — | feed dismesso (404, verificato 17/07/2026) | — |

## Provider di mercato commerciali (stub, non attivi)

| Provider | Stub | Valutazione dalla ricerca |
|---|---|---|
| EODHD | `eodhd_stub` | candidato principale al bake-off (EOD $19,99–29,99/mese); retention dichiarata limitata alla durata dell'abbonamento |
| Tiingo | `tiingo_stub` | secondo candidato (~$30/mese); IEX ≠ consolidato SIP |
| **Alpaca** | **adapter reale** (`alpaca`) | provider live di default (free, IEX): barre EOD rettificate in bulk, metadati asset. SOLO market data, mai endpoint di trading. Limiti: volumi IEX parziali, no float/delisted/pre-market |
| Massive (ex Polygon) | — | **escluso** senza autorizzazione scritta (termini su derived/non-display) |
| Norgate | — | candidato per backtest storico point-in-time (Fase 0/3) |

### Hard gate prima di qualsiasi contratto

Nessun provider si attiva senza risposta **scritta** su:

1. conservazione storica dei dati dopo la cessazione;
2. calcolo e conservazione di feature derivate;
3. backtest personale;
4. backup;
5. cancellazione alla cessazione;
6. uso non-display.

## Fonti escluse dall'MVP

Reddit/X/Stocktwits (API instabili o licenze restrittive: solo consultazione
manuale), Google Trends (alpha), YouTube (quota), scraping di Yahoo/Investing
(ToS), Discord/Telegram (privacy/consenso), opzioni/OPRA (costo), borrow/locate
(nessuna fonte low-cost affidabile: lo squeeze resta `sconosciuto`).

## Regole di ingestion

- **Allowlist di domini** (`DDR_INGEST_ALLOWED_DOMAINS`): fuori lista = rifiuto.
- Solo HTTPS; blocco IP privati/loopback (anti-SSRF); redirect rivalidati.
- Timeout 20 s, dimensione max 5 MB, content-type validato.
- Niente aggiramento di paywall, autenticazioni o robots.txt.
- Dei contenuti protetti si conservano: URL, titolo, autore, timestamp, hash,
  estratto breve necessario a dimostrare il claim, classificazioni, feature.
  **Mai la copia integrale automatica.**
- Retention configurabile (`DDR_RETENTION_*`); i contenuti da community hanno
  retention breve e cancellazione su richiesta.

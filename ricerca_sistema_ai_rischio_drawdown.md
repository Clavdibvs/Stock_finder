# Ricerca decisionale — sistema AI di early warning per rischio di drawdown

**Data di verifica delle fonti e dei prezzi: 16 luglio 2026.** I dati ATAI relativi al pre-market sono fotografie puntuali di una sessione ancora in evoluzione e non prezzi definitivi.

---

## A. Executive summary

### Problema realisticamente risolvibile

Il prodotto non dovrebbe cercare di “prevedere il prossimo crollo” né generare raccomandazioni short. Il problema risolvibile è più ristretto:

> **Dato un titolo che ha già manifestato un’accelerazione anomala di prezzo, volume o attenzione, stimare e ordinare il rischio condizionale che nei successivi 1–20 giorni subisca un drawdown materialmente superiore alla normale volatilità del titolo e del settore.**

La letteratura fornisce un razionale economico: gli investitori retail tendono a comprare titoli che attirano improvvisamente attenzione attraverso rendimenti estremi, volumi e notizie; l’attenzione di ricerca può accompagnare rialzi nel breve e successive inversioni; sui social, disaccordo e concentrazione della narrativa aggiungono informazione che il solo sentiment medio non cattura. Questo non prova che lo specifico sistema proposto funzionerà: il valore incrementale deve essere dimostrato fuori campione. Anche il rischio di squeeze va separato dal rischio di correzione, perché gli squeeze sono particolarmente rilevanti proprio nei titoli più difficili e costosi da prendere in prestito. ([Fonte accademica](https://faculty.haas.berkeley.edu/odean/Papers%20current%20versions/AllThatGlitters_RFS_2008.pdf))

### Soluzione consigliata

La soluzione migliore è un sistema **ibrido e interpretabile**:

1. **Candidate generator deterministico** basato su prezzo, volume, volatilità e turnover.
2. **Motore di intelligence** che ricostruisce evento, fonte originaria, conferme, duplicazioni e contraddizioni.
3. **Risk Index ordinale 0–100**, non presentato come probabilità.
4. **Gate di sicurezza separati** per evento binario, squeeze, illiquidità e dati insufficienti.
5. **LLM limitato a estrazione e spiegazione**; nessun numero di mercato o score viene deciso liberamente dal modello.
6. **Validazione point-in-time** contro baseline semplici, prima di costruire una dashboard complessa.

### MVP minimo utile

Il più piccolo MVP con utilità concreta comprende:

- azioni ordinarie quotate negli Stati Uniti;
- dati giornalieri e un aggiornamento pre-market ritardato;
- SEC, investor relations, FDA, ClinicalTrials.gov, sospensioni Nasdaq e FINRA;
- un unico provider di mercato sostituibile;
- screening deterministico dell’intero universo;
- approfondimento solo sui primi 10–30 candidati;
- report giornaliero con classifica, stato, spiegazione e fonti;
- nessun social scraping, nessun dato opzioni, nessun borrow cost e nessun trading automatico.

### Architettura raccomandata

**VPS europeo singolo con Docker Compose**, PostgreSQL, DuckDB/Parquet, FastAPI, frontend leggero, scheduler di sistema e backup S3-compatible. Non servono nell’MVP Kubernetes, vector database, Redis, una piattaforma multi-agent o un modello locale.

### Costo indicativo

Un budget operativo realistico è **circa 55–85 euro equivalenti al mese**, dipendente da IVA, cambio, volume AI e fornitore dati:

| Componente | Ordine di costo |
|---|---:|
| VPS europeo | €8,49/mese, IVA e IPv4 esclusi |
| Object storage opzionale | circa €6,49/mese |
| Dati di mercato | circa $30/mese |
| Ricerca web autorizzata | $0–5/mese iniziali |
| API AI con tetto rigido | €15–30/mese |
| Posta/notifiche/monitoraggio | prossimo a zero nell’uso personale |

Hetzner indica, dopo l’aggiornamento prezzi di giugno 2026, €8,49 per CX33 e circa €6,49 come base per Object Storage; l’alternativa Supabase Pro parte da $25 e Vercel Hobby è destinato a progetti personali non commerciali. ([Hetzner](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/))

### Limiti principali

- La licenza di **conservazione e uso derivato dei dati di mercato** è il maggiore rischio progettuale.
- Il vero short interest FINRA è pubblicato solo due volte al mese; il daily short volume non è short interest.
- Il borrow cost richiede normalmente una fonte commerciale o il proprio broker.
- La ricostruzione automatica di Reddit, X e Stocktwits non è oggi sufficientemente stabile e conforme per essere un requisito dell’MVP.
- Eventi come acquisizioni, trial e decisioni FDA possono produrre ulteriori gap rialzisti: uno score di correzione elevato non rende automaticamente il titolo shortabile.

---

## B. Verifica del caso ATAI

### B.1 Timeline essenziale

| Data | Evento verificabile | Interpretazione per il sistema |
|---|---|---|
| 1 luglio 2025 | Beckley Psytech comunicò risultati positivi della Phase 2b di BPL-003 in 193 pazienti, dichiarando raggiunti l’endpoint primario e tutti i principali secondari. | Catalizzatore clinico primario, non semplice rumor; richiede lettura di sicurezza, dimensione dell’effetto e comparatore, non solo sentiment. ([Investor Relations](https://ir.ataibeckley.com/news-releases/news-release-details/atai-life-sciences-and-beckley-psytech-announce-positive-topline)) |
| 5 novembre 2025 | Completata la combinazione strategica tra atai e Beckley Psytech, dopo approvazione degli azionisti. | Cambiamento strutturale della società e della pipeline; le serie storiche e il confronto fondamentale devono tenere conto dell’operazione. ([Investor Relations](https://ir.ataibeckley.com/news-releases/news-release-details/atai-life-sciences-and-beckley-psytech-announce-successful/)) |
| 30 dicembre 2025 | Completata la redomiciliazione nel Delaware con scambio uno-a-uno delle azioni. | Evento societario da normalizzare nella master security table; non è un catalizzatore economico autonomo. ([Investor Relations](https://ir.ataibeckley.com/news-releases/news-release-details/ataibeckley-completes-redomiciliation-united-states)) |
| 26 febbraio 2026 | EMP-01 Phase 2a: 71 pazienti; endpoint primario di sicurezza raggiunto. Un risultato esplorativo riportava p=0,036 a una coda e lo studio non era dimensionato per dimostrare efficacia statistica. | Esempio di possibile differenza tra headline positiva e forza probatoria del contenuto. ([Investor Relations](https://ir.ataibeckley.com/news-releases/news-release-details/ataibeckley-announces-positive-topline-results-exploratory-phase)) |
| Q1 2026 | Cash e mezzi equivalenti pari a $209,9 milioni al 31 marzo; la società dichiarava runway attesa fino al 2029, includendo le letture Phase 3 previste di BPL-003. | Controevidenza rispetto a una tesi di diluizione imminente; resta comunque necessario analizzare strumenti, shelf e fabbisogno prospettico. ([Investor Relations](https://ir.ataibeckley.com/news-releases/news-release-details/ataibeckley-reports-first-quarter-2026-financial-results-and)) |
| 25 giugno 2026 | Annunciata l’inclusione negli indici Russell. | Possibile componente meccanica di domanda e volume, distinta da un miglioramento fondamentale. ([Investor Relations](https://ir.ataibeckley.com/news-releases/news-release-details/ataibeckley-join-russell-indexes-expanding-visibility-across-us)) |
| 6 luglio 2026 | Ultimo paziente dosato nella Phase 2 VLS-01, 156 partecipanti; topline attesa nel Q4 2026. | Milestone operativa, non risultato di efficacia. Il sistema deve impedire che “ultimo paziente dosato” venga classificato come “trial positivo”. ([Investor Relations](https://ir.ataibeckley.com/news-releases/news-release-details/ataibeckley-doses-last-patient-vls-01-phase-2b-trd-study-plans)) |
| 15 luglio 2026 | Reuters riferì che Eli Lilly era in trattative per acquistare AtaiBeckley, citando persone informate; un annuncio avrebbe potuto arrivare entro la settimana. Le società non avevano fornito conferma immediata. | Fonte giornalistica credibile, ma claim centrale non confermato e basato su fonti anonime: evento M&A binario. ([Reuters ripubblicato da WSAU](https://wsau.com/2026/07/15/eli-lilly-nears-deal-to-buy-psychedelic-drugmaker-ataibeckley-bloomberg-news-reports/)) |
| 15–16 luglio 2026 | Il 15 luglio ATAI chiuse a $5,36, -5,47%, con 10,87 milioni di azioni scambiate contro una media a 65 giorni di 7,74 milioni. Alle 06:12 ET del 16 luglio il pre-market WSJ indicava $8,669, +61,74%, con 4,12 milioni di azioni; nell’after-hours era stato osservato un massimo pubblico di circa $9,01. | Segnale estremo di prezzo e volume, ma non automaticamente segnale short. ([WSJ Market Data](https://www.wsj.com/market-data/quotes/US/XNAS/ATAI)) |

### B.2 Stato delle conferme ufficiali

Al controllo del 16 luglio, la pagina dei filing mostrava come documenti più recenti un Form 4 del 9 luglio e un Form 144 del 7 luglio; non risultava ancora un nuovo 8-K relativo all’indiscrezione M&A. Anche le pagine investor relations consultate non presentavano un comunicato di accordo. Questo prova soltanto l’assenza di una conferma pubblica nei canali controllati in quel momento: **non è una smentita e non dimostra che i colloqui non esistano**. ([SEC filings ATAI](https://ir.ataibeckley.com/sec-filings/sec-filings-ataibeckleyinc))

Form 4 e Form 144 vanno interpretati con precisione: il primo registra variazioni nella proprietà beneficiaria degli insider; il secondo riguarda vendite proposte ai sensi della Rule 144. Nessuno dei due, isolatamente, conferma o smentisce una transazione societaria. ([SEC Form 4](https://www.sec.gov/files/form4.pdf))

### B.3 Propagazione della narrativa

Dopo il report originale, varie pagine finanziarie e community hanno riscritto la stessa indiscrezione. Stocktwits mostrava ATAI tra i titoli pre-market più in tendenza, ma le metriche pubbliche di sentiment e messaggi non erano disponibili in forma riproducibile; Benzinga e Stocktwits News riportavano essenzialmente la medesima origine informativa. Queste copie devono essere rappresentate come **un’unica famiglia di claim**, non come conferme indipendenti. ([Stocktwits ATAI](https://stocktwits.com/symbol/ATAI/fundamentals))

Non è stato possibile ricostruire da pagine pubbliche indicizzabili un campione affidabile e completo di post contemporanei su Reddit e X, con timestamp e autori sufficienti per un’analisi quantitativa. Per il caso ATAI, quindi, la parte social rimane incompleta e non va retrospettivamente inventata.

### B.4 Cosa avrebbe rilevato il sistema

Il candidate generator avrebbe identificato:

- gap pre-market superiore al 60%;
- volume pre-market di milioni di azioni;
- superamento del massimo precedente a 52 settimane;
- accelerazione improvvisa della copertura;
- molte riscritture riconducibili a un’unica origine;
- assenza, al momento del controllo, di conferma societaria o filing M&A;
- forte dipendenza del prezzo da un singolo evento binario.

### B.5 Cosa avrebbe sconsigliato uno short

- L’origine non era un account anonimo o un forum, ma un report Reuters.
- Una conferma dell’acquisizione avrebbe potuto produrre un ulteriore gap o un prezzo d’offerta superiore.
- La società disponeva di una pipeline clinica materiale e dichiarava runway fino al 2029.
- Il borrow cost, la disponibilità di titoli da prendere in prestito e lo short interest aggiornato non erano stati verificati.
- Un titolo in movimento del 50–60% fuori orario può presentare spread, halt, locate revocato e rischio di perdita non limitata.
- La mancanza di 8-K non equivale a smentita.

### Classificazione corretta di ATAI

**Stato consigliato:** `EVENTO BINARIO — EVITARE`

**Risk Index:** non pubblicare ancora un valore numerico, perché mancano almeno borrow, float point-in-time, spread consolidato, storia completa della propagazione e un modello già validato.

**Squeeze hazard:** `NON QUANTIFICABILE / POTENZIALMENTE ELEVATO`

**Tesi:** il caso dimostra l’utilità di separare:

- reputazione dell’editore;
- conferma del claim;
- numero di pagine che lo ripetono;
- opportunità di monitoraggio;
- effettiva shortabilità.

---

## C. Definizione del target

### C.1 Fenomeno da prevedere

Il sistema deve stimare:

> **La probabilità ordinale di un drawdown rilevante dopo un evento di accelerazione, condizionata alle informazioni effettivamente disponibili al momento del segnale.**

Non deve stimare il “fair value” generale del titolo. Un titolo può essere sopravvalutato per mesi senza correggere; un titolo può correggere e tuttavia essere impossibile o pericoloso da shortare.

### C.2 Prezzo di riferimento eseguibile

Per ogni segnale si definisce un prezzo `P0` coerente con ciò che un investitore retail avrebbe potuto realmente osservare ed eseguire:

| Momento del segnale | `P0` primario |
|---|---|
| Pre-market entro le 09:25 ET | VWAP dei primi 5 minuti regolari, oppure primo VWAP disponibile dopo un halt |
| Durante la sessione | VWAP della prima barra completa di 5 minuti successiva al segnale |
| After-hours o report EOD | VWAP 09:30–09:35 ET della seduta successiva |
| Modello solo giornaliero | Apertura/VWAP della seduta successiva, non la chiusura già nota |

I segnali prodotti con dati ritardati devono usare nel backtest lo stesso ritardo.

### C.3 Etichetta primaria raccomandata

La prima etichetta da validare è:

```text
DD_10(t) = min per d=1,...,10 di ((Low_d / P0(t)) - 1)
Y_20,10(t) = 1 se DD_10(t) <= -20%, altrimenti 0
```

Quindi:

> **Forte correzione primaria = perdita intraday di almeno il 20% dal prezzo eseguibile del segnale entro dieci sedute.**

Motivazione:

- il 10% è spesso normale volatilità per biotech e microcap;
- il 20% è economicamente materiale ma non raro quanto il 30–40%;
- dieci sedute mantengono il carattere di early warning;
- il riferimento dal segnale è azionabile;
- non richiede conoscere in anticipo il massimo futuro.

### C.4 Etichette secondarie obbligatorie

Devono essere calcolate tutte le combinazioni:

- soglie: `-10%, -20%, -30%, -40%`;
- orizzonti: `1, 3, 5, 10, 20 sedute`;
- drawdown su minimo intraday e su chiusura;
- rendimento assoluto;
- rendimento relativo al settore;
- rendimento relativo a Russell 2000, Nasdaq Composite o benchmark coerente;
- massimo movimento contrario alla tesi, cioè il massimo rialzo successivo;
- drawdown dal massimo futuro, **solo come analisi diagnostica**, non come etichetta operativa primaria.

La scelta finale di `-20%/10 giorni` va confermata confrontando base rate, stabilità e utilità rispetto alle alternative.

### C.5 Definizioni quantitative iniziali

Le soglie seguenti sono ipotesi operative da pre-registrare e testare, non risultati già dimostrati.

| Concetto | Definizione operativa |
|---|---|
| **Rialzo anomalo** | Rendimento robust-z almeno 3 rispetto alla storia 252 giorni e al peer group; oppure rendimento 1 giorno ≥15%, 5 giorni ≥25% o 20 giorni ≥50%. |
| **Crescita parabolica** | Almeno due condizioni: coefficiente quadratico positivo sulla regressione del log-prezzo a 10 giorni; slope 5 giorni >1,5× slope 20 giorni; prezzo > EMA20 + 3 ATR; accelerazione positiva per tre rilevazioni. |
| **Volume anomalo** | Volume relativo ≥2 rispetto alla mediana comparabile per giorno e fascia oraria, oppure turnover sul flottante in percentile ≥95 dell’universo. |
| **Attenzione anomala** | Robust-z delle citazioni uniche >3 rispetto agli ultimi 60 giorni, controllando giorno della settimana e fascia oraria, e almeno 4× la mediana degli ultimi 7 giorni. |
| **Hype/euforia** | Composito di velocità delle citazioni, estremità del sentiment, linguaggio promozionale, certezza non giustificata, price target senza fonte, concentrazione degli autori e rapporto ricondivisioni/originali. |
| **Deterioramento informativo** | Aumento di contenuti senza fonte, duplicazioni, promozione e contraddizioni, accompagnato da riduzione di fonti primarie e origini indipendenti. |
| **Evento binario** | Evento discreto — FDA, trial, M&A, sentenza, finanziamento — capace di produrre una rivalutazione significativa in una singola sessione e con esiti nettamente divergenti. |
| **Narrativa non confermata** | Claim centrale senza una fonte di livello 1–2 al momento del segnale, anche se riportato da molte pagine. |
| **Rischio di drawdown** | Posizione ordinale nel ranking condizionale; non probabilità finché non calibrata. |
| **Forte correzione** | Primariamente `DD10 ≤ -20%`; le altre soglie rimangono outcome secondari. |

Una standardizzazione robusta può usare:

```text
z_robusto(x) = (x - mediana(x)) / (1.4826 * MAD(x))
```

### C.6 Regola iniziale di ammissione al ranking

Un titolo entra nel set dei candidati quando soddisfa:

1. almeno una condizione di accelerazione:
   - rendimento giornaliero o gap ≥15%;
   - rendimento 5 giorni ≥25%;
   - rendimento 20 giorni ≥50%;
   - return robust-z ≥3;

**e**

2. almeno una condizione di conferma:
   - volume relativo ≥2;
   - turnover anomalo;
   - attenzione robust-z ≥3;
   - nuovo evento materiale classificato.

Il filtro serve solo a ridurre l’universo. Non attribuisce da solo rischio elevato.

### C.7 Universo iniziale

#### Universo modellabile

- azioni ordinarie su Nasdaq, NYSE e NYSE American;
- incluse società successivamente delistate;
- esclusi ETF, fondi, preferred, warrant, right, unit, OTC e SPAC pre-combinazione;
- prezzo ≥$1;
- market cap point-in-time tra $50 milioni e $5 miliardi;
- median dollar volume a 20 giorni ≥$1 milione.

#### Universo ombra

Titoli sotto $1 o con liquidità inferiore non vengono ignorati, ma classificati separatamente come:

- `RISCHIO NON QUANTIFICABILE`;
- `ILLIQUIDO`;
- `DATI INSUFFICIENTI`.

In questo modo non si scambia la mancanza di modellabilità per assenza di rischio.

### C.8 Modello generale o modelli separati

#### Raccomandazione

Partire con:

- un **modello generale**;
- feature e interazioni per tipo di evento;
- gate specifici;
- analisi per sottogruppo.

Creare modelli separati per M&A, biotech, diluizione o meme stock solo quando:

- il numero di eventi positivi è sufficiente;
- il lift fuori campione è stabile;
- le feature hanno significato coerente;
- la separazione migliora il risultato rispetto al modello generale.

Un modello complesso non va adottato se una regressione regolarizzata, un GAM/Explainable Boosting Machine o regole monotone producono prestazioni equivalenti.

### C.9 Tassonomia dei pattern

| Categoria | Segnali precoci e fonti migliori | Orizzonte tipico | Falsi positivi | Pericolo dello short / stato |
|---|---|---:|---|---|
| **Biotech prima di risultati clinici** | Calendario trial, completamento enrollment, ClinicalTrials.gov, protocolli, cash runway, opzioni se disponibili | Giorni–mesi | Rinvi, anticipazioni non informative | Evento binario: evitare prima della lettura |
| **Biotech dopo risultati clinici** | Endpoint primario/secondari, statistica vs rilevanza clinica, safety, comparatore, subgroup, comunicato e paper | 1–20 giorni | Buon risultato realmente trasformativo | Gap, partnership o acquisizione successiva |
| **FDA: approvazione, CRL, AdCom** | FDA, calendario comitati, PDUFA, briefing documents, company filing | 1–10 giorni | Label più favorevole del previsto | Halt e gap incontrollabile; evento binario |
| **M&A confermata** | Filing 8-K, comunicati di entrambe le parti, merger agreement | Immediato–chiusura deal | Spread di arbitraggio normale | Offerta migliorata o contro-offerta; non adatto a short direzionale |
| **M&A non confermata** | Origine del rumor, indipendenza delle fonti, assenza di conferma, opzioni/volume | Ore–10 giorni | Rumor corretto | Massimo rischio di gap; `EVENTO BINARIO — EVITARE` |
| **Partnership senza economics chiari** | Upfront, milestone, royalty, esclusiva, cash effettivo, 8-K | 1–10 giorni | Partnership strategicamente importante | Una successiva disclosure può migliorare gli economics |
| **Small/microcap, low-float, stock promotion** | Float point-in-time, turnover/float, promo disclosure, Form 4/144, filing finanziari | Ore–20 giorni | Vera svolta aziendale | Locate scarso, halt, spread, squeeze; spesso `NON SHORTABILE` |
| **Meme, influencer, community** | Autori unici, concentrazione, repost, short interest, call activity, menzioni/float | Ore–10 giorni | Mobilitazione persistente | La tesi fondamentale può essere irrilevante nel breve |
| **Pivot AI, crypto, quantum o settore di moda** | Cambi di nome, descrizioni vaghe, ricavi riconducibili alla narrativa, capex e clienti | Giorni–mesi | Pivot genuino con contratti | Nuove promozioni e finanziamenti possono estendere il rally |
| **Earnings surprise / guidance** | 10-Q, call, qualità dei ricavi, backlog, margini, one-off, guidance bridge | 1–20 giorni | Re-rating fondamentale sostenibile | Revisions degli analisti e momentum successivo |
| **Shelf, ATM, offering, warrant, convertibili** | S-1/S-3, 424B, prospectus supplement, capacità residua ATM, warrant strike, cash burn | Ore–60 giorni | Shelf non utilizzata | Lo short può essere prematuro; l’offerta può eliminare rischio di solvibilità |
| **Lock-up / vendite insider** | Prospectus, lock-up terms, Form 4, Form 144, volume effettivo venduto | Giorni–mesi | Vendite pianificate o fiscali | Segnale debole senza contesto |
| **Reverse split, delisting, going concern, runway** | Nasdaq notices, 8-K, 10-K/10-Q, audit opinion, minimum bid | Giorni–mesi | Ricapitalizzazione riuscita | Prezzo nominale più alto e float ridotto possono facilitare squeeze |
| **Giudiziario o regolatorio** | Documenti dell’autorità, docket pubblico, filing societari | Ore–mesi | Procedimento risolto favorevolmente | Esito binario, halt e settlement |
| **Promozione coordinata** | Stesso testo su più account, burst sincronizzato, disclosure sponsor, indirizzi o domini collegati | Ore–giorni | Campagna marketing lecita | Tempistica imprevedibile, manipolazione e borrow assente |

Una shelf registration descrive una capacità potenziale di emettere titoli nel tempo; non dimostra che una vendita sia già avvenuta. Un ATM può utilizzare una shelf, ma il sistema deve cercare prospectus supplement, 424B, quantità residue e vendite effettive prima di aumentare il rischio di diluizione. ([SEC](https://www.sec.gov/files/rules/proposed/2026/33-11418.pdf))

---

## D. Matrice delle fonti

### D.1 Gerarchia esplicita

Il sistema deve assegnare due attributi distinti:

1. **affidabilità del produttore della fonte**;
2. **livello di conferma dello specifico claim**.

Una testata credibile può pubblicare un rumor non confermato; un comunicato aziendale è primario ma può presentare i risultati in modo selettivo.

| Livello | Tipo | Uso |
|---:|---|---|
| 1 | Filing, autorità, documento giudiziario o regolatorio | Evidenza primaria |
| 2 | Dichiarazione diretta di società o autorità | Primaria, ma da confrontare con il documento |
| 3 | Agenzia con reporting e fonti proprie | Origine giornalistica |
| 4 | Articolo che cita e collega una fonte primaria | Conferma derivata |
| 5 | Analisi finanziaria o scientifica | Interpretazione |
| 6 | Rumor attribuito a fonti anonime | Claim non confermato |
| 7 | Post di un utente identificabile | Segnale di attenzione |
| 8 | Opinione non verificata | Contesto, non evidenza |
| 9 | Contenuto promozionale o sponsorizzato | Possibile rischio |
| 10 | Riscrittura automatica o duplicato | Non conta come conferma |

### D.2 Deduplicazione e ricostruzione della fonte

Pipeline raccomandata:

1. normalizzazione URL e rimozione dei parametri di tracking;
2. hash esatto del contenuto disponibile;
3. SimHash/MinHash e similarità TF-IDF per copie quasi identiche;
4. estrazione di claim strutturati: soggetto, verbo, oggetto, cifra, data;
5. rilevazione di citazioni, link e frasi attribuite;
6. grafo `cita / riscrive / contraddice / conferma`;
7. clustering temporale;
8. attribuzione della probabile origine;
9. conteggio delle **origini indipendenti**, non del numero di pagine;
10. revisione manuale quando l’origine non è determinabile.

Non serve un vector database nell’MVP: hash, ricerca full-text, MinHash e una tabella di claim sono sufficienti.

### D.3 Timestamp obbligatori

Per ogni documento:

- `published_at`;
- `effective_at`, quando l’evento è avvenuto;
- `first_seen_at`;
- `retrieved_at`;
- timezone originale;
- URL canonico;
- autore/editore;
- hash;
- identificativo della famiglia di duplicati;
- identificativo del claim;
- livello della fonte;
- testo o estratto che supporta il claim.

La propagazione si misura come numero di origini e copie nei primi 15, 30, 60 e 240 minuti.

Una notizia pubblicata dopo il superamento della soglia di prezzo può spiegare il movimento a posteriori, ma non entra nelle feature predittive del segnale precedente.

### D.4 Fonti ufficiali

| Fonte | Dati, qualità e latenza | Costi/API/limiti | Licenza e conservazione | Stato |
|---|---|---|---|---|
| **SEC EDGAR** | Filing, submissions, XBRL, RSS, bulk; aggiornamento durante la giornata; full-text dal 2001 | Gratuito, senza API key; fair-access circa 10 richieste/s; bulk notturno | Conservare filing e metadati con user-agent identificabile e rispetto fair access | **MVP** ([SEC API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)) |
| **Investor relations** | Comunicati, presentazioni, webcast; qualità primaria ma tono aziendale | Generalmente gratuito; RSS o polling moderato | Conservare URL, metadata ed estratti; copie integrali solo se consentito | **MVP** |
| **FDA / Drugs@FDA / openFDA** | Decisioni, label, database e calendari; openFDA avverte che non tutti i dati sono validati per uso clinico o produttivo | Con chiave: 240 richieste/min e 120.000/giorno; senza chiave 1.000/giorno | Fonte pubblica; mantenere provenienza e data | **MVP** ([openFDA](https://open.fda.gov/apis/authentication/)) |
| **ClinicalTrials.gov API v2** | Registri trial, endpoint, stato e date | Gratuito; API ufficiale | Le date di submission e posting possono differire: conservarle entrambe | **MVP** ([ClinicalTrials.gov API](https://clinicaltrials.gov/data-api/api)) |
| **AACT** | Snapshot relazionale dell’intero ClinicalTrials.gov, aggiornato giornalmente | Gratuito, download/database | Ideale per ricerca storica e join strutturati | **Phase 0/MVP** ([AACT](https://aact.ctti-clinicaltrials.org/)) |
| **Nasdaq halt RSS** | Halt, pause e riaperture; feed aggiornato ogni minuto | Gratuito; non interrogare più frequentemente del feed | Conservare evento e timestamp | **MVP** ([Nasdaq Halt RSS](https://nasdaqtrader.com/Trader.aspx?id=TradeHaltRSS)) |
| **FINRA short interest** | Short interest ufficiale, ma solo due volte al mese | Gratuito/pubblico | Utile come contesto storico, non come misura live | **MVP, bassa frequenza** ([FINRA Short Interest](https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest)) |
| **FINRA short-sale volume** | Volume short nelle sedi FINRA, non consolidato su tutto il mercato e non equivalente allo short interest | File giornalieri/mensili | Non trasformarlo in “percentuale di azioni short” | **MVP solo descrittivo** ([FINRA Short Sale Volume](https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/monthly-short-sale-volume-files)) |
| **Form 4 e Form 144** | Proprietà insider e vendite proposte | Via EDGAR | Richiede contestualizzazione; non convertire automaticamente in segnale bearish | **MVP** |

### D.5 Dati di mercato

I prezzi seguenti sono quelli pubblicati dai provider al controllo del 16 luglio 2026 e possono cambiare.

| Provider | Copertura e latenza | Storico/costo verificato | Vincoli rilevanti | Decisione |
|---|---|---|---|---|
| **EODHD** | EOD globale, fondamentali, delisted, pre/post-market USA; dati ritardati tipicamente 15–20 minuti | EOD $19,99/mese; EOD + intraday $29,99; All-in-One $99,99. Intraday 1 minuto circa 120 giorni, 5 minuti 600 giorni, 1 ora 7.200 giorni | Uso personale; i termini indicano conservazione durante l’abbonamento e cancellazione entro un mese dalla cessazione. Verificare per iscritto uso di feature derivate e backtest | **Candidato principale al bake-off MVP** ([EODHD](https://eodhd.com/)) |
| **Tiingo** | EOD, news, IEX intraday; ampia copertura US | Piano individuale circa $30/mese; 65.000+ asset US e 100.000 richieste/giorno nel piano indicato; storico pluridecennale dichiarato | Uso personale/interno, niente redistribuzione; IEX non equivale al consolidato SIP | **Secondo candidato al bake-off** ([Tiingo](https://www.tiingo.com/about/pricing)) |
| **Alpaca Market Data** | Free con real-time IEX e dati API ritardati; SIP nel piano superiore | Free: $0, 200 richieste/min, oltre 7 anni; Plus SIP circa $99/mese | IEX rappresenta una frazione ridotta del mercato consolidato, quindi il volume pre-market non è completo | **POC e fallback, non fonte consolidata primaria** ([Alpaca Market Data](https://alpaca.markets/data)) |
| **Massive, ex Polygon** | Aggregate, trade, quote, websocket e flat files | Starter $29, Developer $79, Advanced $199; storico e latenza crescono per piano | I termini individuali sollevano un rischio materiale per uso non-display, analytics derivati, redistribuzione e cancellazione alla cessazione | **Escluso senza autorizzazione scritta** ([Massive Pricing](https://massive.com/pricing)) |
| **Norgate Data** | EOD point-in-time e survivorship-bias-free, inclusi delisted nei piani adeguati | Prezzo da verificare direttamente; niente intraday/live | Dipendenza da Windows e database proprietario | **Candidato Phase 0 per backtest** ([Norgate Data](https://norgatedata.com/)) |
| **Alpha Vantage** | EOD e intraday; semplice da integrare | Free circa 25 richieste/giorno; intraday storico e real-time richiedono premium | Non sufficiente per scansione ampia nel piano gratuito | **Fallback/manuale** ([Alpha Vantage](https://www.alphavantage.co/premium/)) |
| **Twelve Data e altri** | Potenzialmente utili | Preventivo e termini non sufficientemente verificati in questa ricerca | Nessuna decisione senza conferma di retention, delisted e extended hours | **Da valutare** |
| **Opzioni/OPRA** | Volumi, open interest, skew | Costo e licenza non compatibili con una decisione MVP già supportata | Introduce costi, complessità e data quality | **Escluso dall’MVP** |
| **Borrow/locate/cost-to-borrow** | Essenziale per simulare short reali | Normalmente broker o vendor commerciale | Nessuna fonte affidabile sotto budget verificata | **Successivo; gate “sconosciuto” nell’MVP** |

#### Decisione sui dati di mercato

- **POC live:** prova comparativa EODHD Extended contro Tiingo/Alpaca.
- **Backtest storico:** cercare un dataset point-in-time con delisted; Norgate è strutturalmente adatto ma richiede verifica commerciale e operativa.
- **Hard gate:** nessun contratto annuale finché il provider non risponde per iscritto su:
  - conservazione storica;
  - feature derivate;
  - backtest personale;
  - backup;
  - cancellazione alla cessazione;
  - uso non-display.

### D.6 News, ricerca web e community

| Fonte | Valutazione | Vincoli | Stato |
|---|---|---|---|
| **RSS ufficiali e comunicati IR** | Alta precisione per conferme | Copertura frammentata | **MVP** |
| **Brave Search API** | Buona discovery web/news, non sostituisce la licenza del contenuto | Circa $5 di credito mensile e pricing a consumo; i diritti sui contenuti terzi non vengono trasferiti automaticamente | **MVP per discovery; conservare metadata e link** ([Brave Search API](https://brave.com/search/api/)) |
| **GDELT** | Gratuito e molto ampio; utile per propagazione e discovery | Rumore elevato, deduplicazione necessaria; DOC 2.0 ha finestra recente limitata | **Phase 0/Successiva** ([GDELT](https://www.gdeltproject.org/)) |
| **Reuters/Bloomberg/agenzie** | Ottima origine giornalistica | Feed integrale costoso; nessun aggiramento di paywall | **Link/manuale o licenza dedicata** |
| **NewsAPI Developer** | Facile integrazione | Il piano Developer è per sviluppo e test, non produzione | **Escluso come backend gratuito dell’MVP** ([NewsAPI Pricing](https://newsapi.org/pricing)) |
| **Reddit API** | Utile per attenzione, concentrazione e utenti unici | Licenza revocabile; limitazioni su conservazione e addestramento; obblighi di eliminazione alla cessazione | **Successiva e limitata** ([Reddit Data API Terms](https://redditinc.com/policies/data-api-terms)) |
| **Stocktwits** | Verticale finanziario rilevante | Nuove registrazioni API risultavano sospese; pagine pubbliche non espongono sempre metriche riproducibili | **Solo consultazione manuale nell’MVP** ([Stocktwits Developers](https://api.stocktwits.com/developers)) |
| **X** | Potenzialmente rapido per rumor e influencer | Prezzo, accesso e conservazione non sufficientemente verificati | **Escluso dall’MVP; manuale** |
| **Google Trends API** | Buon proxy di attenzione retail | API in alpha, accesso limitato; storico indicato di cinque anni e dati fino a circa due giorni prima | **Successiva, se ammessi** ([Google Trends API](https://developers.google.com/search/blog/2025/07/trends-api)) |
| **YouTube Data API** | Utile per influencer e narrativa lenta | Quota base di circa 10.000 unità/giorno; ricerca costosa in quote | **Successiva/manuale** ([YouTube Data API quota](https://developers.google.com/youtube/v3/determine_quota_cost)) |
| **Yahoo Finance, Investing.com** | Contesto manuale | Nessun scraping senza autorizzazione e ToS verificati | **Manuale** |
| **Discord/Telegram** | Possibile segnale anticipatore | Privacy, accesso, consenso, archiviazione e manipolazione difficili | **Esclusi salvo canali pubblici e permesso esplicito** |

---

## E. Metodologia di scoring

### E.1 Struttura generale

Il sistema produce quattro output distinti:

1. **Drawdown Risk Index**: 0–100, ordinale.
2. **Squeeze Hazard**: 0–100 oppure `sconosciuto`.
3. **Execution/Liquidity Hazard**: 0–100.
4. **Confidence Grade**: A, B, C o D.

Il Risk Index non deve essere mostrato come “72% di probabilità”. Diventa probabilità soltanto dopo calibrazione e verifica fuori campione.

### E.2 Componenti e pesi iniziali

Ogni componente viene trasformato in percentile robusto 0–100 nell’universo point-in-time. I pesi sono iniziali e devono essere contestati dal backtest.

```text
RiskIndex = 0.20R + 0.15V + 0.10A + 0.20C + 0.15D + 0.10F + 0.10B
```

| Componente | Peso | Feature principali |
|---|---:|---|
| `R` Rally extremity | 20% | rendimenti 1/3/5/10/20/60 giorni, robust-z, gap, distanza da EMA/ATR, accelerazione, massimo recente |
| `V` Volume e turnover | 15% | RVOL, turnover, volume/float, concentrazione intraday, volume prima/dopo evento |
| `A` Attenzione | 10% | menzioni, crescita, autori unici, concentrazione, originali/repost, attenzione rispetto a cap e float |
| `C` Fragilità catalizzatore e fonte | 20% | conferma, origine, duplicati, claim indipendenti, rumor, headline/content gap, contraddizioni |
| `D` Diluizione e struttura capitale | 15% | shelf, ATM, 424B, warrant, convertibili, burn, runway, capacità residua |
| `F` Mismatch fondamentale | 10% | ricavi, perdite, cash, EV, capitalizzazione, scenario richiesto dal prezzo |
| `B` Dipendenza da evento binario | 10% | concentrazione del valore su un singolo outcome, imminenza e asimmetria |

#### Nota sulla liquidità

L’illiquidità non deve semplicemente alzare il Risk Index: può aumentare la probabilità di crash ma rende anche l’operazione molto più pericolosa. Perciò spread, ADV insufficiente, halt e borrow incerto alimentano soprattutto l’**Execution Hazard** e possono bloccare lo stato operativo.

### E.3 Information Quality Deterioration

Indicatore riproducibile:

```text
IQD = z(quota senza fonte) + z(duplicati) + z(promozionali) + z(contraddizioni)
      - z(fonti primarie) - z(origini indipendenti)
```

Il sentiment medio non entra da solo nello score: è più utile conoscere quanto è estremo, concentrato, originale, supportato e divergente dai dati ufficiali.

### E.4 Squeeze Hazard separato

Feature, quando disponibili:

- short interest;
- days-to-cover;
- borrow availability e fee;
- rapporto volume/float;
- variazioni intraday estreme;
- call volume e gamma, solo in una fase successiva;
- halt/LULD;
- concentrazione delle menzioni;
- gap pre-market;
- fallimenti di settlement o threshold list, con interpretazione prudente.

Il daily short volume FINRA non può sostituire queste misure. ([FINRA Short Interest](https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest))

### E.5 Precedenza degli stati

I gate prevalgono sul punteggio:

1. `EVENTO BINARIO — EVITARE`
2. `POSSIBILE SQUEEZE — NON ADATTO ALLO SHORT`
3. `RISCHIO NON QUANTIFICABILE`
4. `DATI INSUFFICIENTI`
5. `RISCHIO DI CORREZIONE ELEVATO`
6. `MONITORARE`

Un titolo può avere Risk Index 80 ma stato “evento binario: evitare”.

### E.6 Soglie operative provvisorie

Solo dopo il POC:

- `≥70`: rischio elevato, se confidence A/B e nessun gate;
- `55–69`: monitorare;
- `<55`: non mostrato nella lista primaria.

Queste non sono soglie statistiche finali. Devono essere pre-registrate, testate e poi eventualmente sostituite da percentili giornalieri.

### E.7 Gestione dei dati mancanti

- Un dato mancante non vale zero e non equivale a “sicuro”.
- Feature critiche mancanti riducono la confidence.
- Se mancano prezzo affidabile, timestamp dell’evento o origine del claim, il segnale viene soppresso.
- Se manca borrow, il sistema mostra `squeeze/shortability sconosciuta`.
- Nel modello statistico si possono usare imputazione mediana point-in-time e missing indicators.
- Nella spiegazione utente i campi mancanti restano visibili.

### E.8 Confidence Grade

| Grade | Condizione |
|---|---|
| **A** | Dati critici completi, almeno una fonte primaria o più origini indipendenti, timestamp verificati |
| **B** | Dati di mercato completi, evento ben classificato, ma una parte dell’intelligence è secondaria |
| **C** | Mancano float, economics, origine o dati community rilevanti |
| **D** | Dati incoerenti, ritardati, fonte non disponibile o impossibilità di ricostruire il claim |

### E.9 Explainability obbligatoria

Ogni scheda deve contenere:

- fattori che alzano lo score;
- fattori che lo riducono;
- evidenze contrarie;
- dati mancanti;
- condizioni di invalidazione;
- stato e gate;
- confidence;
- timestamp;
- link e passaggio probatorio;
- versione del codice, delle feature e del prompt.

#### Ruolo consentito all’AI

- classificazione del tipo di evento;
- estrazione di importi, date, endpoint e attribuzioni;
- separazione fatto/interpretazione/previsione;
- identificazione di contraddizioni;
- riassunto con citazioni;
- linguaggio leggibile.

#### Ruolo vietato all’AI

- inventare valori;
- modificare dati grezzi;
- assegnare liberamente lo score;
- classificare un titolo come shortabile;
- utilizzare contenuto di un forum come istruzione;
- sostituire un dato assente con una supposizione.

---

## F. Piano di validazione

### F.1 Dataset

Ogni riga-evento deve contenere:

- security identifier stabile;
- ticker point-in-time;
- exchange e stato di listing;
- prezzi e volumi con sessione;
- corporate actions;
- market cap e shares point-in-time;
- feature disponibili al timestamp;
- documenti già pubblicati;
- `first_seen_at`;
- versione della sorgente;
- etichette future calcolate solo dopo la chiusura della finestra.

L’universo deve includere delisted, fusioni, fallimenti e reverse split. Utilizzare soltanto i ticker oggi esistenti produrrebbe survivorship bias.

### F.2 Ricostruzione storica delle notizie

Per ogni documento:

- distinguere `published_at` da `first_seen_at`;
- usare il timestamp disponibile all’utente, non quello corretto successivamente;
- conservare una snapshot immutabile dei metadati;
- impedire che un filing rettificato sostituisca silenziosamente la versione iniziale;
- bloccare dal training qualsiasi articolo pubblicato dopo il segnale.

### F.3 Sessioni e prezzi

- calendario ufficiale di mercato;
- gestione di pre-market e after-hours;
- primo prezzo realmente tradabile dopo halt;
- spread e slippage dipendenti dalla liquidità;
- split e reverse split;
- delisting return;
- nessun uso retroattivo di un prezzo consolidato non disponibile live.

### F.4 Split temporale

Usare:

1. periodo iniziale di training;
2. periodo cronologicamente successivo di validazione;
3. test finale mai consultato;
4. walk-forward con finestre mobili;
5. purging ed embargo per evitare sovrapposizione degli outcome a 20 giorni.

Non utilizzare cross-validation casuale.

### F.5 Baseline

Il sistema deve battere almeno:

- rendimento 1, 5 e 20 giorni;
- volume relativo;
- volatilità realizzata;
- ATR;
- RSI;
- distanza dalla media;
- market cap;
- regola `rendimento + RVOL`;
- ranking casuale;
- ranking esclusivamente per capitalizzazione;
- ranking solo sentiment.

### F.6 Metriche primarie

- precision@5;
- precision@10;
- recall;
- area precision-recall;
- lift rispetto al base rate;
- drawdown mediano e distribuzione;
- lead time;
- massimo rialzo contrario alla tesi;
- tasso di falsi positivi;
- stabilità per anno;
- stabilità per settore;
- stabilità per tipo di catalizzatore;
- copertura e percentuale di segnali soppressi.

Brier score, reliability diagram e calibrazione entrano solo quando il sistema pubblica probabilità.

### F.7 Analisi degli errori

Ogni falso positivo deve essere attribuito a una categoria:

- catalizzatore confermato;
- nuovo evento successivo;
- acquisizione;
- squeeze;
- dati mancanti;
- duplicazione non riconosciuta;
- errore di timestamp;
- fondamentali non aggiornati;
- settore in rally;
- pura volatilità.

Analogamente, ogni falso negativo deve verificare se il candidate generator ha escluso il titolo o se lo scoring lo ha sottostimato.

### F.8 Simulazione short separata

La simulazione di trading non deve essere usata per scegliere il modello informativo iniziale. Quando verrà aggiunta dovrà comprendere:

- disponibilità di locate;
- borrow fee;
- richiami del prestito;
- spread;
- slippage;
- size come frazione dell’ADV;
- halt;
- gap contrari;
- acquisizioni;
- loss cap;
- impossibilità di entrare al prezzo teorico.

La prima domanda è: **il ranking identifica meglio dei baseline i futuri drawdown?** Non: “quanto avrebbe guadagnato uno short ideale e gratuito?”

### F.9 Criterio di successo

Prima di conoscere il test set, Fable 5 deve approvare:

- metrica primaria;
- baseline di riferimento;
- ampiezza dell’intervallo di confidenza;
- lift minimo economicamente utile;
- sottogruppi che non devono collassare.

La promozione del modello richiede un intervallo di confidenza del lift sopra zero contro il miglior baseline e una stabilità accettabile nel tempo; non basta il miglior risultato su un singolo periodo.

---

## G. Architetture confrontate

### G.1 Alternative

| Architettura | Vantaggi | Svantaggi | Costo/complessità | Valutazione |
|---|---|---|---|---|
| **1. Vercel + Supabase + worker separato** | Deploy frontend semplice, auth e DB gestiti, backup inclusi | Tre ambienti, costi minimi più alti, job lunghi scomodi, maggior lock-in | Almeno $25 Supabase più eventuale Vercel/worker, prima dei dati | Buona per prodotto commerciale, non necessaria ora |
| **2. VPS europeo all-in-one** | Costo basso, dati in UE, controllo, portabilità Docker, job lunghi semplici | Patch, backup e monitoraggio a carico dell’utente | Circa €8,49 VPS più storage opzionale | **Raccomandata** |
| **3. Serverless europeo gestito** | Scaling automatico, poco server management | Costi variabili, cold start, timeout, molte integrazioni e lock-in | Difficile da prevedere con ingestion e AI | Non consigliata per il primo MVP |
| **4. Frontend statico + VPS backend** | UI separabile in futuro, backend controllato | Due deploy e gestione CORS/auth | Poco più complessa della VPS unica | Evoluzione possibile dopo il POC |

### G.2 Architettura MVP raccomandata

#### Componenti

- **Caddy**: TLS e reverse proxy.
- **FastAPI**: API e servizi interni.
- **PostgreSQL**:
  - securities;
  - listing history;
  - bars;
  - events;
  - documents;
  - claims;
  - scores;
  - audit log.
- **PostgreSQL full-text search**: sufficiente nell’MVP.
- **DuckDB + Parquet**:
  - feature research;
  - backtest;
  - snapshot point-in-time;
  - analisi senza sovraccaricare PostgreSQL.
- **Python workers**: ingestion e feature engine.
- **systemd timers o cron**: orchestrazione iniziale.
- **Frontend leggero**: SvelteKit o Next.js, servito dallo stesso VPS.
- **Restic**: backup cifrato.
- **S3-compatible object storage opzionale**: backup e Parquet.
- **Email o Telegram personale**: notifiche, senza contenuti sensibili.

#### Componenti non necessari

- Kubernetes;
- Redis/Celery;
- Kafka;
- time-series database dedicato;
- vector database;
- multi-agent framework;
- modelli locali;
- data warehouse cloud;
- monitoraggio continuo al secondo.

### G.3 Anti-lock-in

Ogni provider deve implementare un’interfaccia comune:

- `get_daily_bars`;
- `get_intraday_bars`;
- `get_reference_data`;
- `get_corporate_actions`;
- `get_delisted`;
- `get_news_metadata`.

I dati normalizzati e le feature non devono contenere identificativi proprietari come chiave primaria.

### G.4 Sicurezza e conformità

#### Sicurezza

- accesso mono-utente tramite Tailscale/WireGuard o access proxy;
- nessun pannello amministrativo pubblico;
- segreti in file cifrati o secret store, mai nel repository;
- utenze database a privilegio minimo;
- rate limiting;
- allowlist dei domini di ingestion;
- log con redazione automatica di token;
- backup giornalieri e prova periodica di ripristino;
- aggiornamenti critici immediati e manutenzione ordinaria programmata.

#### Prompt injection

Tutto il testo esterno è dati non fidati:

- racchiuso in un campo separato;
- mai concatenato alle istruzioni di sistema;
- nessun tool call autorizzato dal testo ingerito;
- output LLM vincolato a JSON Schema;
- claim accompagnati da evidence span;
- azioni consentite in allowlist;
- documenti e forum non possono cambiare configurazione o punteggi.

#### GDPR e contenuti degli utenti

L’EDPB ha ribadito nel luglio 2026 che il GDPR si applica allo scraping quando vengono raccolti e organizzati dati personali; restano necessari base giuridica, minimizzazione, limitazione delle finalità, accuratezza, sicurezza e retention. ([EDPB](https://www.edpb.europa.eu/news/edpb-sheds-light-on-anonymisation-and-web-scraping-for-generative-ai-and-adopts-final-version_en))

Pratica consigliata:

- non conservare profili social completi;
- hash degli username quando l’identità non è necessaria;
- conservare conteggi e feature aggregate;
- retention breve per post;
- procedura di cancellazione;
- registro delle fonti e delle basi giuridiche;
- nessun contenuto da gruppi privati senza consenso.

#### Copyright e database rights

Conservare preferibilmente:

- URL;
- titolo;
- autore;
- timestamp;
- hash;
- estratti brevi necessari a dimostrare il claim;
- classificazioni;
- feature;
- identificatore del documento.

Le eccezioni europee per text and data mining e la possibilità di usare collegamenti o estratti molto brevi non equivalgono a un diritto generale di ripubblicare articoli completi. ([EUR-Lex](https://eur-lex.europa.eu/eli/dir/2019/790/oj/eng))

---

## H. Funzionamento giornaliero

Tutti i timestamp vengono conservati in UTC e visualizzati in `Europe/Rome`; non si codifica un offset fisso perché Stati Uniti ed Europa cambiano ora legale in date diverse.

| Orario ET | Attività | Output |
|---|---|---|
| **05:45** | Ingestione EOD precedente, corporate actions, nuovi filing, FDA, ClinicalTrials.gov, IR e halt | Snapshot di apertura |
| **06:30** | Quality checks: barre mancanti, split, ticker change, timestamp anomali | Report integrità |
| **08:30** | Snapshot pre-market ritardato; calcolo gap, RVOL, turnover e candidati | Prima lista |
| **08:35–09:05** | Ricerca e deduplicazione delle fonti solo per i candidati | Claim graph |
| **09:10** | Estrazione AI strutturata e applicazione dei gate | Brief pre-market |
| **11:30** | Sweep intraday limitato | Solo cambiamenti materiali |
| **15:30** | Secondo sweep intraday | Preparazione EOD |
| **16:15** | Chiusura barre, feature complete e ranking deterministico | Ranking giornaliero |
| **16:30–17:30** | Ricostruzione narrativa, controtesi, controllo fonti | Report leggibile |
| **18:00** | Freeze della versione giornaliera e backup | Snapshot riproducibile |

Il monitoraggio continuo non è giustificato nell’MVP. Due sweep intraday sono sufficienti per verificare se l’informazione aggiuntiva vale il costo.

### H.1 Condizioni di notifica

Inviare una notifica soltanto quando si verifica almeno una condizione:

- nuovo candidato nel top 10;
- variazione del Risk Index superiore a una soglia pre-registrata;
- cambiamento di stato;
- nuova fonte primaria;
- filing di finanziamento o diluizione;
- smentita o conferma di un rumor;
- nuova contraddizione materiale;
- halt;
- passaggio da confidence C/D ad A/B o viceversa.

Non notificare semplici riscritture della stessa notizia.

### H.2 Comportamento in caso di errore

- Fonte indisponibile: campo `stale`, non valore zero.
- Barra mancante: nessun segnale.
- Corporate action non riconciliata: titolo bloccato.
- Output LLM non valido: scartato e non trasformato in report.
- News senza timestamp affidabile: solo consultazione manuale.
- Database parzialmente aggiornato: ranking non pubblicato.

### H.3 Ruolo di Claude

Per l’operatività quotidiana:

- analizza notizie e filing già acquisiti;
- estrae claim e attribuzioni;
- classifica il catalizzatore;
- distingue fatto, interpretazione, rumor e previsione;
- individua evidenze contrarie;
- produce il testo da uno schema strutturato.

Il modello giornaliero dovrebbe essere il più economico che supera i test di estrazione. Fable 5 va riservato a audit, casi ambigui e phase gate. Anthropic indicava Fable 5 a $10 per milione di token input e $50 output, con tariffe batch inferiori; un modello Sonnet più economico è più adatto alla routine. ([Anthropic](https://www-cdn.anthropic.com/files/4zrzovbb/website/53da0764b66f75f6cc5521ed77e3e6426f144989.pdf))

### H.4 Ruolo di Codex

- implementazione e manutenzione delle pipeline;
- esecuzione di test;
- controllo dei timestamp;
- verifica di schema e migrazioni;
- rilevazione di dati mancanti;
- confronto tra report e fonti;
- proposte di patch;
- revisione dei job e dei log.

Codex non deve essere un passaggio obbligatorio per calcolare ogni score. Il runtime di produzione deve essere codice deterministico; Codex opera sul repository e in CI con permessi limitati. Se serve inferenza OpenAI automatizzata, va usata un’API con budget e modello espliciti, non una dipendenza implicita da un abbonamento interattivo. Le pagine OpenAI correnti separano il pricing API dei modelli e l’accesso Codex per piano. ([OpenAI Models](https://developers.openai.com/api/docs/models/compare))

### H.5 Controlli incrociati

- Claude non può scrivere nelle tabelle raw.
- Il feature engine ricalcola ogni numero.
- Il report builder rifiuta claim privi di source ID.
- Codex verifica che ogni cifra nel testo corrisponda al database.
- Ogni run conserva hash del codice, configurazione, prompt e modello.
- Una fonte non confermata mantiene l’etichetta `rumor` in tutti gli output.
- Fable 5 esamina campioni e decisioni ai phase gate, non ogni titolo quotidiano.

---

## I. Specifica funzionale per Fable 5

### I.1 Obiettivo del prodotto

Fornire ogni giorno una lista limitata di azioni statunitensi che presentano un rischio relativo elevato di drawdown dopo un’accelerazione, mostrando:

- evidenze;
- controevidenze;
- qualità informativa;
- condizioni di invalidazione;
- rischi che rendono pericolosa qualsiasi operazione short.

### I.2 Requisiti funzionali

| ID | Requisito | Criterio di accettazione |
|---|---|---|
| FR-01 | Universo point-in-time | Include ticker changes, delisted e corporate actions |
| FR-02 | Candidate generator | Ogni inclusione indica la regola numerica attivata |
| FR-03 | Raccolta fonti ufficiali | SEC/FDA/trial/IR associati a security e timestamp |
| FR-04 | Claim graph | Duplicati non contano come conferme indipendenti |
| FR-05 | Event classifier | Output da tassonomia chiusa e confidence |
| FR-06 | Risk Index deterministico | Stesso input e versione producono lo stesso score |
| FR-07 | Gate | Evento binario, squeeze, dati mancanti e illiquidità prevalgono |
| FR-08 | Lista giornaliera | Massimo 10–20 titoli, ordinati e spiegati |
| FR-09 | Pagina titolo | Prezzo, eventi, documenti, claim, score history |
| FR-10 | Timeline | Separa evento, pubblicazione, first seen e movimento prezzo |
| FR-11 | Report | Ogni affermazione materiale ha source ID |
| FR-12 | Notifiche | Solo su cambiamenti materiali predefiniti |
| FR-13 | Watchlist | Aggiunta/rimozione manuale, nessuna operazione di trading |
| FR-14 | Retrospective review | Registra l’outcome a 1/3/5/10/20 giorni |
| FR-15 | Manual override | L’utente può correggere classificazione lasciando audit trail |

### I.3 Dashboard giornaliera

Campi essenziali:

- ticker e società;
- prezzo;
- market cap;
- rendimenti 1/5/20 giorni;
- gap;
- RVOL;
- tipo di catalizzatore;
- Risk Index;
- confidence;
- squeeze hazard;
- dilution risk;
- stato;
- una frase di spiegazione;
- principale evidenza contraria;
- numero di origini indipendenti;
- ultimo aggiornamento.

Nessun grafico deve essere presente se non risponde a una domanda decisionale.

### I.4 Pagina di dettaglio

Quattro blocchi:

1. **Perché è entrato**
   - regole attivate;
   - feature principali.

2. **Cosa è successo**
   - timeline prezzo, volume, filing e notizie.

3. **Qualità della narrativa**
   - claim primari;
   - duplicati;
   - contraddizioni;
   - rumor;
   - post-move coverage.

4. **Rischi della tesi**
   - possibile conferma positiva;
   - squeeze;
   - liquidità;
   - borrow sconosciuto;
   - dati mancanti.

### I.5 Invarianti che Fable 5 deve far rispettare

- Nessuna esecuzione di ordini.
- Nessuna frase “sicuro da shortare”.
- Nessuna probabilità non calibrata.
- Nessuna conclusione senza fonte.
- Nessun dato futuro nelle feature.
- Nessun errore di ingestion trasformato in zero.
- Nessun rumor trasformato in fatto per effetto dei duplicati.
- Nessuna istruzione esterna eseguita dal modello.
- Nessun componente architetturale senza un caso d’uso dimostrato.

### I.6 Pacchetto di revisione per Fable 5

A ogni phase gate devono essere forniti:

- label specification;
- data dictionary;
- source registry con termini e data di verifica;
- 30–50 casi storici ricostruiti;
- baseline;
- error analysis;
- esempi di output;
- decision log;
- cost report;
- lista delle assunzioni non dimostrate.

Fable 5 deve restituire, per ogni decisione:

- `approvata / respinta / condizionata`;
- evidenza;
- principale controargomento;
- rischio residuo;
- esperimento più economico;
- condizione per riesame.

---

## J. Piano e backlog di implementazione

### J.1 Fasi

| Fase | Obiettivo e funzionalità | Dati richiesti | Accettazione | Dipendenze/rischi/costo | Gate |
|---|---|---|---|---|---|
| **0 — Validazione problema** | Definire label, ricostruire casi, baseline e disponibilità dati | EOD point-in-time, delisted, campione news/eventi | Dataset riproducibile; nessun look-ahead; confronto con baseline | Costo dipende dalla licenza storica; non impegnarsi prima delle risposte commerciali | Fable 5 approva label e data rights |
| **1 — Proof of concept** | Candidate generator, fonti ufficiali, score fisso, report testuale | Un provider live, SEC/FDA/trial/IR | Completezza critica elevata; ogni claim citato; budget sotto €100 | VPS + provider + API AI con cap | Il report è utile senza dashboard |
| **2 — MVP** | Dashboard, timeline, watchlist, notifiche, persistence e QC | Stessi dati, object storage opzionale | Run riproducibile; backup verificato; nessun segnale da dati corrotti | Aumenta lavoro operativo, non necessariamente costo dati | Accettazione UX e sicurezza |
| **3 — Validazione** | Walk-forward, paper tracking, error review e soglie | Storia sufficiente e stream live immutabile | Lift fuori campione e stabilità contro il miglior baseline | Può richiedere dataset point-in-time commerciale | Nessuna probabilità prima di calibrazione |
| **4 — Estensioni** | Europa, opzioni, borrow, modelli settoriali, maggiore frequenza | Licenze e mapping addizionali | Ogni estensione dimostra valore incrementale | Potenziale superamento del budget iniziale | Decisione separata per fonte |

Il paper tracking deve continuare finché il numero di alert indipendenti consente intervalli di confidenza utili; non va promosso dopo un numero arbitrario di settimane.

### J.2 Backlog

| Epic | Priorità | Funzionalità | Dipendenze | Criterio di accettazione |
|---|---:|---|---|---|
| **Source registry e licensing** | P0 | Termini, prezzi, retention, uso derivato | Risposte provider | Nessuna fonte attiva senza stato licenza |
| **Security master** | P0 | Ticker history, CIK, exchange, delisted | Provider reference + SEC | Un identificatore stabile per società/listing |
| **Market ingestion** | P0 | EOD, pre/post, corporate action | Provider selezionato | Reconciliation giornaliera e idempotenza |
| **Calendario sessioni** | P0 | Regular, pre, post, holiday, halt | Exchange data | Prezzi di riferimento corretti |
| **SEC pipeline** | P0 | 8-K, 10-Q/K, S-1/S-3, 424B, Form 4/144 | EDGAR | Parsing, raw hash e timestamp |
| **FDA/trial pipeline** | P0 | Decisioni, calendari, trial changes | FDA/ClinicalTrials | Differenza tra milestone e outcome |
| **News metadata** | P0 | Discovery, URL, hash, first seen | Brave/RSS | Niente copie integrali non autorizzate |
| **Claim graph** | P0 | Dedup, origine, conferma, contraddizione | Document ingestion | 100 copie = una famiglia di claim |
| **Feature engine** | P0 | Prezzo, volume, fundamentals, eventi | Dati puliti | Feature point-in-time testate |
| **Candidate generator** | P0 | Regole accelerazione | Feature engine | Ogni candidato ha motivazione numerica |
| **Risk score e gate** | P0 | Score, confidence, squeeze/binary states | Feature + claim graph | Output deterministico |
| **Backtest framework** | P0 | Label, baseline, walk-forward | Dataset point-in-time | Nessun leakage nei test automatici |
| **Text report** | P1 | Top ranking e spiegazioni | Score + AI extractor | Ogni frase materiale citata |
| **Dashboard** | P1 | Lista e dettaglio | API stabile | UX accettata senza grafici superflui |
| **Notifications** | P1 | Alert su delta/evento | Score history | Nessun alert da duplicati |
| **Audit e observability** | P1 | Log, run ID, versioni, health | Tutte le pipeline | Riproduzione completa del report |
| **Backup e restore** | P1 | Snapshot cifrati | Storage | Restore provato |
| **Social metadata** | P2 | Reddit/Trends autorizzati | Licenza e privacy | Lift incrementale dimostrato |
| **Borrow/opzioni** | P2 | Shortability e squeeze avanzato | Vendor commerciale | Valore superiore al costo |
| **Europa** | P3 | Filing e market mapping UE | Fonti nazionali/ESMA | Progetto separato approvato |

---

## K. Registro dei rischi

| Rischio | Prob./impatto | Segnale precoce | Mitigazione | Residuo |
|---|---|---|---|---|
| Dati di mercato errati | M/H | Gap impossibili, OHLC incoerente | Reconciliation, due fonti su casi estremi, blocco segnale | Medio |
| Survivorship bias | H/H | Solo ticker attivi nel dataset | Delisted e universe point-in-time | Basso-medio |
| Licensing insufficiente | H/H | Termini vaghi su derived/non-display | Conferma scritta prima del contratto | Alto finché non risolto |
| Cancellazione dati alla cessazione | M/H | Clausola retention limitata | Separare raw/feature e scegliere vendor con diritti adeguati | Medio-alto |
| Aumento dei costi | M/M | API/AI oltre cap | Budget mensile, enrichment solo top candidati | Basso |
| Variazione API | H/M | Deprecation, errori schema | Adapter, contract test e fallback | Medio |
| Scraping non conforme | M/H | robots/ToS contrari | API/RSS autorizzati; manuale o esclusione | Basso |
| Hallucination LLM | M/H | Claim senza evidence span | Schema, citazioni obbligatorie, reject | Basso-medio |
| Prompt injection | M/H | Testo con istruzioni o tool requests | Sandbox, separazione dati/istruzioni, allowlist | Medio |
| Overfitting | H/H | Risultati forti in un solo periodo | Test finale, walk-forward, baseline semplici | Medio |
| Falsi positivi | H/M | Molti rally proseguono | Controevidenze, confidence, revisione per evento | Medio |
| Falso senso di probabilità | M/H | Utente legge “80” come 80% | Etichetta “indice ordinale”, niente percentuali | Basso |
| Short squeeze | M/H | Turnover/float, gap, borrow ignoto | Gate separato; mai raccomandare short | Alto ma esplicito |
| Illiquidità | H/H | Spread/ADV insufficienti | Execution Hazard e stato non quantificabile | Medio |
| Timestamp non sincronizzati | M/H | News sembra precedere il prezzo | UTC, first seen, session calendar, test | Basso-medio |
| Narrativa manipolata | M/H | Copie sincronizzate, pochi autori | Origini indipendenti, concentration metrics | Medio |
| Filing mal interpretato | M/H | Shelf trattata come offerta completata | Ontologia, document chain e review | Basso-medio |
| Social data incompleti | H/M | API assente, campione parziale | Feature opzionale; confidence ridotta | Medio |
| Automazione incontrollata | L/H | Job modifica dati o configurazione | Permessi minimi, immutabilità, audit | Basso |
| Segreti esposti | L/H | Token nei log/repository | Secret scanning, rotazione, redazione | Basso |
| Backup inutilizzabile | M/H | Snapshot mai ripristinata | Restore test obbligatorio | Basso |
| Eventi rari e sottocampioni | H/M | Pochi M&A/FDA positivi | Modello generale, no segmentazione prematura | Medio |
| Model drift | M/M | Precision@10 decrescente | Monitoraggio per regime e retraining controllato | Medio |
| Conflitto tra fonti | H/M | Company vs authority/news | Conservare entrambi; non forzare sintesi | Basso-medio |
| Contenuti protetti conservati | M/H | Archivio di articoli completi | Metadata, link, estratti minimi, retention | Basso-medio |

---

## L. Decisioni aperte

### L.1 Decisioni già supportate

- Il prodotto deve essere un **ranking di rischio**, non un motore di trading.
- Il target primario più utile da testare è un drawdown dal prezzo eseguibile, non dal massimo futuro.
- L’architettura deve essere ibrida: numeri deterministici e AI semantica.
- Squeeze, evento binario e illiquidità devono essere gate separati.
- SEC, FDA, ClinicalTrials.gov, IR, Nasdaq e FINRA costituiscono il nucleo informativo.
- Un singolo VPS europeo è sufficiente per l’MVP.
- Vector database, agent framework, opzioni, modelli locali e monitoraggio continuo non sono giustificati.
- Le copie della stessa notizia non devono aumentare il numero di conferme.
- Il caso ATAI va classificato come evento binario, non come dimostrazione retrospettiva della strategia.
- Codex e Claude devono avere ruoli controllabili e non modificare liberamente i dati.

### L.2 Decisioni che richiedono test

- `-20% entro 10 sedute` rispetto alle altre etichette.
- Soglie di candidate generation.
- Pesi del Risk Index.
- EODHD contro Tiingo/Alpaca.
- Incremento informativo del pre-market rispetto al solo EOD.
- Valore di Reddit o Google Trends dopo prezzo e volume.
- Modello generale contro modelli per evento.
- Frequenza ottimale degli sweep.
- Valore incrementale dell’LLM rispetto a regole di document parsing.
- Banda di score da mostrare nella dashboard.

### L.3 Decisioni non ancora prendibili

- Probabilità calibrata di drawdown.
- Shortability effettiva senza borrow/locate.
- Uso sistematico di X e Stocktwits.
- Conservazione pluriennale dei raw market data senza risposta scritta del vendor.
- Fornitore definitivo del dataset survivorship-free.
- Necessità di opzioni.
- Espansione ai mercati europei.
- Uso unattended di specifici prodotti Claude/Codex nel runtime.
- Valore economico di una simulazione short.

### L.4 Informazioni mancanti

- Risposta commerciale su retention e derived analytics.
- Prezzo e condizioni correnti di Norgate per il caso d’uso.
- Copertura point-in-time del float.
- Fonte low-cost per borrow cost.
- Profondità storica affidabile delle news con timestamp originali.
- Dataset social legalmente conservabile.
- Base rate reale di `Y20,10` nell’universo scelto.
- Numero di eventi per ciascuna tassonomia.
- Distribuzione di spread e halt nei candidati.

### L.5 Esperimenti più economici

#### 1. Case packet storico

Ricostruire 30–50 casi, comprendendo:

- veri crash;
- rally che sono proseguiti;
- acquisizioni confermate;
- rumor smentiti;
- FDA/trial;
- offering e ATM;
- meme/squeeze;
- reverse split;
- falsi positivi.

Output: timeline point-in-time, fonti, feature e outcome.

#### 2. Bake-off dati di due settimane

Confrontare EODHD, Tiingo e Alpaca su:

- barre mancanti;
- pre-market;
- corporate actions;
- delisted/reference;
- latenza;
- correzioni successive;
- diritti di conservazione;
- tempo di integrazione.

#### 3. Baseline notebook

Prima dell’AI:

- return;
- RVOL;
- ATR;
- market cap;
- semplice combinazione soglie.

Misurare precision@10 e lead time.

#### 4. Shadow run

Eseguire il sistema senza dashboard e senza notifiche operative, congelando ogni giorno input, ranking e report. Proseguire fino a ottenere un numero di alert sufficiente per intervalli di confidenza utili.

#### 5. Ablation social

Confrontare:

- solo mercato;
- mercato + fonti ufficiali;
- mercato + ufficiali + news;
- mercato + ufficiali + news + social.

Integrare i social soltanto se il quarto modello aggiunge lift stabile.

#### 6. Licensing test

Inviare ai candidati provider una descrizione identica del caso d’uso e chiedere risposta scritta su:

- uso personale;
- calcolo di feature;
- storage;
- backup;
- backtest;
- cancellazione;
- output nella dashboard locale;
- impiego dei dati come input a un modello AI.

---

## Raccomandazione finale

La prima attività non deve essere la costruzione della dashboard. Deve essere **Fase 0**, con tre risultati verificabili:

1. **specifica immutabile delle etichette e dei timestamp**;
2. **dataset di casi storici point-in-time con delisted**;
3. **confronto delle regole elementari contro il Risk Index proposto**.

Solo dopo questa verifica conviene costruire un MVP composto da:

- VPS europeo;
- PostgreSQL;
- DuckDB/Parquet;
- un provider di mercato sotto contratto mensile;
- SEC/FDA/ClinicalTrials/IR/Nasdaq;
- candidate generator;
- claim graph;
- Risk Index ordinale;
- gate evento binario/squeeze/dati insufficienti;
- report giornaliero dei primi dieci titoli.

Il problema che può essere realisticamente risolto è **ridurre un grande universo a una lista piccola, motivata e auditabile di situazioni fragili**. Non può essere realisticamente risolta, con i dati e il budget iniziali, la previsione certa di un crollo o la selezione sicura di posizioni short.

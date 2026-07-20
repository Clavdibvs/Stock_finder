# Validazione

## Etichette

**Primaria** (pre-registrata): `DD_10 ≤ −20%` — drawdown intraday di almeno il
20% dal prezzo di riferimento entro 10 sedute.

```
DD_h(t) = min_{d=1..h} (Low_d / P0(t) − 1)
Y(t)    = 1 se DD_10(t) ≤ −0.20
```

**Secondarie** (tutte calcolate): soglie −10/−20/−30/−40 % × orizzonti
1/3/5/10/20 sedute, su minimo intraday e su chiusura; rendimento assoluto;
rendimento relativo al benchmark (e al settore quando disponibile);
**massimo movimento contrario alla tesi** (max rialzo successivo).

## Prezzo di riferimento P0

Coerente con ciò che un investitore avrebbe potuto osservare ed eseguire:
per il modello EOD dell'MVP, **apertura (o VWAP se disponibile) della seduta
successiva al segnale** — mai la chiusura già nota quando il segnale è
prodotto. (`app/validation/retrospective.py::reference_price`).

## Anti-leakage (regole verificate da test automatici)

- Le feature usano solo barre con `bar_date ≤ asof` (`test_features_use_only_past_bars`).
- Il claim graph point-in-time considera solo documenti con
  `first_seen_at ≤ asof_ts`: una smentita futura non entra in uno score
  passato (`test_future_documents_excluded_from_pit_stats`).
- `published_at` e `first_seen_at` sono campi separati; la propagazione si
  misura sul secondo.
- Una notizia pubblicata dopo il movimento è conteggiata come "post-move
  coverage" e non entra nelle feature predittive del segnale precedente.
- Gli outcome si calcolano solo dopo la chiusura della finestra (`complete`).
- Gli snapshot (`feature_snapshots`) sono immutabili per data e versionati.
- L'universo include delisted (caso demo DLST) e titoli bloccati: usare solo i
  ticker attivi produrrebbe survivorship bias.

## Baseline da battere (`app/validation/baselines.py`)

`ret_1d`, `ret_5d`, `ret_20d`, `rvol`, `atr`, `dist_ema20` (distanza dalla
media), `market_cap`, `ret_plus_rvol` (combinazione), `random` (riproducibile
con seed esplicito). Tutte producono un ranking sullo stesso set di candidati;
i valori mancanti finiscono in coda, mai trattati come 0.

## Metriche

`precision@5` e `precision@10` (implementate in
`retrospective.py::precision_at_k`), recall, lift sul base rate, drawdown
mediano, lead time, massimo rialzo contrario, stabilità per anno/settore/tipo
di catalizzatore, copertura e quota di segnali soppressi. Brier score e
calibrazione **solo** quando (e se) il sistema pubblicherà probabilità.

## Split temporale

Mai cross-validation casuale. Train → validation cronologica → test finale mai
consultato; walk-forward con purging/embargo di 20 sedute per evitare
sovrapposizione degli outcome.

## Export per il backtest

`POST /api/settings/export?fmt=parquet|csv` (o job `freeze_and_backup`):
una riga per (segnale × orizzonte) con `stable_id`, ticker point-in-time,
Risk Index, stato, confidence, hazard, versioni, feature JSON complete e
outcome. Point-in-time: le feature sono quelle salvate al momento del segnale.

## Criterio di successo (pre-registrato, Fase 3)

Prima di consultare il test set vanno fissati: metrica primaria
(precision@10 sull'etichetta primaria), miglior baseline di riferimento,
ampiezza dell'intervallo di confidenza, lift minimo utile, sottogruppi che non
devono collassare. La promozione richiede lift con intervallo di confidenza
sopra zero contro il miglior baseline e stabilità temporale — non il miglior
risultato su un singolo periodo. Il paper tracking (shadow run) continua
finché il numero di alert indipendenti non consente intervalli utili.

## Cosa NON è ancora fatto (onestà del perimetro)

- Nessun modello statistico: solo scoring deterministico + baseline.
- Nessuna calibrazione: per questo il Risk Index resta ordinale.
- Il benchmark demo è un indice fittizio; in live serve Russell 2000/Nasdaq.
- `ret_vs_sector` è previsto dallo schema ma richiede dati settoriali live.
- La trasformazione a percentili cross-section sull'universo reale
  sostituirà le saturazioni fisse (vedi SCORING.md e DECISIONS.md).

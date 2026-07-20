# Scoring

## Output distinti

Per ogni titolo il sistema produce quattro output separati, mai fusi in un
numero unico:

1. **Drawdown Risk Index** 0–100 — indice **ordinale**. Non è una probabilità e
   non viene mai presentato come tale; diventerebbe probabilità solo dopo
   calibrazione e verifica fuori campione (Fase 3).
2. **Squeeze Hazard** 0–100 oppure **`sconosciuto`** — senza short interest
   ufficiale il valore resta sconosciuto: il solo volume/float non basta.
3. **Execution/Liquidity Hazard** 0–100 — spread proxy, ADV, halt, price level.
   L'illiquidità non alza il Risk Index: rende l'operatività pericolosa, quindi
   alimenta questo hazard e può bloccare lo stato.
4. **Confidence Grade** A–D.

## Formula

```
RiskIndex = 0.20·R + 0.15·V + 0.10·A + 0.20·C + 0.15·D + 0.10·F + 0.10·B
```

Pesi in `config/scoring.yaml`, versionati (`version`), sommano a 1.0
(verificato a runtime). Ogni score salva `scoring_version`, `config_hash`
(SHA-256 della configurazione quantitativa) e `code_version`: stesso input +
stesse versioni ⇒ stesso output.

| Comp. | Peso | Contenuto | Fattori |
|---|---|---|---|
| R | 0.20 | Rally extremity | ret 1/5/20g, gap, robust-z (252g), distanza EMA20 in ATR |
| V | 0.15 | Volume/turnover | RVOL (mediana 20g), turnover sul float |
| A | 0.10 | Attenzione | documenti/giorno (le copie contano per l'attenzione), robust-z 60g |
| C | 0.20 | Fragilità catalizzatore | stato claim centrale, fonti primarie, **origini indipendenti** (i duplicati non contano), quota duplicati, contraddizioni, promo |
| D | 0.15 | Diluizione | filing recenti (S-1/S-3/424B/ATM), shelf aperta (capacità ≠ vendita avvenuta) |
| F | 0.10 | Mismatch fondamentale | proxy iniziale: rally 20g senza catalizzatore fondamentale dichiarato; attenuato da earnings/guidance |
| B | 0.10 | Evento binario | esito binario pendente (FDA/trial/M&A/sentenza), concentrazione su singolo outcome |

### Trasformazioni

Ogni fattore è mappato linearmente in 0–100 con saturazioni dichiarate nel
codice (`scale(x, lo, hi)`), poi aggregato per componente con
`combine = 0.6·max + 0.4·media`: un segnale estremo non viene diluito dai
fattori normali. Le saturazioni sono un **proxy dei percentili robusti
sull'universo point-in-time** (il disegno originale): con un universo live
completo la trasformazione andrà sostituita dai percentili cross-section —
decisione registrata in DECISIONS.md e da contestare in validazione.

### Dati mancanti (regola non negoziabile)

- Un componente non calcolabile è `None`, **mai 0**: i pesi vengono
  rinormalizzati sui componenti disponibili.
- Ogni componente mancante è visibile in dashboard e riduce la confidence.
- Più di 3 componenti mancanti → `DATI INSUFFICIENTI`, Risk Index non
  pubblicato.
- Se mancano prezzo affidabile, storia minima (60 barre) o dati freschi
  (≤3 sedute), il segnale è soppresso.
- Short interest assente → squeeze `sconosciuto` (mai 0).

## Gate (prevalgono sempre sullo score)

Precedenza:

1. **`EVENTO BINARIO — EVITARE`** — evento binario pendente (FDA, readout,
   M&A rumor/confermata, sentenza) o componente B ≥ 70 con evento dominante binario.
2. **`POSSIBILE SQUEEZE — NON ADATTO ALLO SHORT`** — squeeze hazard ≥ 60
   (calcolabile solo con short interest noto).
3. **`RISCHIO NON QUANTIFICABILE`** — prezzo < $1, universo ombra illiquido,
   execution hazard ≥ 80. Il Risk Index non viene pubblicato.
4. **`DATI INSUFFICIENTI`** — storia corta, dati stale, troppi componenti mancanti.

Un titolo può avere Risk Index 80 e stato `EVENTO BINARIO — EVITARE`: il gate
vince. Senza gate:

- `≥ 70` **e** confidence A/B → `RISCHIO DI CORREZIONE ELEVATO`
- `55–69` → `MONITORARE`
- `< 55` → `SOTTO SOGLIA` (non mostrato nella lista primaria)

Le soglie sono provvisorie (config, versionate) e pre-registrate: la
validazione (VALIDATION.md) deve contestarle.

## Confidence Grade

| Grade | Condizione |
|---|---|
| A | dati critici completi (float incluso) + fonte primaria o ≥2 origini indipendenti + storia/freschezza ok |
| B | dati di mercato e market cap completi; float assente o intelligence in parte secondaria (in live senza fonte float il massimo è B — DECISIONS D18) |
| C | manca un componente critico (R/V/C) oppure il market cap |
| D | dati stale (>3 sedute), storia <60 barre, mercato incompleto o ≥2 componenti critici mancanti |

## Squeeze Hazard

Pesi interni (config): short interest/float 0.35, days-to-cover 0.20,
volume/float 0.20, gap pre-market 0.15, halt 0.10. Richiede
`short_interest_pct_float`: in sua assenza l'hazard è `sconosciuto` e la UI lo
dice esplicitamente («short interest o borrow non disponibili»). Il borrow non
è disponibile nell'MVP: la scheda titolo mostra sempre «borrow non verificato».

## Explainability

Ogni score conserva (tabella `score_factors` + campi del punteggio): fattori
che alzano, fattori che riducono, evidenze contrarie, componenti mancanti con
spiegazione, condizioni di invalidazione, confidence, fonti (via claim →
documenti), timestamp, versioni di codice e configurazione. La dashboard non
mostra mai un numero privo di spiegazione.

## Divieti

- Mai presentare il Risk Index come probabilità o percentuale.
- Mai la frase «sicuro da shortare» (o equivalenti) in alcun output.
- L'AI non può modificare né produrre score.
- Nessun dato futuro nelle feature (test anti look-ahead automatici).

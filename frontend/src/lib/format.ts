/** Formattazione it-IT. Un dato mancante si mostra come mancante, mai come 0. */

export const MISSING = '—';

export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return MISSING;
  const sign = v > 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(digits).replace('.', ',')}%`;
}

export function num(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return MISSING;
  return v.toLocaleString('it-IT', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function int(v: number | null | undefined): string {
  if (v === null || v === undefined) return MISSING;
  return Math.round(v).toLocaleString('it-IT');
}

export function usd(v: number | null | undefined): string {
  if (v === null || v === undefined) return MISSING;
  return `$${num(v)}`;
}

export function marketCap(v: number | null | undefined): string {
  if (v === null || v === undefined) return MISSING;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2).replace('.', ',')} Mld`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)} Mln`;
  return `$${int(v)}`;
}

export function mult(v: number | null | undefined): string {
  if (v === null || v === undefined) return MISSING;
  return `${v.toFixed(1).replace('.', ',')}×`;
}

const dtf = new Intl.DateTimeFormat('it-IT', {
  timeZone: 'Europe/Rome',
  day: '2-digit', month: '2-digit', year: 'numeric',
  hour: '2-digit', minute: '2-digit'
});
const df = new Intl.DateTimeFormat('it-IT', {
  timeZone: 'Europe/Rome', day: '2-digit', month: 'short', year: 'numeric'
});

export function ts(iso: string | null | undefined): string {
  if (!iso) return MISSING;
  return dtf.format(new Date(iso)) + ' (Roma)';
}

export function day(iso: string | null | undefined): string {
  if (!iso) return MISSING;
  return df.format(new Date(iso.length === 10 ? iso + 'T12:00:00Z' : iso));
}

/** Classe CSS per lo stato. */
export function stateClass(state: string | null | undefined): string {
  switch (state) {
    case 'RISCHIO DI CORREZIONE ELEVATO': return 'b-elevated';
    case 'EVENTO BINARIO — EVITARE': return 'b-binary';
    case 'POSSIBILE SQUEEZE — NON ADATTO ALLO SHORT': return 'b-squeeze';
    case 'RISCHIO NON QUANTIFICABILE': return 'b-unquant';
    case 'DATI INSUFFICIENTI': return 'b-nodata';
    case 'MONITORARE': return 'b-monitor';
    default: return 'b-below';
  }
}

export function stateShort(state: string | null | undefined): string {
  switch (state) {
    case 'RISCHIO DI CORREZIONE ELEVATO': return 'RISCHIO ELEVATO';
    case 'EVENTO BINARIO — EVITARE': return 'EVENTO BINARIO';
    case 'POSSIBILE SQUEEZE — NON ADATTO ALLO SHORT': return 'POSSIBILE SQUEEZE';
    case 'RISCHIO NON QUANTIFICABILE': return 'NON QUANTIFICABILE';
    default: return state ?? MISSING;
  }
}

/** Colore della barra Risk Index (ordinale, non probabilità). */
export function riskColor(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'var(--ink-3)';
  if (v >= 70) return 'var(--state-elevated)';
  if (v >= 55) return 'var(--accent)';
  return 'var(--state-monitor)';
}

export const EVENT_LABELS: Record<string, string> = {
  clinical_readout_positive: 'Risultati clinici',
  clinical_readout_negative: 'Risultati clinici negativi',
  clinical_readout_pending: 'Lettura clinica attesa',
  clinical_milestone: 'Milestone clinica',
  fda_decision_pending: 'Decisione FDA attesa',
  fda_approval: 'Approvazione FDA',
  fda_crl: 'FDA CRL',
  ma_confirmed: 'M&A confermata',
  ma_rumor: 'Rumor M&A',
  ma_rumor_denied: 'Rumor M&A smentito',
  partnership: 'Partnership',
  offering_or_dilution: 'Offering / diluizione',
  insider_activity: 'Attività insider',
  earnings_surprise: 'Earnings surprise',
  guidance_change: 'Cambio guidance',
  index_inclusion: 'Inclusione in indice',
  reverse_split: 'Reverse split',
  delisting_notice: 'Avviso delisting',
  going_concern: 'Going concern',
  court_ruling_pending: 'Sentenza attesa',
  court_ruling: 'Sentenza',
  promotion_suspected: 'Promozione sospetta',
  meme_attention: 'Attenzione social/meme',
  sector_pivot: 'Pivot di settore',
  halt: 'Halt',
  other_material: 'Altro evento materiale'
};

export function eventLabel(t: string | null | undefined): string {
  if (!t) return MISSING;
  return EVENT_LABELS[t] ?? t;
}

export const SOURCE_LEVELS: Record<number, string> = {
  1: 'Filing / autorità',
  2: 'Dichiarazione diretta',
  3: 'Agenzia con fonti proprie',
  4: 'Cita fonte primaria',
  5: 'Analisi',
  6: 'Rumor (fonti anonime)',
  7: 'Post utente',
  8: 'Opinione non verificata',
  9: 'Promozionale',
  10: 'Riscrittura / duplicato'
};

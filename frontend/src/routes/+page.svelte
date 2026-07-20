<script lang="ts">
  import { api } from '$lib/api';
  import { goto } from '$app/navigation';
  import Badge from '$lib/components/Badge.svelte';
  import Conf from '$lib/components/Conf.svelte';
  import RiskBar from '$lib/components/RiskBar.svelte';
  import { pct, usd, marketCap, mult, ts, eventLabel, MISSING } from '$lib/format';

  type Row = {
    id: number; ticker: string; name: string; is_demo: boolean;
    price: number | null; market_cap: number | null;
    ret_1d: number | null; ret_5d: number | null; ret_20d: number | null;
    gap: number | null; premarket_gap: number | null; rvol: number | null;
    catalyst_type: string | null; risk_index: number | null; confidence: string;
    squeeze_hazard: number | null; squeeze_unknown: boolean;
    dilution_risk: number | null; state: string; summary: string | null;
    main_contrary_evidence: string | null; independent_origins: number | null;
    missing_data: string[]; updated_at: string; in_watchlist: boolean;
  };

  let items: Row[] = $state([]);
  let date: string | null = $state(null);
  let loading = $state(true);
  let error = $state('');
  let expanded: number | null = $state(null);

  let filters = $state({
    state: '', event_type: '', confidence: '',
    watchlist_only: false, new_only: false, changed_only: false, max_market_cap: ''
  });
  let filterOptions = $state<{ states: string[]; event_types: string[]; confidence_grades: string[] }>({
    states: [], event_types: [], confidence_grades: []
  });

  async function load() {
    loading = true;
    error = '';
    try {
      const params = new URLSearchParams();
      if (filters.state) params.set('state', filters.state);
      if (filters.event_type) params.set('event_type', filters.event_type);
      if (filters.confidence) params.set('confidence', filters.confidence);
      if (filters.watchlist_only) params.set('watchlist_only', 'true');
      if (filters.new_only) params.set('new_only', 'true');
      if (filters.changed_only) params.set('changed_only', 'true');
      if (filters.max_market_cap) params.set('max_market_cap', String(Number(filters.max_market_cap) * 1e6));
      const data = await api.get<{ date: string | null; items: Row[] }>(
        `/api/dashboard?${params.toString()}`
      );
      items = data.items;
      date = data.date;
    } catch (e) {
      if ((e as { status?: number }).status !== 401) error = String((e as Error).message);
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    // ricarica al cambio di qualunque filtro
    void filters.state; void filters.event_type; void filters.confidence;
    void filters.watchlist_only; void filters.new_only; void filters.changed_only;
    void filters.max_market_cap;
    load();
  });

  $effect(() => {
    api.get<typeof filterOptions>('/api/dashboard/filters')
      .then((o) => (filterOptions = o))
      .catch(() => {});
  });

  function sq(row: Row): string {
    if (row.squeeze_unknown) return 'sconosciuto';
    if (row.squeeze_hazard === null) return MISSING;
    return String(Math.round(row.squeeze_hazard));
  }
  function dil(row: Row): string {
    return row.dilution_risk === null ? MISSING : String(Math.round(row.dilution_risk));
  }
</script>

<div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:12px">
  <h1>Classifica giornaliera</h1>
  {#if date}<span class="mono" style="color:var(--ink-2); font-size:13px">seduta di riferimento: {date}</span>{/if}
</div>

<div class="filters">
  <select bind:value={filters.state} aria-label="Filtro stato">
    <option value="">Tutti gli stati</option>
    {#each filterOptions.states as s}<option value={s}>{s}</option>{/each}
  </select>
  <select bind:value={filters.event_type} aria-label="Filtro evento">
    <option value="">Tutti gli eventi</option>
    {#each filterOptions.event_types as e}<option value={e}>{eventLabel(e)}</option>{/each}
  </select>
  <select bind:value={filters.confidence} aria-label="Filtro confidence">
    <option value="">Ogni confidence</option>
    {#each filterOptions.confidence_grades as g}<option value={g}>Confidence {g}</option>{/each}
  </select>
  <input type="number" placeholder="Cap max (Mln $)" bind:value={filters.max_market_cap}
         style="width:130px" aria-label="Market cap massima in milioni" />
  <label class="check"><input type="checkbox" bind:checked={filters.watchlist_only} /> watchlist</label>
  <label class="check"><input type="checkbox" bind:checked={filters.new_only} /> solo nuovi</label>
  <label class="check"><input type="checkbox" bind:checked={filters.changed_only} /> solo cambi materiali</label>
</div>

{#if error}
  <div class="panel" style="border-color:var(--state-elevated)">Errore: {error}</div>
{:else if loading}
  <div class="panel" style="color:var(--ink-2)">Caricamento…</div>
{:else if items.length === 0}
  <div class="panel" style="color:var(--ink-2)">
    Nessun titolo supera i criteri con i filtri correnti. La lista mostra al massimo 20 titoli;
    i titoli sotto soglia non compaiono nella lista primaria.
  </div>
{:else}
  <div class="panel table-wrap" style="padding:6px 8px">
    <table class="data">
      <thead>
        <tr>
          <th>Titolo</th>
          <th>Stato</th>
          <th class="num">Risk Idx</th>
          <th>Conf</th>
          <th class="num">Prezzo</th>
          <th class="num">Cap</th>
          <th class="num">1g</th>
          <th class="num">5g</th>
          <th class="num">20g</th>
          <th class="num">Gap</th>
          <th class="num">RVOL</th>
          <th>Catalizzatore</th>
          <th class="num">Squeeze</th>
          <th class="num">Diluiz.</th>
          <th class="num">Origini</th>
        </tr>
      </thead>
      <tbody>
        {#each items as row (row.id)}
          <tr class="rowlink"
              onclick={() => (expanded = expanded === row.id ? null : row.id)}
              ondblclick={() => goto(`/titolo/${row.id}`)}>
            <td>
              <a href="/titolo/{row.id}" onclick={(e) => e.stopPropagation()}
                 class="mono" style="font-weight:700">{row.ticker}</a>
              <div style="font-size:11px; color:var(--ink-3); max-width:150px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">
                {row.name}{#if row.in_watchlist}<span title="in watchlist" style="color:var(--accent)"> ☆</span>{/if}
              </div>
            </td>
            <td><Badge state={row.state} /></td>
            <td class="num"><RiskBar value={row.risk_index} /></td>
            <td><Conf grade={row.confidence} /></td>
            <td class="num">{usd(row.price)}</td>
            <td class="num">{marketCap(row.market_cap)}</td>
            <td class="num" class:pos={(row.ret_1d ?? 0) > 0} class:neg={(row.ret_1d ?? 0) < 0}>{pct(row.ret_1d)}</td>
            <td class="num" class:pos={(row.ret_5d ?? 0) > 0} class:neg={(row.ret_5d ?? 0) < 0}>{pct(row.ret_5d)}</td>
            <td class="num" class:pos={(row.ret_20d ?? 0) > 0} class:neg={(row.ret_20d ?? 0) < 0}>{pct(row.ret_20d)}</td>
            <td class="num">{pct(row.premarket_gap ?? row.gap)}</td>
            <td class="num">{mult(row.rvol)}</td>
            <td style="font-size:12px">{eventLabel(row.catalyst_type)}</td>
            <td class="num">
              {#if row.squeeze_unknown}<span class="missing" title="Short interest o borrow non disponibili: hazard non quantificabile">sconosciuto</span>
              {:else}{sq(row)}{/if}
            </td>
            <td class="num">
              {#if row.dilution_risk === null}<span class="missing" title="Nessuna informazione su shelf/ATM/offering: componente non calcolata, non zero">n/d</span>
              {:else}{dil(row)}{/if}
            </td>
            <td class="num">{row.independent_origins ?? MISSING}</td>
          </tr>
          {#if expanded === row.id}
            <tr class="subrow">
              <td colspan="15">
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 6px 24px">
                  <div><strong style="color:var(--ink)">Perché:</strong> {row.summary ?? MISSING}</div>
                  <div><strong style="color:var(--claim-fatto)">Evidenza contraria:</strong>
                    {row.main_contrary_evidence ?? 'nessuna registrata'}</div>
                  <div>
                    <strong style="color:var(--accent)">Dati mancanti:</strong>
                    {#if row.missing_data.length === 0}nessuno{:else}
                      {#each row.missing_data.slice(0, 6) as m}<span class="missing" style="margin-right:4px">{m}</span>{/each}
                      {#if row.missing_data.length > 6}+{row.missing_data.length - 6}{/if}
                    {/if}
                  </div>
                  <div style="color:var(--ink-3)">Aggiornato: {ts(row.updated_at)} ·
                    <a href="/titolo/{row.id}">apri scheda completa →</a></div>
                </div>
              </td>
            </tr>
          {/if}
        {/each}
      </tbody>
    </table>
  </div>
  <p style="font-size:12px; color:var(--ink-3)">
    Clic per espandere la spiegazione, doppio clic o link sul ticker per la scheda.
    Il Risk Index è un indice ordinale 0–100: <em>non</em> è una probabilità.
    I gate (evento binario, squeeze, illiquidità, dati insufficienti) prevalgono sempre sul punteggio.
  </p>
{/if}

<script lang="ts">
  import { api } from '$lib/api';
  import Badge from '$lib/components/Badge.svelte';
  import Conf from '$lib/components/Conf.svelte';
  import RiskBar from '$lib/components/RiskBar.svelte';
  import { ts, MISSING } from '$lib/format';

  let items: any[] = $state([]);
  let alerts: any[] = $state([]);
  let error = $state('');
  let editingId: number | null = $state(null);
  let editNote = $state('');

  async function load() {
    try {
      [items, alerts] = await Promise.all([
        api.get<any[]>('/api/watchlist'),
        api.get<any[]>('/api/watchlist/alerts')
      ]);
    } catch (e) {
      error = String((e as Error).message);
    }
  }
  $effect(() => { load(); });

  async function remove(itemId: number) {
    await api.del(`/api/watchlist/${itemId}`);
    await load();
  }

  async function saveNote(itemId: number) {
    await api.put(`/api/watchlist/${itemId}/note`, { note: editNote });
    editingId = null;
    await load();
  }
</script>

<h1 style="margin-bottom:14px">Watchlist personale</h1>
<p style="color:var(--ink-2); font-size:13px; margin-top:0">
  Elenco manuale con note personali. Nessuna funzione di trading: la watchlist non compra,
  non vende e non invia ordini.
</p>
{#if error}<div class="panel" style="border-color:var(--state-elevated)">Errore: {error}</div>{/if}

<section class="panel">
  <h2>Titoli seguiti</h2>
  {#if items.length === 0}
    <p style="color:var(--ink-2)">Watchlist vuota. Aggiungi titoli dalla dashboard o dalla scheda titolo.</p>
  {:else}
    <div class="table-wrap">
      <table class="data">
        <thead><tr><th>Titolo</th><th>Stato attuale</th><th class="num">Risk Idx</th><th>Conf</th>
          <th>Nota personale</th><th>Aggiunto</th><th></th></tr></thead>
        <tbody>
          {#each items as w (w.item_id)}
            <tr>
              <td>
                <a href="/titolo/{w.security.id}" class="mono" style="font-weight:700">{w.security.ticker}</a>
                <div style="font-size:11px; color:var(--ink-3)">{w.security.name}</div>
              </td>
              <td>{#if w.latest_score}<Badge state={w.latest_score.state} />{:else}<span class="missing">mai valutato</span>{/if}</td>
              <td class="num">{#if w.latest_score}<RiskBar value={w.latest_score.risk_index} />{:else}{MISSING}{/if}</td>
              <td>{#if w.latest_score}<Conf grade={w.latest_score.confidence} />{:else}{MISSING}{/if}</td>
              <td style="max-width:340px">
                {#if editingId === w.item_id}
                  <div style="display:flex; gap:6px">
                    <input type="text" bind:value={editNote} style="flex:1" maxlength="2000" />
                    <button onclick={() => saveNote(w.item_id)} class="primary" style="font-size:12px">salva</button>
                    <button onclick={() => (editingId = null)} style="font-size:12px">annulla</button>
                  </div>
                {:else}
                  <span style="font-size:12.5px; color:var(--ink-2)">{w.note ?? '—'}</span>
                  <button style="font-size:11px; padding:1px 8px; margin-left:6px"
                          onclick={() => { editingId = w.item_id; editNote = w.note ?? ''; }}>modifica</button>
                {/if}
              </td>
              <td class="mono" style="font-size:11.5px; white-space:nowrap">{ts(w.added_at)}</td>
              <td><button class="danger" style="font-size:12px" onclick={() => remove(w.item_id)}>rimuovi</button></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>

<section class="panel">
  <h2>Storico degli alert</h2>
  <p style="font-size:12px; color:var(--ink-3); margin-top:0">
    Notifiche generate solo su cambiamenti materiali predefiniti. Mai per semplici duplicati.
  </p>
  {#if alerts.length === 0}
    <p style="color:var(--ink-2)">Nessun alert registrato.</p>
  {:else}
    <table class="data">
      <thead><tr><th>Quando</th><th>Titolo</th><th>Condizione</th><th>Messaggio</th></tr></thead>
      <tbody>
        {#each alerts as a}
          <tr>
            <td class="mono" style="font-size:11.5px; white-space:nowrap">{ts(a.created_at)}</td>
            <td>{#if a.security}<a href="/titolo/{a.security.id}" class="mono" style="font-weight:600">{a.security.ticker}</a>{:else}{MISSING}{/if}</td>
            <td><span class="mono" style="font-size:11px; color:var(--accent)">{a.rule}</span></td>
            <td style="font-size:12.5px"><strong>{a.title}</strong>
              {#if a.body}<div style="color:var(--ink-2)">{a.body}</div>{/if}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<script lang="ts">
  import { api } from '$lib/api';
  import { ts } from '$lib/format';

  let data: any = $state(null);
  let error = $state('');
  let runningJob = $state('');
  let jobResult = $state('');

  async function load() {
    try {
      data = await api.get('/api/quality');
    } catch (e) {
      error = String((e as Error).message);
    }
  }
  $effect(() => { load(); });

  async function runJob(name: string) {
    runningJob = name;
    jobResult = '';
    try {
      const res = await api.post<{ result: { status: string } }>(`/api/quality/jobs/${name}/run`);
      jobResult = `${name}: ${res.result.status}`;
      await load();
    } catch (e) {
      jobResult = `${name}: errore — ${(e as Error).message}`;
    } finally {
      runningJob = '';
    }
  }

  const sevColor: Record<string, string> = {
    error: 'var(--state-elevated)', warn: 'var(--accent)', info: 'var(--state-monitor)'
  };
</script>

<h1 style="margin-bottom:14px">Data quality e run</h1>
{#if error}<div class="panel" style="border-color:var(--state-elevated)">Errore: {error}</div>{/if}

{#if data}
  <section class="panel">
    <h2>Auto-valutazione del ranking</h2>
    {#if !data.validation}
      <p style="color:var(--ink-2); font-size:13px">
        Nessun report ancora: il job settimanale <span class="mono">validation_report</span>
        (sabato 12:00 ET) misura precision@5/@10 del ranking contro le 9 baseline
        appena le finestre a 10 sedute si chiudono. Eseguibile anche manualmente qui sotto.
      </p>
    {:else}
      {@const v = data.validation.latest}
      <div style="display:flex; gap:28px; flex-wrap:wrap; margin-bottom:8px" class="mono">
        <div><span style="font-size:22px; font-weight:700">{v.signals_evaluated}</span>
          <span style="color:var(--ink-3); font-size:12px"> segnali con finestra chiusa</span></div>
        <div><span style="font-size:22px; font-weight:700">{v.precision['system@10'] ?? '—'}</span>
          <span style="color:var(--ink-3); font-size:12px"> precision@10 sistema</span></div>
        <div><span style="font-size:22px; font-weight:700">{v.best_baseline ? (v.precision[v.best_baseline] ?? '—') : '—'}</span>
          <span style="color:var(--ink-3); font-size:12px"> miglior baseline ({v.best_baseline ?? 'n/d'})</span></div>
        <div><span style="font-size:22px; font-weight:700;
             color:{v.lift_vs_best_baseline == null ? 'var(--ink-3)' : v.lift_vs_best_baseline >= 0 ? 'var(--claim-fatto)' : 'var(--state-elevated)'}">
             {v.lift_vs_best_baseline ?? '—'}</span>
          <span style="color:var(--ink-3); font-size:12px"> lift vs baseline</span></div>
      </div>
      <p style="font-size:12px; color:{v.interpretable ? 'var(--ink-3)' : 'var(--accent)'}">
        {v.note} · etichetta: <span class="mono">{v.label}</span> ·
        aggiornato {ts(v.generated_at)}. I pesi non si modificano mai da soli:
        la ricalibrazione è una decisione manuale informata da questi numeri.
      </p>
    {/if}
  </section>

  <section class="panel">
    <h2>Stato dei provider</h2>
    <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:10px">
      {#each data.providers as p}
        <div style="border:1px solid var(--border); border-radius:5px; padding:10px 12px; display:flex; justify-content:space-between; align-items:center">
          <div>
            <div style="font-weight:600; font-size:13px">{p.name}</div>
            <div style="font-size:11px; color:var(--ink-3)">{p.kind}</div>
          </div>
          {#if p.configured}
            <span class="badge b-monitor" style="color:var(--claim-fatto); border-color:color-mix(in srgb, var(--claim-fatto) 40%, transparent); background:color-mix(in srgb, var(--claim-fatto) 10%, transparent)">ok</span>
          {:else}
            <span class="missing">{p.status}</span>
          {/if}
        </div>
      {/each}
    </div>
    <p style="font-size:11.5px; color:var(--ink-3); margin-bottom:0">
      Una fonte non configurata resta esplicitamente «non configurata»: il sistema non genera
      dati fittizi e la confidence dei titoli interessati si riduce.
    </p>
  </section>

  <section class="panel">
    <div style="display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px">
      <h2>Run recenti</h2>
      {#if jobResult}<span class="mono" style="font-size:12px; color:var(--accent)">{jobResult}</span>{/if}
    </div>
    <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:12px">
      {#each data.allowed_jobs as j}
        <button style="font-size:12px" disabled={runningJob !== ''}
                onclick={() => runJob(j)}>
          {runningJob === j ? 'in esecuzione…' : `▶ ${j}`}
        </button>
      {/each}
    </div>
    <div class="table-wrap">
      <table class="data">
        <thead><tr><th>Job</th><th>Esito</th><th>Avvio</th><th>Fine</th><th class="num">Elementi</th>
          <th>Trigger</th><th>Errori</th></tr></thead>
        <tbody>
          {#each data.runs as r}
            <tr>
              <td class="mono" style="font-size:12px">{r.job}</td>
              <td>
                <span style="color:{r.status === 'success' ? 'var(--claim-fatto)' : r.status === 'failed' ? 'var(--state-elevated)' : 'var(--accent)'}; font-weight:600; font-size:12px">
                  {r.status}
                </span>
              </td>
              <td class="mono" style="font-size:11.5px; white-space:nowrap">{ts(r.started_at)}</td>
              <td class="mono" style="font-size:11.5px; white-space:nowrap">{ts(r.finished_at)}</td>
              <td class="num">{r.items}</td>
              <td style="font-size:12px; color:var(--ink-3)">{r.triggered_by}</td>
              <td style="font-size:11.5px; color:var(--state-elevated)">
                {r.errors ? r.errors.slice(0, 2).join('; ') : ''}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel">
    <h2>Problemi aperti</h2>
    {#if data.issues.length === 0}
      <p style="color:var(--claim-fatto)">Nessun problema di qualità dati aperto.</p>
    {:else}
      <table class="data">
        <thead><tr><th>Tipo</th><th>Gravità</th><th>Titolo</th><th>Messaggio</th><th>Rilevato</th></tr></thead>
        <tbody>
          {#each data.issues as i}
            <tr>
              <td class="mono" style="font-size:11.5px">{i.type}</td>
              <td><span style="color:{sevColor[i.severity] ?? 'var(--ink-2)'}; font-weight:600; font-size:12px">{i.severity}</span></td>
              <td>{#if i.security}<a href="/titolo/{i.security.id}" class="mono">{i.security.ticker}</a>{:else}—{/if}</td>
              <td style="font-size:12.5px; color:var(--ink-2)">{i.message}</td>
              <td class="mono" style="font-size:11.5px; white-space:nowrap">{ts(i.detected_at)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>

  <section class="panel">
    <h2>Output AI scartati</h2>
    {#if data.ai_rejected.length === 0}
      <p style="color:var(--ink-2)">Nessun output AI scartato (o AI disabilitata).</p>
    {:else}
      <table class="data">
        <thead><tr><th>Quando</th><th>Modello</th><th>Scopo</th><th>Esito</th></tr></thead>
        <tbody>
          {#each data.ai_rejected as a}
            <tr>
              <td class="mono" style="font-size:11.5px">{ts(a.ts)}</td>
              <td class="mono" style="font-size:12px">{a.model}</td>
              <td>{a.purpose}</td>
              <td style="color:var(--accent)">{a.status}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    <p style="font-size:11.5px; color:var(--ink-3); margin-bottom:0">
      Un output AI che non rispetta lo schema o è privo di evidence span viene scartato
      e non entra mai nei report.
    </p>
  </section>
{/if}

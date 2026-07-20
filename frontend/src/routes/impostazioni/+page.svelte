<script lang="ts">
  import { api, getCsrf } from '$lib/api';
  import { eventLabel } from '$lib/format';

  let s: any = $state(null);
  let error = $state('');
  let exporting = $state(false);
  let exportMsg = $state('');
  let universe: any = $state(null);
  let newTickers = $state('');
  let universeMsg = $state('');
  let universeBusy = $state(false);

  async function loadUniverse() {
    try {
      universe = await api.get('/api/settings/universe');
    } catch {
      universe = null;
    }
  }

  $effect(() => {
    api.get('/api/settings').then((d) => (s = d)).catch((e) => (error = String(e.message)));
    loadUniverse();
  });

  async function syncUniverse() {
    universeBusy = true;
    universeMsg = '';
    try {
      const tickers = newTickers.split(/[\s,;]+/).filter(Boolean);
      const res = await api.post<any>('/api/settings/universe', { tickers });
      const unknown = res.unknown_to_sec?.length
        ? ` — non registrati SEC: ${res.unknown_to_sec.join(', ')}` : '';
      universeMsg = `Creati ${res.created.length}, aggiornati ${res.updated.length}${unknown}. ` +
        `Ora esegui backfill_history da Data quality per lo storico.`;
      newTickers = '';
      await loadUniverse();
    } catch (e) {
      universeMsg = String((e as Error).message);
    } finally {
      universeBusy = false;
    }
  }

  async function doExport(fmt: string) {
    exporting = true;
    exportMsg = '';
    try {
      const headers: Record<string, string> = {};
      const csrf = getCsrf();
      if (csrf) headers['X-CSRF-Token'] = csrf;
      const res = await fetch(`/api/settings/export?fmt=${fmt}`, {
        method: 'POST', credentials: 'same-origin', headers
      });
      if (!res.ok) throw new Error(`export fallito (${res.status})`);
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `signals.${fmt}`;
      a.click();
      URL.revokeObjectURL(a.href);
      exportMsg = 'Export completato.';
    } catch (e) {
      exportMsg = String((e as Error).message);
    } finally {
      exporting = false;
    }
  }
</script>

<h1 style="margin-bottom:14px">Impostazioni</h1>
{#if error}<div class="panel" style="border-color:var(--state-elevated)">Errore: {error}</div>{/if}

{#if s}
  <section class="panel">
    <h2>Modalità e ambiente</h2>
    <dl class="kv">
      <dt>Modalità</dt><dd style="color:{s.mode === 'demo' ? 'var(--accent)' : 'var(--claim-fatto)'}; font-weight:700">{s.mode.toUpperCase()}</dd>
      <dt>Versione applicazione</dt><dd>{s.app_version}</dd>
      <dt>Login applicativo</dt><dd>{s.auth_disabled ? 'disabilitato (rete privata/Tailscale)' : 'attivo'}</dd>
      <dt>Timezone di visualizzazione</dt><dd>{s.timezone_display}</dd>
    </dl>
    <p style="font-size:12px; color:var(--ink-3)">
      La modalità si cambia con la variabile d'ambiente <span class="mono">DDR_APP_MODE</span>
      (demo / live) e riavvio del backend. In modalità live servono provider configurati:
      senza configurazione le fonti restano «non configurate», mai simulate.
    </p>
  </section>

  <section class="panel">
    <h2>Universo live</h2>
    {#if s.mode !== 'live'}
      <p style="color:var(--ink-2); font-size:13px">
        In modalità demo l'universo è gestito dal seed. Per operare su titoli reali:
        imposta <span class="mono">DDR_APP_MODE=live</span> (con provider configurati) e riavvia.
      </p>
    {:else if universe?.universe_mode === 'auto'}
      <p style="font-size:13px; margin-top:0">
        <strong style="color:var(--claim-fatto)">Scoperta automatica attiva</strong> —
        l'intero listino USA viene sincronizzato ogni giorno dal provider
        (ETF, fondi, warrant, unit e preferred esclusi con euristiche documentate).
      </p>
      <div style="display:flex; gap:28px; flex-wrap:wrap; margin-bottom:8px" class="mono">
        <div><span style="font-size:22px; font-weight:700">{universe.total_equities.toLocaleString('it-IT')}</span>
          <span style="color:var(--ink-3); font-size:12px"> azioni in universo</span></div>
        <div><span style="font-size:22px; font-weight:700">{universe.total_crypto}</span>
          <span style="color:var(--ink-3); font-size:12px"> coppie crypto{universe.crypto_enabled ? '' : ' (disabilitate)'}</span></div>
        <div><span style="font-size:22px; font-weight:700">{universe.benchmark}</span>
          <span style="color:var(--ink-3); font-size:12px"> benchmark</span></div>
      </div>
      <p style="font-size:12px; color:var(--ink-3)">
        L'anagrafica SEC (CIK, shares outstanding) e le news vengono arricchite solo
        sui candidati del giorno. Le crypto non hanno filing né market cap ufficiale:
        confidence massima C, mai «RISCHIO ELEVATO».
      </p>
    {:else}
      <p style="font-size:12.5px; color:var(--ink-2); margin-top:0">
        Universo esplicito (max 500 ticker). L'anagrafica (CIK, nome, shares outstanding)
        arriva da SEC se configurata. Benchmark outcome: <span class="mono">{universe?.benchmark ?? '—'}</span>.
        Per la scoperta automatica full-market: <span class="mono">DDR_UNIVERSE_MODE=auto</span>.
      </p>
      <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:flex-start">
        <textarea rows="2" style="flex:1; min-width:280px" placeholder="Ticker separati da virgola o spazio, es. ATAI, SAVA, IONQ, MARA"
                  bind:value={newTickers}></textarea>
        <button class="primary" onclick={syncUniverse}
                disabled={universeBusy || !newTickers.trim()}>
          {universeBusy ? 'Sincronizzo…' : 'Aggiungi e sincronizza'}
        </button>
      </div>
      {#if universeMsg}<p style="font-size:12px; color:var(--accent)">{universeMsg}</p>{/if}
      {#if universe?.tickers?.length}
        <div class="table-wrap" style="margin-top:10px">
          <table class="data" style="max-width:860px">
            <thead><tr><th>Ticker</th><th>Società</th><th>Exchange</th><th>CIK</th><th class="num">Shares out.</th></tr></thead>
            <tbody>
              {#each universe.tickers as t}
                <tr>
                  <td class="mono" style="font-weight:700"><a href="/titolo/{t.security_id}">{t.ticker}</a></td>
                  <td style="font-size:12.5px">{t.name}</td>
                  <td style="font-size:12px; color:var(--ink-2)">{t.exchange}</td>
                  <td class="mono" style="font-size:11.5px">{t.cik ?? '—'}</td>
                  <td class="num">{t.shares_outstanding
                    ? (t.shares_outstanding / 1e6).toFixed(1).replace('.', ',') + ' Mln'
                    : '—'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <p style="color:var(--accent); font-size:12.5px">
          Universo vuoto: aggiungi i ticker qui sopra, poi esegui
          <span class="mono">backfill_history</span> da Data quality per caricare lo storico.
        </p>
      {/if}
    {/if}
  </section>

  <section class="panel">
    <h2>Provider e API key</h2>
    <div class="table-wrap">
      <table class="data" style="max-width:720px">
        <thead><tr><th>Provider</th><th>Tipo</th><th>Stato</th></tr></thead>
        <tbody>
          {#each s.providers as p}
            <tr>
              <td>{p.name}</td>
              <td style="color:var(--ink-3); font-size:12px">{p.kind}</td>
              <td>{#if p.configured}<span class="pos">configurato</span>{:else}<span class="missing">{p.status}</span>{/if}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <dl class="kv" style="margin-top:10px">
      {#each Object.entries(s.api_keys) as [name, present]}
        <dt>API key {name}</dt>
        <dd>{present ? '••••• presente' : 'assente'}</dd>
      {/each}
    </dl>
    <p style="font-size:12px; color:var(--ink-3)">Le chiavi non vengono mai mostrate né trasmesse al frontend.</p>
  </section>

  <section class="panel">
    <h2>Candidate generator (v{s.candidate_thresholds.version})</h2>
    <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px">
      <div>
        <h3 style="margin-bottom:6px">Accelerazione (almeno una)</h3>
        <dl class="kv">
          <dt>Rendimento 1g / gap</dt><dd>≥ {(s.candidate_thresholds.acceleration.ret_1d_min * 100).toFixed(0)}%</dd>
          <dt>Rendimento 5g</dt><dd>≥ {(s.candidate_thresholds.acceleration.ret_5d_min * 100).toFixed(0)}%</dd>
          <dt>Rendimento 20g</dt><dd>≥ {(s.candidate_thresholds.acceleration.ret_20d_min * 100).toFixed(0)}%</dd>
          <dt>Robust-z rendimento</dt><dd>≥ {s.candidate_thresholds.acceleration.robust_z_min}</dd>
        </dl>
      </div>
      <div>
        <h3 style="margin-bottom:6px">Conferma (almeno una)</h3>
        <dl class="kv">
          <dt>Volume relativo</dt><dd>≥ {s.candidate_thresholds.confirmation.rvol_min}×</dd>
          <dt>Turnover percentile</dt><dd>≥ {s.candidate_thresholds.confirmation.turnover_pctile_min}</dd>
          <dt>Attenzione robust-z</dt><dd>≥ {s.candidate_thresholds.confirmation.attention_z_min}</dd>
          <dt>Evento materiale</dt><dd>{s.candidate_thresholds.confirmation.material_event ? 'sì' : 'no'}</dd>
        </dl>
      </div>
      <div>
        <h3 style="margin-bottom:6px">Universo modellabile</h3>
        <dl class="kv">
          <dt>Prezzo min</dt><dd>${s.candidate_thresholds.universe.min_price}</dd>
          <dt>Market cap</dt><dd>$50 Mln – $5 Mld</dd>
          <dt>Dollar volume 20g</dt><dd>≥ $1 Mln (mediana)</dd>
        </dl>
      </div>
    </div>
  </section>

  <section class="panel">
    <h2>Pesi dello scoring (v{s.scoring.version} · hash <span class="mono">{s.scoring.config_hash.slice(0, 8)}</span>)</h2>
    <div style="display:flex; gap:10px; flex-wrap:wrap; margin-bottom:10px">
      {#each Object.entries(s.scoring.weights) as [comp, w]}
        <div style="border:1px solid var(--border); border-radius:5px; padding:8px 14px; text-align:center; min-width:72px">
          <div class="mono" style="font-size:18px; font-weight:700">{comp}</div>
          <div class="mono" style="color:var(--accent)">{((w as number) * 100).toFixed(0)}%</div>
        </div>
      {/each}
    </div>
    <dl class="kv">
      <dt>Soglia rischio elevato</dt><dd>≥ {s.scoring.thresholds.elevated} (con confidence A/B, nessun gate)</dd>
      <dt>Soglia monitorare</dt><dd>{s.scoring.thresholds.monitor}–{s.scoring.thresholds.elevated - 1}</dd>
      <dt>Sotto soglia</dt><dd>&lt; {s.scoring.thresholds.monitor}: non mostrato nella lista primaria</dd>
    </dl>
    <p style="font-size:12px; color:var(--ink-3)">{s.config_note}</p>
  </section>

  <section class="panel">
    <h2>Job giornalieri (orari ET)</h2>
    <table class="data" style="max-width:820px">
      <thead><tr><th>Job</th><th class="num">Orario ET</th><th>Attivo</th><th>Descrizione</th></tr></thead>
      <tbody>
        {#each Object.entries(s.jobs) as [name, j]}
          {@const job = j as { hour: number; minute: number; enabled: boolean; description: string }}
          <tr>
            <td class="mono" style="font-size:12px">{name}</td>
            <td class="num mono">{String(job.hour).padStart(2, '0')}:{String(job.minute).padStart(2, '0')}</td>
            <td>{job.enabled ? 'sì' : 'no'}</td>
            <td style="font-size:12px; color:var(--ink-2)">{job.description}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </section>

  <section class="panel">
    <h2>Notifiche e AI</h2>
    <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px">
      <div>
        <h3 style="margin-bottom:6px">Notifiche</h3>
        <dl class="kv">
          <dt>Canale</dt><dd>{s.notifications.channel === 'none' ? 'solo in-app' : s.notifications.channel}</dd>
          <dt>Delta score minimo</dt><dd>{s.notifications.rules.score_delta_min} punti</dd>
        </dl>
        <p style="font-size:12px; color:var(--ink-3)">Mai notifiche per semplici duplicati.</p>
      </div>
      <div>
        <h3 style="margin-bottom:6px">AI (opzionale)</h3>
        <dl class="kv">
          <dt>Stato</dt><dd style="color:{s.ai.enabled ? 'var(--claim-fatto)' : 'var(--ink-2)'}">{s.ai.enabled ? `attiva (${s.ai.provider})` : 'disabilitata'}</dd>
          {#if s.ai.enabled}<dt>Modello</dt><dd>{s.ai.model}</dd>{/if}
          <dt>Budget mensile</dt><dd>{s.ai.monthly_budget_eur} €</dd>
          <dt>Speso questo mese</dt><dd>{s.ai.month_spend_eur} €</dd>
          <dt>Enrichment max</dt><dd>primi {s.ai.max_candidates} candidati</dd>
        </dl>
        <p style="font-size:12px; color:var(--ink-3)">
          L'applicazione funziona interamente con AI disabilitata. L'AI non calcola mai lo score
          e non tocca i dati raw.
        </p>
      </div>
    </div>
  </section>

  <section class="panel">
    <h2>Esportazione e backup</h2>
    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap">
      <button onclick={() => doExport('parquet')} disabled={exporting}>Esporta Parquet</button>
      <button onclick={() => doExport('csv')} disabled={exporting}>Esporta CSV</button>
      {#if exportMsg}<span style="font-size:12px; color:var(--accent)">{exportMsg}</span>{/if}
    </div>
    <p style="font-size:12px; color:var(--ink-3)">
      L'export contiene segnali point-in-time e outcome per il backtest.
      Backup del database: vedi <span class="mono">scripts/backup.sh</span> (Restic cifrato) e la
      procedura di restore in SECURITY.md.
    </p>
    <dl class="kv">
      <dt>Retention documenti</dt><dd>{s.retention.documents_days} giorni</dd>
      <dt>Retention contenuti social</dt><dd>{s.retention.social_days} giorni</dd>
    </dl>
  </section>
{/if}

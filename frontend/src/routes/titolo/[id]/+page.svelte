<script lang="ts">
  import { page } from '$app/state';
  import { api } from '$lib/api';
  import Badge from '$lib/components/Badge.svelte';
  import Conf from '$lib/components/Conf.svelte';
  import RiskBar from '$lib/components/RiskBar.svelte';
  import Timeline from '$lib/components/Timeline.svelte';
  import Sparkline from '$lib/components/Sparkline.svelte';
  import { pct, usd, marketCap, mult, ts, day, eventLabel, MISSING, SOURCE_LEVELS } from '$lib/format';

  let detail: any = $state(null);
  let error = $state('');
  let watchBusy = $state(false);

  async function load() {
    try {
      detail = await api.get(`/api/securities/${page.params.id}`);
    } catch (e) {
      error = String((e as Error).message);
    }
  }
  $effect(() => { void page.params.id; load(); });

  async function toggleWatch() {
    if (!detail) return;
    watchBusy = true;
    try {
      if (detail.current?.in_watchlist) {
        const wl = await api.get<any[]>('/api/watchlist');
        const item = wl.find((w) => w.security.id === detail.security.id);
        if (item) await api.del(`/api/watchlist/${item.item_id}`);
      } else {
        await api.post('/api/watchlist', { security_id: detail.security.id });
      }
      await load();
    } finally {
      watchBusy = false;
    }
  }

  let cur = $derived(detail?.current);
  let feats = $derived(detail?.why_entered?.features ?? {});
</script>

{#if error}
  <div class="panel" style="border-color:var(--state-elevated)">Errore: {error}</div>
{:else if !detail}
  <div class="panel" style="color:var(--ink-2)">Caricamento…</div>
{:else}
  <!-- intestazione -->
  <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap; margin-bottom:10px">
    <div>
      <h1>
        <span class="mono">{detail.security.ticker}</span>
        <span style="color:var(--ink-2); font-weight:400"> · {detail.security.name}</span>
        {#if detail.security.is_demo}<span class="missing" style="margin-left:8px">DEMO</span>{/if}
      </h1>
      <div style="font-size:12.5px; color:var(--ink-3); margin-top:2px">
        {detail.security.exchange ?? MISSING} · {detail.security.sector ?? MISSING}
        {#if detail.security.listing_status === 'delisted'} · <span style="color:var(--state-elevated)">DELISTED</span>{/if}
        · id stabile <span class="mono">{detail.security.stable_id.slice(0, 8)}</span>
      </div>
    </div>
    <div style="display:flex; gap:10px; align-items:center">
      {#if cur}
        <Badge state={cur.state} full />
        <RiskBar value={cur.risk_index} />
        <Conf grade={cur.confidence} />
      {/if}
      <button onclick={toggleWatch} disabled={watchBusy}>
        {cur?.in_watchlist ? '★ In watchlist' : '☆ Aggiungi a watchlist'}
      </button>
    </div>
  </div>

  <nav class="section-nav">
    <a href="#perche">1 · Perché è entrato</a>
    <a href="#successo">2 · Cosa è successo</a>
    <a href="#narrativa">3 · Qualità della narrativa</a>
    <a href="#rischi">4 · Rischi della tesi</a>
    <a href="#storico">5 · Storico</a>
  </nav>

  {#if cur?.summary}
    <div class="panel" style="border-left: 3px solid var(--accent)">
      <div>{cur.summary}</div>
      {#if cur.main_contrary_evidence}
        <div style="margin-top:6px; color:var(--claim-fatto)">
          <strong>Evidenza contraria principale:</strong> {cur.main_contrary_evidence}
        </div>
      {/if}
      <div style="margin-top:6px; font-size:11.5px; color:var(--ink-3)">
        Score del {cur.score_date} · scoring v{cur.scoring_version} · config
        <span class="mono">{cur.config_hash.slice(0, 8)}</span> · aggiornato {ts(cur.updated_at)}
      </div>
    </div>
  {/if}

  <!-- 1. PERCHÉ È ENTRATO -->
  <section class="panel" id="perche">
    <h2>1 · Perché è entrato</h2>
    {#if detail.why_entered.candidate_reasons?.length}
      <table class="data" style="max-width:760px">
        <thead><tr><th>Regola</th><th>Tipo</th><th class="num">Osservato</th><th class="num">Soglia</th></tr></thead>
        <tbody>
          {#each detail.why_entered.candidate_reasons as r}
            <tr>
              <td>{r.description}</td>
              <td style="font-size:11px; color:var(--ink-3)">{r.kind === 'acceleration' ? 'accelerazione' : 'conferma'}</td>
              <td class="num">{typeof r.observed === 'number' ? r.observed : String(r.observed)}</td>
              <td class="num">{typeof r.threshold === 'number' ? r.threshold : String(r.threshold)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {:else}
      <p style="color:var(--ink-2)">Nessuna regola attivata alla data dello snapshot (titolo fuori dai candidati odierni).</p>
    {/if}

    <h3 style="margin:14px 0 8px">Feature principali</h3>
    <dl class="kv" style="max-width:680px; grid-template-columns: max-content 1fr max-content 1fr">
      <dt>Prezzo</dt><dd>{usd(feats.price)}</dd>
      <dt>Market cap</dt><dd>{marketCap(feats.market_cap)}</dd>
      <dt>Rend. 1g / 5g / 20g</dt><dd>{pct(feats.ret_1d)} / {pct(feats.ret_5d)} / {pct(feats.ret_20d)}</dd>
      <dt>RVOL</dt><dd>{mult(feats.rvol)}</dd>
      <dt>Gap (pre-market)</dt><dd>{pct(feats.premarket_gap ?? feats.gap)}</dd>
      <dt>Turnover/float</dt><dd>{pct(feats.turnover_float)}</dd>
      <dt>Robust-z rendimento</dt><dd>{feats.robust_z_ret?.toFixed?.(1) ?? MISSING}</dd>
      <dt>Short interest/float</dt><dd>{feats.short_interest_pct_float != null ? pct(feats.short_interest_pct_float) : MISSING}</dd>
    </dl>

    {#if detail.why_entered.missing_fields?.length}
      <h3 style="margin:14px 0 6px; color:var(--accent)">Dati mancanti (mai trattati come zero)</h3>
      <div>
        {#each detail.why_entered.missing_fields as m}
          <span class="missing" style="margin: 0 4px 4px 0; display:inline-block">{m}</span>
        {/each}
      </div>
    {/if}
  </section>

  <!-- 2. COSA È SUCCESSO -->
  <section class="panel" id="successo">
    <h2>2 · Cosa è successo</h2>
    <Timeline bars={detail.timeline.bars} events={detail.timeline.events} documents={detail.timeline.documents} />
    {#if detail.timeline.events.length}
      <h3 style="margin:14px 0 8px">Eventi classificati</h3>
      <table class="data">
        <thead><tr><th>Annunciato</th><th>Tipo</th><th>Titolo</th><th>Stato</th><th>Classificato da</th></tr></thead>
        <tbody>
          {#each detail.timeline.events as e}
            <tr>
              <td class="mono" style="white-space:nowrap">{ts(e.announced_at)}</td>
              <td>{eventLabel(e.type)}{#if e.is_binary} <span class="claim-tag rumor" title="esiti nettamente divergenti possibili">binario</span>{/if}</td>
              <td>{e.title}</td>
              <td style="font-size:12px; color:var(--ink-2)">{e.status}</td>
              <td style="font-size:12px; color:var(--ink-3)">{e.classified_by}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    {#if detail.corporate_actions.length}
      <h3 style="margin:14px 0 8px">Corporate actions</h3>
      <table class="data" style="max-width:680px">
        <thead><tr><th>Tipo</th><th>Data effettiva</th><th class="num">Ratio</th><th>Riconciliata</th></tr></thead>
        <tbody>
          {#each detail.corporate_actions as a}
            <tr>
              <td>{a.type}</td>
              <td class="mono">{a.effective_date}</td>
              <td class="num">{a.ratio ?? MISSING}</td>
              <td>{#if a.reconciled}<span class="pos">sì</span>{:else}<span class="neg">NO — titolo bloccato</span>{/if}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>

  <!-- 3. QUALITÀ DELLA NARRATIVA -->
  <section class="panel" id="narrativa">
    <h2>3 · Qualità della narrativa</h2>
    <div style="display:flex; gap:28px; flex-wrap:wrap; margin-bottom:12px" class="mono">
      <div><span style="font-size:22px; font-weight:700">{detail.narrative.independent_origins}</span>
        <span style="color:var(--ink-3); font-size:12px"> origini indipendenti</span></div>
      <div><span style="font-size:22px; font-weight:700">{detail.narrative.total_documents}</span>
        <span style="color:var(--ink-3); font-size:12px"> documenti totali</span></div>
      <div><span style="font-size:22px; font-weight:700; color:var(--ink-2)">{detail.narrative.duplicate_documents}</span>
        <span style="color:var(--ink-3); font-size:12px"> duplicati (non contano come conferme)</span></div>
      <div><span style="font-size:22px; font-weight:700; color:var(--accent)">{detail.narrative.post_move_documents}</span>
        <span style="color:var(--ink-3); font-size:12px"> pubblicati dopo il movimento</span></div>
    </div>

    {#if detail.narrative.claims.length}
      <h3 style="margin:0 0 8px">Claim</h3>
      {#each detail.narrative.claims as c}
        <div style="border:1px solid var(--border); border-radius:5px; padding:10px 12px; margin-bottom:8px">
          <div style="display:flex; gap:8px; align-items:baseline; flex-wrap:wrap">
            <span class="claim-tag {c.status}">{c.status}</span>
            <strong>{c.subject}</strong> <span style="color:var(--ink-2)">{c.predicate}</span> {c.object}
            {#if c.figure}<span class="mono" style="color:var(--accent)">{c.figure}</span>{/if}
          </div>
          {#if c.evidence_span}
            <div style="font-size:12.5px; color:var(--ink-2); margin-top:5px; border-left:2px solid var(--border-strong); padding-left:8px; font-style:italic">
              «{c.evidence_span}»
            </div>
          {/if}
          <div style="font-size:11.5px; color:var(--ink-3); margin-top:5px">
            {c.claim_date ? day(c.claim_date) : MISSING}
            · conferma: {c.confirmation_level ? `livello ${c.confirmation_level} (${SOURCE_LEVELS[c.confirmation_level]})` : 'nessuna'}
            · estratto da: {c.extracted_by}
            {#each c.relations as r}
              <span style="margin-left:8px; color:{r.relation === 'contraddice' ? 'var(--state-elevated)' : 'var(--ink-2)'}">
                {r.direction === 'in' ? '←' : '→'} {r.relation} #{r.claim_id}
              </span>
            {/each}
          </div>
        </div>
      {/each}
    {:else}
      <p style="color:var(--ink-2)">Nessun claim estratto.</p>
    {/if}

    <h3 style="margin:14px 0 8px">Famiglie di duplicati</h3>
    <div style="display:flex; gap:8px; flex-wrap:wrap">
      {#each detail.narrative.families as f}
        <span class="mono" style="font-size:12px; border:1px solid var(--border); border-radius:4px; padding:3px 8px">
          famiglia #{f.family_id}: {f.copies} {f.copies === 1 ? 'documento' : 'copie'}
        </span>
      {/each}
    </div>
    <p style="font-size:12px; color:var(--ink-3); margin-bottom:0">
      Cento articoli che riscrivono la stessa notizia contano come una sola origine informativa.
      Elenco completo dei documenti nella sezione <a href="/fonti?security_id={detail.security.id}">Fonti e claim</a>.
    </p>
  </section>

  <!-- 4. RISCHI DELLA TESI -->
  <section class="panel" id="rischi">
    <h2>4 · Rischi della tesi</h2>
    {#if detail.thesis_risks}
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap:16px">
        <div>
          <h3 style="color:var(--state-elevated); margin-bottom:6px">Fattori che alzano lo score</h3>
          {#each detail.thesis_risks.factors_up as f}
            <div class="factor"><span class="dir up">▲</span><span class="comp">{f.component}</span>
              <span>{f.explanation ?? f.name}</span></div>
          {:else}<div style="color:var(--ink-3); font-size:12.5px">nessuno</div>{/each}

          <h3 style="color:var(--claim-fatto); margin:14px 0 6px">Fattori che lo riducono / evidenze contrarie</h3>
          {#each detail.thesis_risks.factors_down as f}
            <div class="factor"><span class="dir down">▼</span><span class="comp">{f.component}</span>
              <span>{f.explanation ?? f.name}</span></div>
          {:else}<div style="color:var(--ink-3); font-size:12.5px">nessuno registrato</div>{/each}

          <h3 style="color:var(--accent); margin:14px 0 6px">Componenti non calcolabili</h3>
          {#each detail.thesis_risks.factors_missing as f}
            <div class="factor"><span class="dir na">◌</span><span class="comp">{f.component}</span>
              <span>{f.explanation ?? f.name}</span></div>
          {:else}<div style="color:var(--ink-3); font-size:12.5px">nessuno: tutti i componenti calcolati</div>{/each}
        </div>
        <div>
          <dl class="kv">
            <dt>Stato / gate</dt>
            <dd>{detail.thesis_risks.gate_applied ?? 'nessun gate: stato da punteggio'}</dd>
            <dt>Squeeze hazard</dt>
            <dd>{#if detail.thesis_risks.squeeze_unknown}<span class="missing">sconosciuto — short interest/borrow non disponibili</span>
                {:else}{detail.thesis_risks.squeeze_hazard ?? MISSING} / 100{/if}</dd>
            <dt>Execution/liquidity</dt>
            <dd>{detail.thesis_risks.execution_hazard ?? MISSING} / 100</dd>
            <dt>Borrow</dt>
            <dd>{#if !detail.thesis_risks.borrow_known}<span class="missing">non verificato (nessuna fonte borrow nell'MVP)</span>{:else}noto{/if}</dd>
          </dl>
          <h3 style="margin:14px 0 6px">Condizioni di invalidazione</h3>
          <ul style="margin:0; padding-left:18px; font-size:13px; color:var(--ink-2)">
            {#each detail.thesis_risks.invalidation_conditions as c}<li style="margin-bottom:4px">{c}</li>{/each}
          </ul>
          {#if detail.thesis_risks.missing_data?.length}
            <h3 style="margin:14px 0 6px; color:var(--accent)">Dati mancanti</h3>
            <div>
              {#each detail.thesis_risks.missing_data as m}
                <span class="missing" style="margin:0 4px 4px 0; display:inline-block">{m}</span>
              {/each}
            </div>
          {/if}
        </div>
      </div>
    {:else}
      <p style="color:var(--ink-2)">Nessuno score calcolato per questo titolo.</p>
    {/if}
  </section>

  <!-- 5. STORICO -->
  <section class="panel" id="storico">
    <h2>5 · Storico</h2>
    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap:20px">
      <div>
        <h3 style="margin-bottom:6px">Evoluzione del Risk Index</h3>
        <Sparkline points={detail.history.scores} />
        <table class="data" style="margin-top:10px">
          <thead><tr><th>Data</th><th class="num">Risk Idx</th><th>Stato</th><th>Conf</th><th>Versione</th></tr></thead>
          <tbody>
            {#each [...detail.history.scores].reverse() as s}
              <tr>
                <td class="mono">{s.date}</td>
                <td class="num">{s.risk_index ?? MISSING}</td>
                <td><Badge state={s.state} /></td>
                <td><Conf grade={s.confidence} /></td>
                <td class="mono" style="font-size:11px; color:var(--ink-3)">v{s.scoring_version} · {s.config_hash.slice(0, 6)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <div>
        <h3 style="margin-bottom:6px">Retrospective outcomes</h3>
        {#if detail.history.outcomes.length === 0}
          <p style="color:var(--ink-2); font-size:13px">
            Nessun outcome ancora calcolabile: le finestre 1/3/5/10/20 sedute si chiudono dopo il segnale.
          </p>
        {/if}
        {#each detail.history.outcomes as o}
          <div style="margin-bottom:14px">
            <div style="font-size:12.5px; color:var(--ink-2); margin-bottom:4px">
              Segnale del <span class="mono">{o.score_date}</span>
              (RI {o.risk_index ?? 'n/d'}, {o.state})
            </div>
            <table class="data">
              <thead><tr><th class="num">Orizz.</th><th class="num">P0</th><th class="num">DD intraday</th>
                <th class="num">Rend. chiusura</th><th class="num">Max contrario</th><th>≤−20%</th><th></th></tr></thead>
              <tbody>
                {#each o.horizons as h}
                  <tr>
                    <td class="num">{h.horizon_days}g</td>
                    <td class="num">{usd(h.reference_price)}</td>
                    <td class="num" class:neg={(h.dd_intraday ?? 0) <= -0.2}>{pct(h.dd_intraday)}</td>
                    <td class="num">{pct(h.ret_close)}</td>
                    <td class="num" class:pos={(h.max_adverse_up ?? 0) > 0.1}>{pct(h.max_adverse_up)}</td>
                    <td>{h.hit_minus20 === null ? MISSING : h.hit_minus20 ? '✔ sì' : 'no'}</td>
                    <td style="font-size:11px; color:var(--ink-3)">{h.complete ? 'chiusa' : 'in corso'}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/each}
        <p style="font-size:11.5px; color:var(--ink-3)">
          P0 = apertura/VWAP della seduta successiva al segnale. Etichetta primaria:
          drawdown intraday ≤ −20% entro 10 sedute. «Max contrario» è il massimo rialzo
          successivo, cioè quanto la tesi sarebbe andata contro.
        </p>
      </div>
    </div>
  </section>
{/if}

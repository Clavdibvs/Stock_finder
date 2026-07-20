<script lang="ts">
  import { api } from '$lib/api';
  import { page } from '$app/state';
  import { ts, day, MISSING, SOURCE_LEVELS } from '$lib/format';

  let registry: any[] = $state([]);
  let documents: any[] = $state([]);
  let claims: any[] = $state([]);
  let overrides: any[] = $state([]);
  let includeDuplicates = $state(false);
  let error = $state('');
  let overrideTarget: any = $state(null);
  let overrideStatus = $state('rumor');
  let overrideReason = $state('');
  let overrideError = $state('');

  const CLAIM_STATUSES = ['fatto', 'rumor', 'opinione', 'interpretazione', 'previsione'];

  async function load() {
    try {
      const sid = page.url.searchParams.get('security_id');
      const docParams = new URLSearchParams();
      if (sid) docParams.set('security_id', sid);
      docParams.set('include_duplicates', String(includeDuplicates));
      const claimParams = sid ? `?security_id=${sid}` : '';
      [registry, documents, claims, overrides] = await Promise.all([
        api.get<any[]>('/api/sources/registry'),
        api.get<any[]>(`/api/sources/documents?${docParams.toString()}`),
        api.get<any[]>(`/api/sources/claims${claimParams}`),
        api.get<any[]>('/api/sources/overrides')
      ]);
    } catch (e) {
      error = String((e as Error).message);
    }
  }
  $effect(() => { void includeDuplicates; void page.url.search; load(); });

  async function submitOverride() {
    overrideError = '';
    try {
      await api.post(`/api/sources/claims/${overrideTarget.id}/override`, {
        status: overrideStatus,
        reason: overrideReason
      });
      overrideTarget = null;
      overrideReason = '';
      await load();
    } catch (e) {
      overrideError = String((e as Error).message);
    }
  }

  const licenseLabels: Record<string, string> = {
    metadata_only: 'solo metadati',
    excerpt_allowed: 'estratti brevi',
    full_allowed: 'testo completo consentito',
    unknown: 'da verificare'
  };
</script>

<h1 style="margin-bottom:14px">Fonti e claim</h1>
{#if error}<div class="panel" style="border-color:var(--state-elevated)">Errore: {error}</div>{/if}

<section class="panel">
  <h2>Registro delle fonti</h2>
  <div class="table-wrap">
    <table class="data">
      <thead><tr><th>Fonte</th><th>Dominio</th><th class="num">Livello</th><th>Significato del livello</th>
        <th>Licenza / conservazione</th><th>Configurata</th></tr></thead>
      <tbody>
        {#each registry as s}
          <tr>
            <td style="font-weight:600">{s.name}</td>
            <td class="mono" style="font-size:12px">{s.domain ?? MISSING}</td>
            <td class="num mono">{s.default_source_level}</td>
            <td style="font-size:12px; color:var(--ink-2)">{SOURCE_LEVELS[s.default_source_level]}</td>
            <td style="font-size:12px">{licenseLabels[s.license_status] ?? s.license_status}</td>
            <td>{#if s.configured}<span class="pos">sì</span>{:else}<span class="missing">non configurata</span>{/if}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>

<section class="panel">
  <div style="display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px">
    <h2>Documenti {#if page.url.searchParams.get('security_id')}<a href="/fonti" style="font-size:12px">(togli filtro titolo)</a>{/if}</h2>
    <label class="check"><input type="checkbox" bind:checked={includeDuplicates} /> mostra duplicati</label>
  </div>
  <div class="table-wrap">
    <table class="data">
      <thead><tr><th>Titolo</th><th class="num">Liv.</th><th>Pubblicato</th><th>Visto per la prima volta</th>
        <th>Famiglia</th><th>Licenza</th><th></th></tr></thead>
      <tbody>
        {#each documents as d}
          <tr style={d.is_duplicate ? 'opacity:0.55' : ''}>
            <td>
              {#if d.is_duplicate}<span class="claim-tag duplicato" style="margin-right:6px">duplicato</span>{/if}
              {d.title}
              <div style="font-size:11px; color:var(--ink-3)">{d.publisher ?? d.source_name ?? MISSING}
                {#if d.author} · {d.author}{/if}</div>
            </td>
            <td class="num mono" title={SOURCE_LEVELS[d.source_level]}>{d.source_level}</td>
            <td class="mono" style="font-size:11.5px; white-space:nowrap">{ts(d.published_at)}</td>
            <td class="mono" style="font-size:11.5px; white-space:nowrap">{ts(d.first_seen_at)}</td>
            <td class="mono" style="font-size:11.5px">#{d.duplicate_family_id ?? d.id}
              {#if d.family_size > 1}<span style="color:var(--ink-3)">({d.family_size})</span>{/if}</td>
            <td style="font-size:11.5px">{licenseLabels[d.license_state] ?? d.license_state}</td>
            <td><a href={d.url} target="_blank" rel="noopener noreferrer" style="font-size:12px">apri ↗</a></td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <p style="font-size:11.5px; color:var(--ink-3); margin-bottom:0">
    `pubblicato` e `visto per la prima volta` sono timestamp separati: la propagazione si misura
    sul secondo. Dei contenuti protetti si conservano solo metadati, hash ed estratti brevi.
  </p>
</section>

<section class="panel">
  <h2>Claim</h2>
  {#each claims as c}
    <div style="border:1px solid var(--border); border-radius:5px; padding:10px 12px; margin-bottom:8px">
      <div style="display:flex; gap:8px; align-items:baseline; flex-wrap:wrap">
        <span class="claim-tag {c.status}">{c.status}</span>
        <strong>{c.subject}</strong> <span style="color:var(--ink-2)">{c.predicate}</span> {c.object}
        {#if c.figure}<span class="mono" style="color:var(--accent)">{c.figure}</span>{/if}
        <span style="flex:1"></span>
        <button style="font-size:11.5px; padding:2px 10px"
                onclick={() => { overrideTarget = c; overrideStatus = c.status; }}>
          correggi
        </button>
      </div>
      {#if c.evidence_span}
        <div style="font-size:12.5px; color:var(--ink-2); margin-top:4px; font-style:italic">«{c.evidence_span}»</div>
      {/if}
      <div style="font-size:11.5px; color:var(--ink-3); margin-top:4px">
        {c.claim_date ? day(c.claim_date) : MISSING} · conferma:
        {c.confirmation_level ? `livello ${c.confirmation_level}` : 'nessuna'} · estratto da: {c.extracted_by}
        {#each c.relations as r}
          <span style="margin-left:8px; color:{r.relation === 'contraddice' ? 'var(--state-elevated)' : 'var(--ink-2)'}">
            {r.direction === 'in' ? '←' : '→'} {r.relation} #{r.claim_id}
          </span>
        {/each}
      </div>
    </div>
  {/each}
</section>

{#if overrideTarget}
  <div class="panel" style="border-color:var(--accent); position:fixed; bottom:20px; right:20px; width:380px; z-index:50; box-shadow: 0 8px 32px rgba(0,0,0,0.6)">
    <h3 style="margin-bottom:8px">Correzione manuale claim #{overrideTarget.id}</h3>
    <p style="font-size:12px; color:var(--ink-2); margin-top:0">
      La correzione resta registrata nell'audit trail con autore, valori e motivo.
    </p>
    <div style="display:flex; flex-direction:column; gap:8px">
      <select bind:value={overrideStatus}>
        {#each CLAIM_STATUSES as s}<option value={s}>{s}</option>{/each}
      </select>
      <textarea rows="2" placeholder="Motivo della correzione (obbligatorio, min 5 caratteri)"
                bind:value={overrideReason}></textarea>
      {#if overrideError}<div class="error-line">{overrideError}</div>{/if}
      <div style="display:flex; gap:8px">
        <button class="primary" onclick={submitOverride}
                disabled={overrideReason.trim().length < 5}>Salva correzione</button>
        <button onclick={() => (overrideTarget = null)}>Annulla</button>
      </div>
    </div>
  </div>
{/if}

{#if overrides.length}
  <section class="panel">
    <h2>Correzioni manuali registrate</h2>
    <table class="data">
      <thead><tr><th>Quando</th><th>Entità</th><th>Campo</th><th>Da</th><th>A</th><th>Motivo</th><th>Autore</th></tr></thead>
      <tbody>
        {#each overrides as o}
          <tr>
            <td class="mono" style="font-size:11.5px; white-space:nowrap">{ts(o.created_at)}</td>
            <td class="mono">{o.entity_type} #{o.entity_id}</td>
            <td>{o.field}</td>
            <td><span class="claim-tag {o.old_value}">{o.old_value}</span></td>
            <td><span class="claim-tag {o.new_value}">{o.new_value}</span></td>
            <td style="font-size:12px; color:var(--ink-2)">{o.reason}</td>
            <td style="font-size:12px">{o.created_by}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </section>
{/if}

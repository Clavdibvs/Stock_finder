<script lang="ts">
  /**
   * Timeline sincronizzata: prezzo (linea), volume (barre), eventi e
   * documenti (marker sull'asse). Un solo asse per pannello, griglia
   * recessiva, crosshair + tooltip.
   */
  import { day, usd, int, eventLabel } from '$lib/format';

  type Bar = { date: string; open: number | null; high: number | null; low: number | null; close: number | null; volume: number | null };
  type Ev = { id: number; type: string; title: string; announced_at: string | null; is_binary: boolean };
  type Doc = { id: number; title: string; first_seen_at: string | null; source_level: number; is_duplicate: boolean };

  let { bars, events, documents }: { bars: Bar[]; events: Ev[]; documents: Doc[] } = $props();

  const W = 900, PRICE_H = 220, VOL_H = 70, EV_H = 30, PAD_L = 8, PAD_R = 56;
  const H = PRICE_H + VOL_H + EV_H + 24;

  let valid = $derived(bars.filter((b) => b.close !== null));
  let closes = $derived(valid.map((b) => b.close as number));
  let lows = $derived(valid.map((b) => (b.low ?? b.close) as number));
  let highs = $derived(valid.map((b) => (b.high ?? b.close) as number));
  let minP = $derived(Math.min(...lows) * 0.97);
  let maxP = $derived(Math.max(...highs) * 1.03);
  let maxV = $derived(Math.max(1, ...valid.map((b) => b.volume ?? 0)));

  let x = $derived((i: number) => PAD_L + (i / Math.max(1, valid.length - 1)) * (W - PAD_L - PAD_R));
  let yP = $derived((p: number) => 12 + (1 - (p - minP) / (maxP - minP)) * (PRICE_H - 24));
  let yV = $derived((v: number) => PRICE_H + 10 + (1 - v / maxV) * (VOL_H - 12));

  let linePath = $derived(
    valid.map((b, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${yP(b.close as number).toFixed(1)}`).join(' ')
  );

  function nearestIndex(dateIso: string | null): number | null {
    if (!dateIso || valid.length === 0) return null;
    const d = dateIso.slice(0, 10);
    let best: number | null = null;
    for (let i = 0; i < valid.length; i++) {
      if (valid[i].date <= d) best = i;
    }
    return best;
  }

  let evMarkers = $derived(
    events
      .map((e) => ({ e, i: nearestIndex(e.announced_at) }))
      .filter((m) => m.i !== null) as { e: Ev; i: number }[]
  );
  let docMarkers = $derived(
    documents
      .filter((d) => !d.is_duplicate)
      .map((d) => ({ d, i: nearestIndex(d.first_seen_at) }))
      .filter((m) => m.i !== null) as { d: Doc; i: number }[]
  );

  // griglia prezzo: 4 linee
  let priceTicks = $derived([0, 1, 2, 3].map((k) => minP + ((maxP - minP) * (k + 1)) / 4));

  let hoverI: number | null = $state(null);
  let tipText: string[] = $state([]);
  let svgEl: SVGSVGElement | undefined = $state();

  function onMove(ev: MouseEvent) {
    if (!svgEl || valid.length === 0) return;
    const rect = svgEl.getBoundingClientRect();
    const px = ((ev.clientX - rect.left) / rect.width) * W;
    const frac = (px - PAD_L) / (W - PAD_L - PAD_R);
    const i = Math.max(0, Math.min(valid.length - 1, Math.round(frac * (valid.length - 1))));
    hoverI = i;
    const b = valid[i];
    tipText = [day(b.date), `chiusura ${usd(b.close)}`, `volume ${int(b.volume)}`];
  }
</script>

<div style="position:relative">
  <svg
    bind:this={svgEl}
    viewBox="0 0 {W} {H}"
    style="width:100%; height:auto; display:block"
    role="img"
    aria-label="Timeline di prezzo, volume, eventi e documenti"
    onmousemove={onMove}
    onmouseleave={() => (hoverI = null)}
  >
    <!-- griglia prezzo (recessiva) -->
    {#each priceTicks as t}
      <line x1={PAD_L} x2={W - PAD_R} y1={yP(t)} y2={yP(t)} stroke="var(--chart-grid)" stroke-width="1" />
      <text x={W - PAD_R + 6} y={yP(t) + 4} fill="var(--ink-3)" font-size="10" font-family="var(--font-mono)">
        {t.toFixed(t < 10 ? 2 : 1)}
      </text>
    {/each}

    <!-- prezzo -->
    <path d={linePath} fill="none" stroke="var(--chart-line)" stroke-width="2" stroke-linejoin="round" />
    <text x={PAD_L} y="10" fill="var(--ink-3)" font-size="10" letter-spacing="0.08em">PREZZO ($)</text>

    <!-- volume -->
    <text x={PAD_L} y={PRICE_H + 6} fill="var(--ink-3)" font-size="10" letter-spacing="0.08em">VOLUME</text>
    {#each valid as b, i}
      {#if b.volume !== null}
        <rect
          x={x(i) - 1.4} width="2.8"
          y={yV(b.volume)} height={PRICE_H + VOL_H - 2 - yV(b.volume)}
          fill="var(--chart-vol)" rx="1"
        />
      {/if}
    {/each}

    <!-- riga eventi/documenti -->
    <line x1={PAD_L} x2={W - PAD_R} y1={PRICE_H + VOL_H + 14} y2={PRICE_H + VOL_H + 14} stroke="var(--chart-grid)" />
    <text x={PAD_L} y={PRICE_H + VOL_H + 6} fill="var(--ink-3)" font-size="10" letter-spacing="0.08em">EVENTI E FONTI</text>
    {#each docMarkers as m}
      <circle
        class="event-marker"
        cx={x(m.i)} cy={PRICE_H + VOL_H + 14} r="3.5"
        fill="var(--ink-3)" opacity="0.7"
      >
        <title>{day(m.d.first_seen_at)} — {m.d.title}</title>
      </circle>
    {/each}
    {#each evMarkers as m}
      <g class="event-marker">
        <circle cx={x(m.i)} cy={PRICE_H + VOL_H + 14} r="5.5"
                fill={m.e.is_binary ? 'var(--state-binary)' : 'var(--state-monitor)'}
                stroke="var(--bg-raised)" stroke-width="2" />
        <title>{day(m.e.announced_at)} — {eventLabel(m.e.type)}: {m.e.title}</title>
      </g>
    {/each}

    <!-- crosshair -->
    {#if hoverI !== null}
      <line x1={x(hoverI)} x2={x(hoverI)} y1="12" y2={PRICE_H + VOL_H + 20} stroke="var(--ink-3)" stroke-width="1" stroke-dasharray="3 3" />
      <circle cx={x(hoverI)} cy={yP(closes[hoverI])} r="4" fill="var(--chart-line)" stroke="var(--bg-raised)" stroke-width="2" />
    {/if}
  </svg>

  {#if hoverI !== null}
    <div class="chart-tip" style="left:{(x(hoverI) / W) * 100}%; top:0; transform:translate(-{hoverI > bars.length / 2 ? 110 : -10}%, 0)">
      {#each tipText as t}<div>{t}</div>{/each}
    </div>
  {/if}
</div>

<div style="display:flex; gap:16px; margin-top:6px; font-size:11.5px; color:var(--ink-2)">
  <span><span style="color:var(--state-binary)">●</span> evento binario</span>
  <span><span style="color:var(--state-monitor)">●</span> altro evento</span>
  <span><span style="color:var(--ink-3)">●</span> documento (origine unica)</span>
</div>
